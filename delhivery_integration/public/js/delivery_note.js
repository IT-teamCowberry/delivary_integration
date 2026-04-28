frappe.ui.form.on("Delivery Note", {
    refresh(frm) {
        // Re-apply partner filter on form load (set_warehouse trigger only fires on change)
        if (frm.doc.set_warehouse) {
            filter_delivery_partners(frm);
        }

        // Indicators
        set_delhivery_indicators(frm);

        // When Delhivery is the partner, hide the Shiprocket button (added async by shiprocket_integration)
        if (frm.doc.delivery_partner === "Delhivery") {
            // Retry across the async window the Shiprocket script uses to add its button
            [200, 600, 1200].forEach((ms) => setTimeout(() => {
                frm.remove_custom_button(__("Ship via Shiprocket"), __("Shiprocket"));
            }, ms));
        }

        // Button: Create Delhivery Shipment
        if (frm.doc.docstatus === 1
            && frm.doc.delivery_partner === "Delhivery"
            && !frm.doc.delhivery_waybill) {
            frm.add_custom_button(__("Create Delhivery Shipment"), () => {
                frappe.call({
                    method: "delhivery_integration.api.create_delhivery_shipment",
                    args: { delivery_note: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating shipment on Delhivery..."),
                    callback(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __("Shipment created! AWB: {0}", [r.message.waybill]),
                                indicator: "green"
                            });
                            frm.reload_doc();
                        }
                    },
                    error() {
                        frappe.show_alert({
                            message: __("Failed to create shipment"),
                            indicator: "red"
                        });
                    }
                });
            }, __("Delhivery"));
        }

        // Button: Track Shipment
        if (frm.doc.delhivery_tracking_url) {
            frm.add_custom_button(__("Track Shipment"), () => {
                window.open(frm.doc.delhivery_tracking_url, "_blank");
            }, __("Delhivery"));
        }

        // Button: Print Packing Slip
        if (frm.doc.delhivery_waybill && frm.doc.delhivery_status !== "Cancelled") {
            frm.add_custom_button(__("Print Packing Slip"), () => {
                frappe.call({
                    method: "delhivery_integration.api.get_delhivery_packing_slip",
                    args: { delivery_note: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Fetching packing slip from Delhivery..."),
                    callback(r) {
                        if (r.message && r.message.file_url) {
                            window.open(r.message.file_url, "_blank");
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Delhivery"));
        }

        // Button: Cancel Delhivery Shipment
        if (frm.doc.docstatus === 1
            && frm.doc.delivery_partner === "Delhivery"
            && frm.doc.delhivery_waybill
            && frm.doc.delhivery_status === "Manifested") {
            frm.add_custom_button(__("Cancel Delhivery Shipment"), () => {
                frappe.confirm(
                    __("Are you sure you want to cancel this Delhivery shipment?"),
                    () => {
                        frappe.call({
                            method: "delhivery_integration.api.cancel_delhivery_shipment",
                            args: { delivery_note: frm.doc.name },
                            freeze: true,
                            callback(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __("Shipment cancelled"),
                                        indicator: "orange"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Delhivery"));
        }
    },

    // When warehouse changes, refresh available partner options
    set_warehouse(frm) {
        frm.set_value("delivery_partner", "");
        frm.set_value("delivery_timeline", "");
        frm.set_value("delivery_charge", 0);

        filter_delivery_partners(frm);
    },

    delivery_partner(frm) {
        frm.set_value("delivery_timeline", "");
        frm.set_value("delivery_charge", 0);

        set_delhivery_indicators(frm);

        if (!frm.doc.delivery_partner || !frm.doc.set_warehouse) return;

        let partner = frm.doc.delivery_partner;

        if (partner === "Delhivery") {
            // Hide Shiprocket button right away
            [200, 600, 1200].forEach((ms) => setTimeout(() => {
                frm.remove_custom_button(__("Ship via Shiprocket"), __("Shiprocket"));
            }, ms));

            if (frm.doc.shipping_address_name) {
                trigger_delhivery_fetch(frm);
            }
        } else if (partner === "OWN Rider") {
            frm.set_value("delivery_charge_mode", "Manual");
        }
        // Shiprocket handled by existing cowberry_app code
    },

    delivery_charge_mode(frm) {
        if (frm.doc.delivery_partner === "Delhivery"
            && frm.doc.delivery_charge_mode === "Fetch from API") {
            trigger_delhivery_fetch(frm);
        }
    },

    package_weight(frm) {
        if (should_auto_refetch(frm)) trigger_delhivery_fetch(frm);
    },

    package_length(frm) {
        if (should_auto_refetch(frm)) trigger_delhivery_fetch(frm);
    },

    package_width(frm) {
        if (should_auto_refetch(frm)) trigger_delhivery_fetch(frm);
    },

    package_height(frm) {
        if (should_auto_refetch(frm)) trigger_delhivery_fetch(frm);
    },

    own_rider_timeline(frm) {
        if (frm.doc.delivery_partner === "OWN Rider") {
            frm.set_value("delivery_timeline", frm.doc.own_rider_timeline);
        }
    }
});

function should_auto_refetch(frm) {
    return frm.doc.delivery_partner === "Delhivery"
        && frm.doc.delivery_charge_mode === "Fetch from API";
}

function trigger_delhivery_fetch(frm) {
    if (!frm.doc.shipping_address_name) return;
    frappe.db.get_value(
        "Address",
        frm.doc.shipping_address_name,
        "pincode",
        (r) => {
            if (r && r.pincode) {
                fetch_delhivery_details(frm, r.pincode);
            }
        }
    );
}

function set_delhivery_indicators(frm) {
    if (frm.doc.delivery_partner !== "Delhivery") return;

    frm.dashboard.clear_headline();

    if (frm.doc.delhivery_waybill) {
        frm.dashboard.set_headline_alert(
            __("Delhivery Shipment Created — AWB: {0} | Status: {1}", [
                frm.doc.delhivery_waybill,
                frm.doc.delhivery_status || "Manifested",
            ]),
            "green"
        );
    } else {
        frm.dashboard.set_headline_alert(
            __("Delivery Partner: Delhivery — shipment not yet created"),
            "blue"
        );
    }
}

function filter_delivery_partners(frm) {
    if (!frm.doc.set_warehouse) return;

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Warehouse",
            name: frm.doc.set_warehouse,
            fields: ["delivery_partners"]
        },
        callback(r) {
            if (r.message && r.message.delivery_partners) {
                let partners = r.message.delivery_partners
                    .filter(p => p.enabled)
                    .map(p => p.delivery_partner);

                let options = [""].concat(partners);
                frm.set_df_property("delivery_partner", "options", options.join("\n"));
            }
        }
    });
}

function fetch_delhivery_details(frm, pincode) {
    if (!pincode) return;

    frappe.call({
        method: "delhivery_integration.api.get_delivery_options",
        args: {
            warehouse: frm.doc.set_warehouse,
            delivery_pincode: pincode,
            weight: frm.doc.package_weight || null,
            length: frm.doc.package_length || null,
            width: frm.doc.package_width || null,
            height: frm.doc.package_height || null
        },
        freeze: true,
        freeze_message: __("Fetching delivery charges from Delhivery..."),
        callback(r) {
            if (!r.message || !r.message.options) return;

            let delhivery = r.message.options.find(o => o.partner === "Delhivery");
            if (!delhivery) return;

            if (delhivery.error) {
                // Surface API errors instead of silently treating as unserviceable
                frappe.msgprint({
                    title: __("Delhivery API Issue"),
                    message: __("{0}<br><br>You can switch Charge Mode to Manual and enter the charge by hand.", [delhivery.error]),
                    indicator: "orange"
                });
                return;
            }

            if (!delhivery.serviceable) {
                frappe.msgprint({
                    title: __("Not Serviceable"),
                    message: __("Pincode {0} is not serviceable by Delhivery.", [pincode]),
                    indicator: "red"
                });
                return;
            }

            if (delhivery.timeline) {
                frm.set_value("delivery_timeline", delhivery.timeline);
            }
            if (delhivery.charge && delhivery.charge_source === "api") {
                frm.set_value("delivery_charge", delhivery.charge);
                frm.set_value("delivery_charge_mode", "Fetch from API");

                let alert_msg = __("Charge updated: ₹{0}", [delhivery.charge]);
                if (delhivery.chargeable_weight_grams) {
                    alert_msg += __(" (chargeable weight: {0}g)", [delhivery.chargeable_weight_grams]);
                }
                frappe.show_alert({
                    message: alert_msg,
                    indicator: "green"
                });
            }
        }
    });
}
