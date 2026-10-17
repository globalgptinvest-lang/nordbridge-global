"""Offline regression tests. All records are synthetic; no web or email calls."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation import public_monitor as monitor
from automation import contact_guard as guard

NOW = dt.datetime(2026, 10, 17, 9, 0, tzinfo=dt.timezone.utc)

class SourceTests(unittest.TestCase):
    def test_rotating_queries_cover_all_sectors(self):
        all_topics = []
        for hour in (0, 1, 2):
            all_topics += [label for label, _ in monitor.rotating_ted_queries(NOW.replace(hour=hour))]
        self.assertEqual(len(all_topics), len(set(all_topics)))
        self.assertEqual(len(all_topics), len(monitor.TOPICS))
        self.assertGreaterEqual(len(all_topics), 9)

    def test_ted_notice_is_source_only_no_guessed_value(self):
        x = monitor.parse_ted_notice({
            "publication-number": "012345-2026", "notice-title": {"eng": "Solar installation"},
            "buyer-name": {"eng": "Synthetic utility"}})
        self.assertEqual(x["id"], "TED:012345-2026")
        self.assertIsNone(x["value"])
        self.assertIsNone(x["deadline"])
        self.assertIsNone(monitor.parse_ted_notice({"notice-title": "Missing ID"}))

    def test_uk_notice_respects_closing_date(self):
        original = {
            "id": "123456-2026", "tag": ["tender"], "buyer": {"name": "Synthetic council"},
            "tender": {"title": "Bridge design", "status": "active",
                       "tenderPeriod": {"endDate": "2026-10-25T10:00:00Z"},
                       "value": {"amount": 120000, "currency": "GBP"}}
        }
        current = monitor.parse_uk_release(original, NOW)
        self.assertEqual(current["source"], "UK Find a Tender")
        self.assertEqual(current["value"], 120000)
        self.assertEqual(current["currency"], "GBP")  # must NOT present as EUR
        self.assertEqual(current["url"], "https://www.find-tender.service.gov.uk/Notice/123456-2026")
        expired = dict(original, tender={**original["tender"], "tenderPeriod": {"endDate": "2026-10-01T10:00:00Z"}})
        self.assertIsNone(monitor.parse_uk_release(expired, NOW))
        awarded = dict(original, tender={**original["tender"], "status": "complete"})
        self.assertIsNone(monitor.parse_uk_release(awarded, NOW))

    def test_uk_fetch_uses_public_documented_endpoint(self):
        with patch.object(monitor, "http_json", return_value={"releases": []}) as http:
            self.assertEqual(monitor.query_uk(NOW), [])
            request = http.call_args.args[0]
            self.assertIn("stages=tender", request)
            self.assertIn("updatedFrom=", request)
            self.assertTrue(request.startswith(monitor.UK_API))

    def test_first_scan_baselines_and_next_scan_deduplicates(self):
        first = monitor.rank_notice(monitor.parse_ted_notice({"publication-number": "012345-2026", "notice-title": "Bridge engineering"}))
        second = monitor.rank_notice(monitor.parse_uk_release({
            "id": "123456-2026", "tag": ["tender"], "tender": {"title": "Renewable energy", "status": "active"}
        }, NOW))
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            with patch.object(monitor, "query_ted", return_value=[first]), patch.object(monitor, "query_uk", return_value=[]):
                code = monitor.run_monitor(p / "report.json", p / "state.json", NOW, website_checker=lambda: {"ok": True})
                self.assertEqual(code, 0)
                a = json.loads((p / "report.json").read_text())
                self.assertTrue(a["first_run"])
                self.assertEqual(a["new"], [])
            with patch.object(monitor, "query_ted", return_value=[first]), patch.object(monitor, "query_uk", return_value=[second]):
                code = monitor.run_monitor(p / "report.json", p / "state.json", NOW, website_checker=lambda: {"ok": True})
                self.assertEqual(code, 0)
                b = json.loads((p / "report.json").read_text())
                self.assertEqual(len(b["new"]), 1)
                self.assertEqual(b["new"][0]["id"], "UK:123456-2026")
                self.assertEqual(b["outreach_sent"], 0)

    def test_legacy_ted_cache_ids_are_migrated(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            state.write_text(json.dumps({"seen": ["123456-2026", "UK:111111-2026"]}))
            ids, first = monitor.read_state(state)
            self.assertFalse(first)
            self.assertIn("TED:123456-2026", ids)
            self.assertIn("UK:111111-2026", ids)
            self.assertNotIn("123456-2026", ids)

    def test_source_partial_vs_total_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            with patch.object(monitor, "query_ted", side_effect=RuntimeError("429")), patch.object(monitor, "query_uk", return_value=[]):
                self.assertEqual(monitor.run_monitor(p / "report.json", p / "state.json", NOW, website_checker=lambda: {"ok": True}), 0)
                r = json.loads((p / "report.json").read_text())
                self.assertTrue(r["partial"])
            with patch.object(monitor, "query_ted", side_effect=RuntimeError("429")), patch.object(monitor, "query_uk", side_effect=RuntimeError("503")):
                self.assertEqual(monitor.run_monitor(p / "report.json", p / "state.json", NOW, website_checker=lambda: {"ok": True}), 1)

class LeadTests(unittest.TestCase):
    def valid(self):
        return {"company": "Synthetic Solar", "email": "hello@example.org",
                "evidence_url": "https://example.org/current-tender",
                "evidence_date": "2026-10-17", "need": "Bid review", "offer_type": "tender",
                "tender_ref": "RFQ-123"}

    def test_review_is_never_automatic_delivery(self):
        self.assertEqual(guard.assess(self.valid(), set(), set(), set(), set(), NOW.date())["status"], "READY_FOR_HUMAN_REVIEW")

    def test_hard_bounce_and_duplicates_are_blocked(self):
        data = self.valid()
        x = guard.assess(data, set(), {"hello@example.org"}, set(), set(), NOW.date())
        self.assertEqual(x["status"], "HOLD")
        self.assertIn("permanent_bounce", x["reasons"])
        payload = {"prospects": [data, data]}
        self.assertIn("duplicate_opportunity", guard.evaluate(payload, NOW.date())[1]["reasons"])

    def test_finance_needs_verified_minimum(self):
        data = {**self.valid(), "offer_type": "finance", "finance_eur": 80000}
        x = guard.assess(data, set(), set(), set(), set(), NOW.date())
        self.assertIn("financing_amount_not_verified_100k_eur", x["reasons"])

    def test_untrusted_url_and_old_evidence(self):
        data = {**self.valid(), "evidence_url": "http://example.org", "evidence_date": "2025-10-17"}
        x = guard.assess(data, set(), set(), set(), set(), NOW.date())
        self.assertIn("official_source_or_https_evidence_missing", x["reasons"])
        self.assertIn("source_not_current", x["reasons"])

if __name__ == "__main__":
    unittest.main()
