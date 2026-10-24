"""Synthetic policy regressions; no messages or external requests."""
import datetime as dt
import unittest
from automation.contact_guard import evaluate

class OwnerHoldTests(unittest.TestCase):
    def assess(self, **changes):
        row = dict(company="Example Works", email="sales@example.org",
                   evidence_url="https://example.org/notice", evidence_date="2026-10-24",
                   need="Tender documentation support", offer_type="tender", tender_ref="TEST-1")
        row.update(changes)
        return evaluate({"prospects": [row]}, dt.date(2026, 10, 24))[0]

    def test_bovendia_address_and_subdomain_hold(self):
        for address in ("POST@BOVENDIA.DK", "person@secure.bovendia.dk"):
            result = self.assess(email=address)
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("owner_specific_message_permission_required", result["reasons"])

    def test_bovendia_company_or_source_hold(self):
        for changes in (dict(company="BoVendia"), dict(evidence_url="https://www.bovendia.dk/")):
            self.assertEqual(self.assess(**changes)["status"], "HOLD")

    def test_record_cannot_override_owner_hold(self):
        self.assertEqual(self.assess(company="BoVendia", owner_approved=True)["status"], "HOLD")

    def test_zynthoro_legal_hold(self):
        result = self.assess(company="Zynthoro", email="info@zynthoro.ai")
        self.assertIn("legal_hold_no_investor_outreach", result["reasons"])

    def test_other_qualified_records_still_require_manual_review(self):
        self.assertEqual(self.assess()["status"], "READY_FOR_HUMAN_REVIEW")
