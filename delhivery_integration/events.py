import frappe

from delhivery_integration.delhivery_api import DelhiveryAPI


def on_delivery_note_cancel(doc, method):
    """When DN is cancelled, cancel Delhivery shipment if applicable."""
    if doc.get("delivery_partner") != "Delhivery":
        return

    if not doc.get("delhivery_waybill"):
        return

    if doc.get("delhivery_status") in ("Delivered", "Cancelled", "RTO"):
        frappe.msgprint(
            f"Delhivery shipment is already {doc.delhivery_status}. "
            "Manual action may be needed."
        )
        return

    try:
        api = DelhiveryAPI()
        result = api.cancel_shipment(doc.delhivery_waybill)
        if result.get("success"):
            doc.db_set("delhivery_status", "Cancelled")
            frappe.msgprint("Delhivery shipment cancelled successfully.")
        else:
            frappe.msgprint(
                f"Could not cancel Delhivery shipment: {result.get('error')}. "
                "Please cancel manually on Delhivery portal."
            )
    except Exception as e:
        frappe.log_error(
            f"Delhivery cancel error for {doc.delhivery_waybill}: {str(e)}",
            "Delhivery Integration",
        )
        frappe.msgprint(
            "Failed to cancel Delhivery shipment. Please cancel manually on Delhivery portal."
        )
