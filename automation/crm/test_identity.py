import unittest
from identity import normalize_domain, normalize_email, company_identity, outbound_key

class IdentityTests(unittest.TestCase):
    def test_domain(self):
        self.assertEqual(normalize_domain("HTTPS://WWW.Example.COM/contact"), "example.com")
        self.assertEqual(normalize_domain("example.com"), "example.com")
    def test_registry_precedence(self):
        self.assertEqual(company_identity("ABC", "dk", "12 34-56", "other.com"), ("registry", "DK", "123456"))
    def test_email(self):
        self.assertEqual(normalize_email(" PERSON@EXAMPLE.COM "), "person@example.com")
    def test_idempotency(self):
        self.assertEqual(outbound_key("deal1", "A@EXAMPLE.COM", "INTRO"),
                         outbound_key("deal1", "a@example.com", "intro"))
        self.assertNotEqual(outbound_key("deal1", "a@example.com", "intro"),
                            outbound_key("deal2", "a@example.com", "intro"))
    def test_bad_input(self):
        with self.assertRaises(ValueError):
            normalize_email("not-an-email")
        with self.assertRaises(ValueError):
            normalize_domain("invalid")

if __name__ == "__main__":
    unittest.main()
