import frappe
from frappe.model.document import Document


class DelhiverySettings(Document):

    @property
    def base_url(self):
        if self.environment == "Production":
            return (self.production_base_url or "").rstrip("/")
        return (self.sandbox_base_url or "").rstrip("/")

    @frappe.whitelist()
    def test_connection(self):
        from delhivery_integration.delhivery_api import DelhiveryAPI

        try:
            api = DelhiveryAPI()
            result = api.check_pincode(self.default_pickup_pincode or "110001")
            if result.get("success"):
                frappe.msgprint(
                    "Connection successful.",
                    indicator="green",
                    alert=True,
                )
            else:
                frappe.throw(f"Connection failed: {result.get('error')}")
        except Exception as e:
            frappe.throw(f"Connection failed: {str(e)}")
