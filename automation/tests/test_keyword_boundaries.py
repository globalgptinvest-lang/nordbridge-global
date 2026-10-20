"""Synthetic regression tests for public procurement keyword triage.

No network, CRM writes, or external communication.
"""
import unittest

from automation import public_monitor as monitor


class KeywordBoundaryTests(unittest.TestCase):
    def rank(self, title):
        return monitor.rank_notice({"title": title, "value": None})

    def test_transport_does_not_imply_seaport(self):
        result = self.rank("Rail transport infrastructure and freight management")
        self.assertIn("transport", result["matched_keywords"])
        self.assertIn("rail", result["matched_keywords"])
        self.assertIn("freight", result["matched_keywords"])
        self.assertNotIn("port", result["matched_keywords"])
        self.assertEqual(result["triage_score"], 65)

    def test_real_port_keyword_still_matches(self):
        result = self.rank("Port services and logistics support")
        self.assertIn("port", result["matched_keywords"])
        self.assertIn("logistic", result["matched_keywords"])

    def test_import_and_portfolio_are_not_port_tenders(self):
        for title in ("Import services", "Portfolio consultancy",
                      "Portable medical equipment", "Rail trail maintenance"):
            with self.subTest(title=title):
                result = self.rank(title)
                self.assertNotIn("port", result["matched_keywords"])
                self.assertNotIn("rail", result["matched_keywords"])

    def test_stemmed_terms_still_match(self):
        result = self.rank("Engineering consultancy and warehouses")
        self.assertIn("engineer", result["matched_keywords"])
        self.assertIn("consult", result["matched_keywords"])
        self.assertIn("warehous", result["matched_keywords"])
        result_uk = self.rank("Логістичне обладнання та інфраструктура")
        self.assertIn("логіст", result_uk["matched_keywords"])
        self.assertIn("обладнан", result_uk["matched_keywords"])

    def test_no_keyword_score_remains_baseline(self):
        result = self.rank("Public information services")
        self.assertEqual(result["triage_score"], 20)
        self.assertEqual(result["matched_keywords"], [])


if __name__ == "__main__":
    unittest.main()
