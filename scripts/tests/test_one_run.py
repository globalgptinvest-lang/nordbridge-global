"""Synthetic offline checks for one-run operations — no external requests."""
from contextlib import contextmanager
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from automation import nordbridge_one_run as audit


class FakeResponse:
    def __init__(self, content=b"ok", status=200, url="https://www.nordbridge-global.com/"):
        self.content, self.status, self.url = content, status, url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, _=None): return self.content


class ReportSafety(unittest.TestCase):
    def test_secret_or_email_is_never_echoed(self):
        result = audit.sanitized("Bearer abcde password sk_live_abcd1234 user@example.org")
        self.assertNotIn("sk_live_", result)
        self.assertNotIn("abcde", result)
        self.assertNotIn("user@example.org", result)

    def test_repeated_failure_is_not_marked_pass(self):
        attempts = []
        def bad_open(request, timeout):
            attempts.append(request)
            raise URLError("SSL connection dropped")
        with self.assertRaises(RuntimeError):
            audit.public_get("https://example.org", opener=bad_open, wait=lambda _: None)
        self.assertEqual(len(attempts), 3)

    def test_404_does_not_get_retried(self):
        attempts = []
        def bad_open(request, timeout):
            attempts.append(request)
            raise HTTPError("https://example.org", 404, "Missing", {}, None)
        with self.assertRaises(HTTPError):
            audit.public_get("https://example.org", opener=bad_open, wait=lambda _: None)
        self.assertEqual(len(attempts), 1)

    def test_site_and_readiness_need_real_json(self):
        def fake_get(url):
            if url.endswith("/api/intake-status"):
                return b'{"ready": false}', url
            return b"<html><body>NordBridge website</body></html>", (
                "https://www.nordbridge-global.com/" if url == "https://nordbridge-global.com/" else url)
        result = audit.check_public_site(getter=fake_get)
        status = {x["name"]:x["status"] for x in result}
        self.assertEqual(status["Private CRM intake readiness"], "FAIL")
        self.assertEqual(status["Apex HTTPS redirect"], "PASS")
        self.assertEqual(status["Site /"], "PASS")

    def test_current_repo_security_gates(self):
        result = audit.inspect_sources(audit.ROOT)
        names = {r["name"]: r["status"] for r in result}
        self.assertEqual(names["Intake source security gates"], "PASS")
        self.assertEqual(names["Six website forms wired"], "PASS")
        # Published payment links demand account-owner review, never false success.
        self.assertIn(names["Published Stripe payment links"], ("PASS", "REVIEW"))

    def test_no_private_record_in_public_report(self):
        report = {"checked_at": "2026-10-17T12:00:00+00:00",
                  "checks": [audit.outcome("live payments", "REVIEW", "Not verified")]}
        output = audit.markdown(report)
        self.assertIn("No email sent", output)
        self.assertIn("Stripe payments", output)
        self.assertNotIn("status\": \"PAID\"", output)


if __name__ == "__main__":
    unittest.main()
