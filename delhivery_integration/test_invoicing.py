from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from delhivery_integration import invoicing


class TestCreatePaymentReference(UnitTestCase):
    """_create_payment_for_si must stamp reference_no + reference_date so bank
    Payment Entries pass ERPNext's validate_transaction_reference."""

    def _run(self, settings):
        pe = MagicMock()
        pe.reference_no = None
        pe.reference_date = None
        pe.cost_center = None
        pe.mode_of_payment = None
        si = MagicMock()
        si.name = "SINV-TEST-0001"
        si.company = "Test Co"
        with patch(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            return_value=pe,
        ), patch.object(invoicing, "_resolve_paid_to_account", return_value=None):
            invoicing._create_payment_for_si(si, settings)
        return pe

    def test_reference_no_and_date_are_set(self):
        settings = MagicMock(
            default_mode_of_payment=None,
            default_cost_center=None,
            auto_submit_payment=False,
        )
        pe = self._run(settings)
        self.assertEqual(pe.reference_no, "SINV-TEST-0001")
        self.assertTrue(pe.reference_date)

    def test_existing_reference_not_overwritten(self):
        settings = MagicMock(
            default_mode_of_payment=None,
            default_cost_center=None,
            auto_submit_payment=False,
        )
        pe = MagicMock()
        pe.reference_no = "EXISTING-REF"
        pe.reference_date = "2026-01-01"
        pe.cost_center = None
        pe.mode_of_payment = None
        si = MagicMock()
        si.name = "SINV-TEST-0002"
        si.company = "Test Co"
        with patch(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            return_value=pe,
        ), patch.object(invoicing, "_resolve_paid_to_account", return_value=None):
            invoicing._create_payment_for_si(si, settings)
        self.assertEqual(pe.reference_no, "EXISTING-REF")
        self.assertEqual(pe.reference_date, "2026-01-01")
