from frappe.tests import UnitTestCase

from delhivery_integration.tasks import TERMINAL_STATUSES, resolve_status


class TestResolveStatus(UnitTestCase):
    """resolve_status must read StatusType before Status — shapes below were
    captured from live Delhivery tracking responses."""

    def test_delivered_by_status_type(self):
        block = {"Status": "Delivered", "StatusType": "DL", "StatusCode": "EOD-38"}
        self.assertEqual(resolve_status(block), ("Delivered", False))

    def test_rto_in_transit_is_rto_not_forward_movement(self):
        # An RT leg reports Status="In Transit" while returning to origin.
        block = {"Status": "In Transit", "StatusType": "RT", "StatusCode": "X-OLL4F"}
        self.assertEqual(resolve_status(block), ("RTO", False))

    def test_dispatched_is_out_for_delivery(self):
        block = {"Status": "Dispatched", "StatusType": "UD", "Instructions": "Out for delivery"}
        self.assertEqual(resolve_status(block), ("Out for Delivery", False))

    def test_forward_in_transit(self):
        self.assertEqual(
            resolve_status({"Status": "In Transit", "StatusType": "UD"}),
            ("In Transit", False),
        )

    def test_manifested(self):
        block = {"Status": "Manifested", "StatusType": "UD", "StatusCode": "DTUP-203"}
        self.assertEqual(resolve_status(block), ("Manifested", False))

    def test_pending(self):
        self.assertEqual(
            resolve_status({"Status": "Pending", "StatusType": "UD"}),
            ("Pending", False),
        )

    def test_status_type_is_case_insensitive(self):
        self.assertEqual(resolve_status({"StatusType": "dl"}), ("Delivered", False))

    def test_unknown_is_flagged_unmapped(self):
        self.assertEqual(resolve_status({"Status": "Lost", "StatusType": "LT"}), (None, True))

    def test_empty_block_is_unmapped(self):
        self.assertEqual(resolve_status({}), (None, True))
        self.assertEqual(resolve_status(None), (None, True))

    def test_terminal_statuses_stop_repolling(self):
        for status in ("Delivered", "RTO", "Cancelled"):
            self.assertIn(status, TERMINAL_STATUSES)
