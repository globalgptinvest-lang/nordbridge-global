"""Synthetic source-level regression checks for the full public QA audit."""
import unittest
from scripts.full_public_audit import sitemap_urls, audit_metadata


class SitewideAuditTests(unittest.TestCase):
    def test_sitemap_deduplication_preserves_homepage(self):
        xml = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://nordbridge-global.com/</loc></url>
          <url><loc>https://www.nordbridge-global.com/contact.html</loc></url>
          <url><loc>https://nordbridge-global.com/contact.html</loc></url>
        </urlset>"""
        self.assertEqual(sitemap_urls(xml), ["/", "/contact.html"])

    def test_external_host_is_rejected(self):
        xml = b"<urlset><url><loc>https://external.example/x</loc></url></urlset>"
        with self.assertRaises(ValueError):
            sitemap_urls(xml)

    def test_canonical_mismatch_is_reported(self):
        result = audit_metadata("/contact.html", {
            "title": "NordBridge Contact", "description": "Contact details",
            "canonical": "https://nordbridge-global.com/contact.html",
            "viewport": True, "lang": "en", "h1_count": 1, "overflow_px": 0})
        codes = {x["code"] for x in result}
        self.assertIn("SEO_CANONICAL_HOST", codes)

    def test_valid_metadata_not_flagged(self):
        result = audit_metadata("/contact.html", {
            "title": "NordBridge Contact", "description": "Contact details",
            "canonical": "https://www.nordbridge-global.com/contact.html",
            "viewport": True, "lang": "en", "h1_count": 1, "overflow_px": 0})
        self.assertEqual(result, [])

    def test_mobile_overflow_reported(self):
        result = audit_metadata("/", {
            "title": "NordBridge", "description": "International consulting",
            "canonical": "https://www.nordbridge-global.com/",
            "viewport": True, "lang": "en", "h1_count": 1, "overflow_px": 29})
        self.assertTrue(any(x["code"]=="MOBILE_OVERFLOW" for x in result))

    def test_unsafe_broken_anchor_reported(self):
        result = audit_metadata("/", {
            "title": "NordBridge", "description": "International consulting",
            "canonical": "https://www.nordbridge-global.com/",
            "viewport": True, "lang": "en", "h1_count": 1, "overflow_px": 0,
            "missing_anchors": ["#unknown-section"]})
        self.assertEqual([x["code"] for x in result], ["BROKEN_ANCHOR"])


    def test_all_sitemap_pages_have_www_canonical_and_language_script(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        xml = (root / "sitemap.xml").read_bytes()
        paths = sitemap_urls(xml)
        self.assertGreaterEqual(len(paths), 30)
        for path in paths:
            filename = "index.html" if path == "/" else path.lstrip("/")
            html = (root / filename).read_text(encoding="utf8")
            expected = "https://www.nordbridge-global.com" + path
            with self.subTest(path=path):
                self.assertIn(expected, html)
                self.assertIn('rel="canonical"', html)
                self.assertIn("i18n.js", html)


if __name__ == "__main__":
    unittest.main()
