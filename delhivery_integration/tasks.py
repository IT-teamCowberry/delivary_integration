import frappe

from delhivery_integration.delhivery_api import DelhiveryAPI

# Delhivery's tracking API reports two status keys on Shipment.Status:
#   StatusType — the leg: UD (forward / undelivered), DL (delivered), RT (return to origin)
#   Status     — the fine-grained state within that leg
# StatusType must win: an RT shipment also reports Status="In Transit" while
# travelling back to the origin, which must not be read as forward movement.
STATUS_TYPE_MAP = {
    "DL": "Delivered",
    "RT": "RTO",
    "CN": "Cancelled",
}

# Forward-leg (UD) states. "Dispatched" is Delhivery's wire value for out-for-delivery.
UD_STATUS_MAP = {
    "Manifested": "Manifested",
    "Not Picked": "Not Picked",
    "Pending": "Pending",
    "In Transit": "In Transit",
    "Dispatched": "Out for Delivery",
    "Out For Delivery": "Out for Delivery",
    "Out for Delivery": "Out for Delivery",
    "Delivered": "Delivered",
}

TERMINAL_STATUSES = ["Delivered", "Cancelled", "RTO"]


def resolve_status(status_obj):
    """Map a Delhivery ``Shipment.Status`` block to our delhivery_status vocabulary.

    Returns ``(mapped, unmapped)`` — ``mapped`` is None when neither key is recognised.
    """
    status_obj = status_obj or {}
    status_type = (status_obj.get("StatusType") or "").strip().upper()
    status = (status_obj.get("Status") or "").strip()

    if status_type in STATUS_TYPE_MAP:
        return STATUS_TYPE_MAP[status_type], False
    if status in UD_STATUS_MAP:
        return UD_STATUS_MAP[status], False
    return None, True


def _emit_status_updated(delivery_note, status, previous):
    """delhivery_status is written with db.set_value, so no doc_event fires.
    ``delhivery_status_updated`` is the substitute other apps subscribe to."""
    for handler in frappe.get_hooks("delhivery_status_updated") or []:
        try:
            frappe.get_attr(handler)(
                delivery_note=delivery_note, status=status, previous=previous
            )
        except Exception:
            frappe.log_error(
                title=f"delhivery_status_updated hook failed: {handler}",
                message=frappe.get_traceback(),
            )


def update_all_tracking():
    """
    Scheduled task: poll Delhivery tracking API for all active shipments.
    Cron-driven from hooks.py (default every 2 hours).
    """
    settings = frappe.get_single("Delhivery Settings")
    if not settings.enabled:
        return

    pending_dns = frappe.get_all(
        "Delivery Note",
        filters={
            "delivery_partner": "Delhivery",
            "delhivery_waybill": ["is", "set"],
            "delhivery_status": ["not in", TERMINAL_STATUSES],
            "docstatus": 1,
        },
        fields=["name", "delhivery_waybill", "delhivery_status"],
    )

    if not pending_dns:
        return

    api = DelhiveryAPI()

    for dn in pending_dns:
        try:
            result = api.track_shipment(dn.delhivery_waybill)
            if not result.get("success"):
                continue

            shipment_data = result.get("data", {}) or {}
            packages = shipment_data.get("ShipmentData", [])
            if not packages:
                continue

            pkg = packages[0] if isinstance(packages, list) else packages
            shipment = pkg.get("Shipment", {}) or {}
            status_obj = shipment.get("Status", {}) or {}

            mapped_status, unmapped = resolve_status(status_obj)
            if unmapped:
                frappe.log_error(
                    f"Unmapped Delhivery status {status_obj!r} for waybill {dn.delhivery_waybill}",
                    "Delhivery Tracking",
                )
                continue

            if mapped_status == dn.delhivery_status:
                continue

            frappe.db.set_value(
                "Delivery Note",
                dn.name,
                {"delhivery_status": mapped_status},
                update_modified=False,
            )
            # Commit per DN so a worker crash doesn't lose previous updates.
            frappe.db.commit()

            _emit_status_updated(dn.name, mapped_status, dn.delhivery_status)

            # Auto-create Sales Invoice + Payment Entry on delivery transition
            if mapped_status == "Delivered":
                try:
                    from delhivery_integration.invoicing import handle_delivered

                    handle_delivered(dn.name)
                except Exception as ie:
                    frappe.db.rollback()
                    frappe.log_error(
                        f"Delhivery auto-invoice error for {dn.name}: {str(ie)}",
                        "Delhivery Tracking",
                    )

        except Exception as e:
            frappe.log_error(
                f"Delhivery tracking error for {dn.delhivery_waybill}: {str(e)}",
                "Delhivery Tracking",
            )
