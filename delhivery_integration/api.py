import frappe
from frappe import _

from delhivery_integration.delhivery_api import DelhiveryAPI


@frappe.whitelist()
def get_delivery_options(
    warehouse,
    delivery_pincode,
    weight=None,
    length=None,
    width=None,
    height=None,
):
    """
    Returns available delivery partners for a warehouse with timeline and charges.
    Called by: DN client script + Cowberry website checkout.
    """
    warehouse_doc = frappe.get_doc("Warehouse", warehouse)
    partners = warehouse_doc.get("delivery_partners", []) or []
    options = []

    for p in partners:
        if not p.enabled:
            continue

        option = {
            "partner": p.delivery_partner,
            "charge_mode": p.charge_mode,
            "pickup_pincode": p.pickup_pincode,
        }

        if p.delivery_partner == "Delhivery" and p.charge_mode == "Fetch from API":
            try:
                api = DelhiveryAPI()
                svc = api.check_pincode(delivery_pincode)
                option["serviceable"] = (
                    svc.get("serviceable", False) if svc.get("success") else False
                )

                if option["serviceable"]:
                    settings = frappe.get_single("Delhivery Settings")
                    actual_w = int(weight) if weight else (settings.default_weight_grams or 500)

                    # Volumetric weight: (L × W × H) / 5000 in cm/grams. Use max(actual, vol).
                    L = float(length) if length else (settings.default_length_cm or 0)
                    W = float(width) if width else (settings.default_width_cm or 0)
                    H = float(height) if height else (settings.default_height_cm or 0)
                    vol_w = int((L * W * H) / 5.0) if (L and W and H) else 0
                    chargeable_w = max(actual_w, vol_w)

                    charge_result = api.fetch_shipping_charge(
                        p.pickup_pincode, delivery_pincode, chargeable_w
                    )
                    if charge_result.get("success"):
                        charge_data = charge_result.get("data", [])
                        amount = 0
                        if isinstance(charge_data, list) and charge_data:
                            amount = charge_data[0].get("total_amount", 0)
                        elif isinstance(charge_data, dict):
                            amount = charge_data.get("total_amount", 0)

                        # Defensive: API sometimes returns charge as string
                        try:
                            amount = float(amount) if amount else 0
                        except (TypeError, ValueError):
                            amount = 0

                        if amount > 0:
                            option["charge"] = amount
                            option["charge_source"] = "api"
                            option["chargeable_weight_grams"] = chargeable_w
                        else:
                            option["charge_source"] = "manual"
                            option["error"] = "Delhivery returned no charge for this route"
                    else:
                        option["charge_source"] = "manual"
                        option["error"] = (
                            charge_result.get("error") or "Charge API call failed"
                        )

                    # TODO: Replace with actual Delhivery EDD endpoint when available
                    option["timeline"] = "3-5 business days"
            except Exception as e:
                frappe.log_error(
                    f"Delhivery API error for warehouse {warehouse}: {str(e)}",
                    "Delhivery Integration",
                )
                option["serviceable"] = False
                option["charge_source"] = "manual"
                option["error"] = f"Delhivery API error: {str(e)[:200]}"

        elif p.delivery_partner == "OWN Rider":
            option["timeline_options"] = (
                p.own_rider_timeline_options or "Same Day,Tomorrow,6-8 Hours,Next Day"
            ).split(",")
            option["charge"] = 0
            option["charge_source"] = "manual"
            option["serviceable"] = True

        elif p.delivery_partner == "Shiprocket":
            # Shiprocket is handled by existing cowberry_app integration.
            option["charge_source"] = (p.charge_mode or "Manual").lower().replace(" ", "_")
            option["serviceable"] = True

        options.append(option)

    return {"options": options}


@frappe.whitelist()
def fetch_delhivery_charge(origin_pin, dest_pin, weight=500):
    """Fetch shipping charge from Delhivery API."""
    api = DelhiveryAPI()
    return api.fetch_shipping_charge(origin_pin, dest_pin, int(weight))


@frappe.whitelist()
def check_serviceability(pincode):
    """Check if pincode is serviceable."""
    api = DelhiveryAPI()
    return api.check_pincode(pincode)


@frappe.whitelist()
def create_delhivery_shipment(delivery_note):
    """
    Full shipment creation flow:
    1. Acquire row lock to prevent double-fetch races
    2. Fetch waybill
    3. Build shipment payload from DN
    4. Create order on Delhivery
    5. Store waybill + tracking URL on DN
    """
    dn = frappe.get_doc("Delivery Note", delivery_note)

    if dn.delivery_partner != "Delhivery":
        frappe.throw(_("Delivery partner is not Delhivery for this Delivery Note."))

    # Lock the DN row and re-check waybill atomically — prevents two concurrent
    # requests from both passing the check and consuming two waybills.
    locked_waybill = frappe.db.get_value(
        "Delivery Note", dn.name, "delhivery_waybill", for_update=True
    )
    if locked_waybill:
        frappe.throw(_("Shipment already created. Waybill: {0}").format(locked_waybill))

    api = DelhiveryAPI()

    # 1. Get warehouse config
    warehouse_partners = frappe.get_all(
        "Warehouse Delivery Partner",
        filters={
            "parent": dn.set_warehouse,
            "delivery_partner": "Delhivery",
            "enabled": 1,
        },
        fields=["pickup_pincode", "pickup_location_name"],
    )
    if not warehouse_partners:
        frappe.throw(
            _("Delhivery is not configured for warehouse {0}").format(dn.set_warehouse)
        )

    wp = warehouse_partners[0]
    pickup_location = wp.pickup_location_name

    if not pickup_location:
        frappe.throw(
            _("Pickup location name not set for Delhivery in warehouse {0}").format(
                dn.set_warehouse
            )
        )

    # 2. Fetch waybill
    waybill_result = api.fetch_waybill(count=1)
    if not waybill_result.get("success"):
        frappe.throw(
            _("Failed to fetch waybill: {0}").format(waybill_result.get("error"))
        )

    waybill_data = waybill_result.get("data")
    if isinstance(waybill_data, list):
        waybill = str(waybill_data[0])
    elif isinstance(waybill_data, dict):
        waybill = str(waybill_data.get("waybill", ""))
    else:
        waybill = str(waybill_data)

    if not waybill:
        frappe.throw(_("Empty waybill received from Delhivery"))

    # 3. Build shipment data
    if not dn.shipping_address_name:
        frappe.throw(_("Shipping address is required for Delhivery shipment"))

    address = frappe.get_doc("Address", dn.shipping_address_name)

    settings = frappe.get_single("Delhivery Settings")

    phone = (
        dn.contact_mobile
        or address.phone
        or _get_customer_primary_phone(dn.customer)
        or ""
    )
    if not phone:
        frappe.throw(
            _(
                "No phone number found for {0}. Set Contact Mobile on the Delivery Note, "
                "or Phone on the Shipping Address, or Mobile on the Customer's primary contact."
            ).format(dn.customer)
        )

    payment_mode = dn.get("delhivery_payment_mode") or "Prepaid"
    cod_amount = str(dn.grand_total) if payment_mode == "COD" else "0"

    shipment_data = {
        "name": dn.customer_name,
        "add": address.address_line1 or "",
        "add2": address.address_line2 or "",
        "pin": address.pincode,
        "city": address.city,
        "state": address.state,
        "country": "India",
        "phone": phone,
        "order": dn.name,
        "payment_mode": payment_mode,
        "total_amount": str(dn.grand_total),
        "cod_amount": cod_amount,
        "weight": dn.get("package_weight") or settings.default_weight_grams or 500,
        "shipment_width": dn.get("package_width") or settings.default_width_cm or 10,
        "shipment_height": dn.get("package_height") or settings.default_height_cm or 10,
        "shipment_length": dn.get("package_length") or settings.default_length_cm or 10,
        "waybill": waybill,
        "product_desc": ", ".join([i.item_name for i in dn.items][:5]),
        "quantity": sum([i.qty for i in dn.items]),
    }

    # 4. Create shipment
    create_result = api.create_shipment(shipment_data, pickup_location)
    if not create_result.get("success"):
        frappe.throw(
            _("Failed to create Delhivery shipment: {0}").format(
                create_result.get("error")
            )
        )

    # 5. Update DN
    tracking_url = api.tracking_url(waybill)
    frappe.db.set_value(
        "Delivery Note",
        dn.name,
        {
            "delhivery_waybill": waybill,
            "delhivery_status": "Manifested",
            "delhivery_tracking_url": tracking_url,
        },
        update_modified=False,
    )

    frappe.db.commit()
    return {
        "waybill": waybill,
        "status": "Manifested",
        "tracking_url": tracking_url,
    }


@frappe.whitelist()
def cancel_delhivery_shipment(delivery_note):
    """Cancel Delhivery shipment if still in Manifested state."""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    if not dn.delhivery_waybill:
        return {"success": False, "error": "No waybill found"}

    if dn.delhivery_status not in ("Manifested", ""):
        frappe.throw(
            _("Cannot cancel — shipment is already {0}").format(dn.delhivery_status)
        )

    api = DelhiveryAPI()
    result = api.cancel_shipment(dn.delhivery_waybill)

    if result.get("success"):
        frappe.db.set_value(
            "Delivery Note",
            dn.name,
            {"delhivery_status": "Cancelled"},
            update_modified=False,
        )
        frappe.db.commit()

    return result


@frappe.whitelist()
def get_delhivery_packing_slip(delivery_note):
    """Fetch packing slip PDF from Delhivery, save as File on DN, return file URL."""
    dn = frappe.get_doc("Delivery Note", delivery_note)

    if not dn.delhivery_waybill:
        frappe.throw(_("No waybill found. Create the Delhivery shipment first."))

    if dn.delhivery_status == "Cancelled":
        frappe.throw(_("Cannot fetch packing slip — shipment is Cancelled."))

    api = DelhiveryAPI()
    result = api.get_packing_slip(dn.delhivery_waybill)

    if not result.get("success"):
        frappe.throw(
            _("Failed to fetch packing slip: {0}").format(result.get("error"))
        )

    pdf_bytes = result["data"]
    if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
        frappe.throw(
            _("Delhivery returned an invalid PDF (response was not a real PDF file).")
        )
    base_name = f"Delhivery-PackingSlip-{dn.delhivery_waybill}"

    # Save the new file FIRST with a temporary name so an existing slip stays
    # accessible if the new save fails (disk full, permissions, etc.).
    tmp_file_name = f"{base_name}-new.pdf"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": tmp_file_name,
        "attached_to_doctype": "Delivery Note",
        "attached_to_name": dn.name,
        "content": pdf_bytes,
        "is_private": 1,
    })
    file_doc.save(ignore_permissions=True)

    # Now safe to delete previous slip(s) — new one is on disk.
    final_file_name = f"{base_name}.pdf"
    previous = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Delivery Note",
            "attached_to_name": dn.name,
            "file_name": final_file_name,
        },
        pluck="name",
    )
    for old in previous:
        try:
            frappe.delete_doc("File", old, ignore_permissions=True, force=True)
        except Exception as e:
            frappe.log_error(
                f"Failed to delete old packing slip {old}: {str(e)}",
                "Delhivery Integration",
            )

    # Rename temp to final.
    file_doc.db_set("file_name", final_file_name, update_modified=False)

    frappe.db.set_value(
        "Delivery Note",
        dn.name,
        "delhivery_packing_slip_url",
        file_doc.file_url,
        update_modified=False,
    )
    frappe.db.commit()

    return {"file_url": file_doc.file_url, "file_name": final_file_name}


@frappe.whitelist()
def get_tracking_info(waybill=None, delivery_note=None):
    """Get tracking info by waybill or delivery note name."""
    if not waybill and delivery_note:
        waybill = frappe.db.get_value("Delivery Note", delivery_note, "delhivery_waybill")

    if not waybill:
        return {"success": False, "error": "No waybill provided"}

    api = DelhiveryAPI()
    return api.track_shipment(waybill)


def _get_customer_primary_phone(customer):
    contact_name = frappe.db.get_value(
        "Dynamic Link",
        {"link_doctype": "Customer", "link_name": customer, "parenttype": "Contact"},
        "parent",
    )
    if not contact_name:
        return None
    return frappe.db.get_value("Contact", contact_name, "mobile_no") or frappe.db.get_value(
        "Contact", contact_name, "phone"
    )
