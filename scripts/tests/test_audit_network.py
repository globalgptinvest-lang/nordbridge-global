"""Offline regression tests for uptime audit transports.

All HTTP responses and browser pages are synthetic. No site, forms, CRM, email,
payments or external API is contacted by these tests.
"""
import asyncio
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
import unittest

from scripts import audit_network


class Response:
    def __init__(self, code=200, body=b"<urlset/>"):
        self.status, self.body = code, body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class RetryTransportTests(unittest.TestCase):
    def test_ssl_eof_is_retried_then_successful(self):
        outcomes = [URLError("SSL UNEXPECTED_EOF_WHILE_READING"), Response(body=b"ok")]
        calls, pauses = [], []

        def opener(url, timeout):
            calls.append(url)
            nxt = outcomes.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

        data = audit_network.read_bytes("https://example.org/sitemap.xml",
                                        opener=opener, sleep=pauses.append)
        self.assertEqual(data, b"ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(pauses, [2])

    def test_retries_503_then_succeeds(self):
        attempts, sleeps = [], []

        def opener(url, timeout):
            attempts.append(url)
            if len(attempts) < 3:
                raise HTTPError(url, 503, "Maintenance", {}, None)
            return Response()

        self.assertEqual(audit_network.read_bytes(
            "https://example.org", opener=opener, sleep=sleeps.append), b"<urlset/>")
        self.assertEqual(sleeps, [2, 4])
        self.assertEqual(len(attempts), 3)

    def test_nonretryable_404_is_not_hidden(self):
        calls = []
        def opener(url, timeout):
            calls.append(url)
            raise HTTPError(url, 404, "Not Found", {}, None)
        with self.assertRaises(HTTPError):
            audit_network.read_bytes("https://example.org/missing",
                                     opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_persistent_ssl_error_remains_failure(self):
        calls = []
        def opener(url, timeout):
            calls.append(url)
            raise URLError("SSL closed")
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            audit_network.read_bytes("https://example.org", opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 3)


class BrowserNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_connection_reset(self):
        calls, sleeps = [], []

        class Page:
            async def goto(self, url, **kwargs):
                calls.append(url)
                if len(calls) == 1:
                    raise Exception("Page.goto: net::ERR_CONNECTION_RESET")
                return Response()

        async def sleeper(delay):
            sleeps.append(delay)

        result = await audit_network.goto_with_retry(Page(), "https://example.org", sleep=sleeper)
        self.assertEqual(result.status, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [2])

    async def test_5xx_transient_retried(self):
        calls = []

        class Page:
            async def goto(self, url, **kwargs):
                calls.append(url)
                return Response(503 if len(calls) == 1 else 200)

        async def sleeper(_): pass
        result = await audit_network.goto_with_retry(Page(), "https://example.org", sleep=sleeper)
        self.assertEqual(result.status, 200)
        self.assertEqual(len(calls), 2)

    async def test_permanent_404_not_hidden(self):
        class Page:
            async def goto(self, url, **kwargs):
                return Response(404)
        result = await audit_network.goto_with_retry(Page(), "https://example.org")
        self.assertEqual(result.status, 404)

    async def test_unexpected_browser_bug_not_retried(self):
        calls = []
        class Page:
            async def goto(self, url, **kwargs):
                calls.append(url)
                raise RuntimeError("unexpected JavaScript issue")
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            await audit_network.goto_with_retry(Page(), "https://example.org")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
