frappe.ui.form.on("Delhivery Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), () => {
            console.log("==ss===dsad==========dasdas")


            if (frm.is_dirty()) {
                frappe.msgprint(__("Please save the form before testing the connection."));
                return;
            }
            frm.call("test_connection");
        });
    },
});
