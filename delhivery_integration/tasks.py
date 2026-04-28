import frappe

from delhivery_integration.delhivery_api import DelhiveryAPI


STATUS_MAP = {
    "Manifested": "Manifested",
    "In Transit": "In Transit",
    "Out For Delivery": "Out for Delivery",
    "Delivered": "Delivered",
    "RTO Initiated": "RTO",
    "RTO Delivered": "RTO",
    "Cancelled": "Cancelled",
    "Pending": "Pending",
    "Not Picked": "Not Picked",
}

TERMINAL_STATUSES = ["Delivered", "Cancelled", "RTO"]


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
            status_type = status_obj.get("StatusType", "")

            # Pass through raw value when unmapped — don't silently mask new statuses.
            mapped_status = STATUS_MAP.get(status_type, status_type or dn.delhivery_status)
            if status_type and status_type not in STATUS_MAP:
                frappe.log_error(
                    f"Unmapped Delhivery status '{status_type}' for waybill {dn.delhivery_waybill}",
                    "Delhivery Tracking",
                )

            if mapped_status != dn.delhivery_status:
                frappe.db.set_value(
                    "Delivery Note",
                    dn.name,
                    {"delhivery_status": mapped_status},
                    update_modified=False,
                )
                # Commit per DN so a worker crash doesn't lose previous updates.
                frappe.db.commit()

        except Exception as e:
            frappe.log_error(
                f"Delhivery tracking error for {dn.delhivery_waybill}: {str(e)}",
                "Delhivery Tracking",
            )
