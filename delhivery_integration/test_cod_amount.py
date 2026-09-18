import frappe
from frappe.tests import UnitTestCase

from delhivery_integration.api import _resolve_cod


def _dn(mode="COD", total=1390.40, paid=None, cod=None):
    d = frappe._dict(delhivery_payment_mode=mode, grand_total=total)
    if paid is not None:
        d.custom_paid_amount = paid
    if cod is not None:
        d.custom_cod_amount = cod
    return d


class TestResolveCod(UnitTestCase):
    """CO1-I64 — only the pending COD amount goes to Delhivery."""

    def test_partial_payment_sends_only_pending_cod(self):
        # The ticket's own example (DN-26-01572): 1390.40 = 998.00 paid + 392.40 COD.
        self.assertEqual(_resolve_cod(_dn(paid=998.00, cod=392.40)), ("COD", "392.4"))

    def test_fully_unpaid_sends_full_amount(self):
        self.assertEqual(_resolve_cod(_dn(paid=0, cod=1390.40)), ("COD", "1390.4"))

    def test_split_fields_absent_falls_back_to_grand_total(self):
        # Legacy / manually-created DN with no split recorded: behaviour unchanged.
        self.assertEqual(_resolve_cod(_dn()), ("COD", "1390.4"))

    def test_fully_paid_is_sent_as_prepaid_with_zero_cod(self):
        self.assertEqual(_resolve_cod(_dn(paid=1390.40, cod=0)), ("Prepaid", "0"))

    def test_pending_derived_from_paid_when_cod_field_blank(self):
        self.assertEqual(_resolve_cod(_dn(paid=998.00, cod=0)), ("COD", "392.4"))

    def test_prepaid_mode_unchanged(self):
        self.assertEqual(_resolve_cod(_dn(mode="Prepaid", paid=0, cod=1390.40)), ("Prepaid", "0"))
        self.assertEqual(_resolve_cod(_dn(mode=None)), ("Prepaid", "0"))

    def test_cod_never_exceeds_order_total(self):
        self.assertEqual(_resolve_cod(_dn(total=500, paid=0, cod=900)), ("COD", "500.0"))

    def test_float_noise_is_rounded(self):
        self.assertEqual(_resolve_cod(_dn(total=1585.20, paid=805.75, cod=779.4500000001)), ("COD", "779.45"))
