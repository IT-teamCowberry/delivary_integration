app_name = "delhivery_integration"
app_title = "Delhivery Integration"
app_publisher = "Reformiqo"
app_description = "Delhivery courier integration with multi-warehouse delivery partner support"
app_email = "info@reformiqo.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

# After install — create custom fields on Delivery Note + Warehouse
after_install = "delhivery_integration.install.after_install"

# Doc Events
doc_events = {
    "Delivery Note": {
        "on_cancel": "delhivery_integration.events.on_delivery_note_cancel",
    }
}

# Scheduler — poll Delhivery tracking every 2 hours
scheduler_events = {
    "cron": {
        "0 */2 * * *": [
            "delhivery_integration.tasks.update_all_tracking"
        ]
    }
}

# Fixtures — export custom fields belonging to this module
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "Delhivery Integration"]]
    }
]

# Inject JS on Delivery Note form
doctype_js = {
    "Delivery Note": "public/js/delivery_note.js"
}
