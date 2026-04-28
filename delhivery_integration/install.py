import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
    create_delivery_note_custom_fields()
    create_warehouse_custom_fields()
    frappe.db.commit()


def create_delivery_note_custom_fields():
    custom_fields = {
        "Delivery Note": [
            dict(
                fieldname="delivery_partner_section",
                label="Delivery Partner Details",
                fieldtype="Section Break",
                insert_after="transporter_name",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delivery_partner",
                label="Delivery Partner",
                fieldtype="Select",
                options="\nOWN Rider\nShiprocket\nDelhivery",
                insert_after="delivery_partner_section",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delivery_timeline",
                label="Estimated Delivery Timeline",
                fieldtype="Data",
                read_only=1,
                insert_after="delivery_partner",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delivery_charge_mode",
                label="Charge Mode",
                fieldtype="Select",
                options="Manual\nFetch from API",
                default="Manual",
                insert_after="delivery_timeline",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delivery_charge",
                label="Delivery Charge",
                fieldtype="Currency",
                insert_after="delivery_charge_mode",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_payment_mode",
                label="Payment Mode",
                fieldtype="Select",
                options="Prepaid\nCOD",
                default="Prepaid",
                description="Prepaid = customer paid online. COD = collect grand_total on delivery.",
                depends_on="eval:doc.delivery_partner=='Delhivery'",
                insert_after="delivery_charge",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_col_break",
                fieldtype="Column Break",
                insert_after="delhivery_payment_mode",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_waybill",
                label="Delhivery Waybill (AWB)",
                fieldtype="Data",
                read_only=1,
                insert_after="delhivery_col_break",
                depends_on="eval:doc.delivery_partner=='Delhivery'",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_status",
                label="Delhivery Status",
                fieldtype="Data",
                read_only=1,
                insert_after="delhivery_waybill",
                depends_on="eval:doc.delivery_partner=='Delhivery'",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_tracking_url",
                label="Tracking URL",
                fieldtype="Data",
                options="URL",
                read_only=1,
                insert_after="delhivery_status",
                depends_on="eval:doc.delivery_partner=='Delhivery'",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="delhivery_packing_slip_url",
                label="Packing Slip URL",
                fieldtype="Data",
                options="URL",
                read_only=1,
                insert_after="delhivery_tracking_url",
                depends_on="eval:doc.delivery_partner=='Delhivery' && doc.delhivery_waybill",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_dimensions_section",
                label="Package Dimensions",
                fieldtype="Section Break",
                collapsible=1,
                insert_after="delhivery_packing_slip_url",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_weight",
                label="Package Weight (g)",
                fieldtype="Int",
                description="Used by Delhivery to calculate shipping charge. Falls back to Delhivery Settings default if blank.",
                insert_after="package_dimensions_section",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_length",
                label="Package Length (cm)",
                fieldtype="Int",
                insert_after="package_weight",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_dim_col_break",
                fieldtype="Column Break",
                insert_after="package_length",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_width",
                label="Package Width (cm)",
                fieldtype="Int",
                insert_after="package_dim_col_break",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="package_height",
                label="Package Height (cm)",
                fieldtype="Int",
                insert_after="package_width",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="own_rider_section",
                label="OWN Rider Details",
                fieldtype="Section Break",
                collapsible=1,
                depends_on="eval:doc.delivery_partner=='OWN Rider'",
                insert_after="package_height",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="own_rider_timeline",
                label="Delivery Timeline",
                fieldtype="Select",
                options="Same Day\nTomorrow\n6-8 Hours\nNext Day",
                insert_after="own_rider_section",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="own_rider_name",
                label="Rider Name",
                fieldtype="Data",
                insert_after="own_rider_timeline",
                module="Delhivery Integration",
            ),
            dict(
                fieldname="own_rider_phone",
                label="Rider Phone",
                fieldtype="Data",
                insert_after="own_rider_name",
                module="Delhivery Integration",
            ),
        ]
    }
    create_custom_fields(custom_fields, update=True)


def create_warehouse_custom_fields():
    custom_fields = {
        "Warehouse": [
            dict(
                fieldname="delivery_partners",
                label="Delivery Partners",
                fieldtype="Table",
                options="Warehouse Delivery Partner",
                insert_after="disabled",
                module="Delhivery Integration",
            ),
        ]
    }
    create_custom_fields(custom_fields, update=True)
