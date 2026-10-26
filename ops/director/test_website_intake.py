import ast
from pathlib import Path
import unittest

# Load the pure evidence boundary without requiring a database or production secrets.
source=Path(__file__).with_name('director.py')
tree=ast.parse(source.read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='website_evidence')
namespace={}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
evidence=namespace['website_evidence']

class WebsiteIntakeBoundaryTests(unittest.TestCase):
    def row(self,**changes):
        row={'lead_id':'WEB-abcdefghijklmnop','company':'Example company','email':'buyer@example.org',
             'source_page':'/free-tender-fit-check.html','privacy_consent':True,'status':'NEW'}
        row.update(changes);return row
    def test_no_consent_never_enters_sales_pipeline(self):
        self.assertIsNone(evidence(self.row(privacy_consent=False)))
        self.assertIsNone(evidence(self.row(privacy_consent='true')))
    def test_synthetic_records_are_excluded_from_live_pipeline(self):
        self.assertIsNone(evidence(self.row(status='INTERNAL_TEST')))
        self.assertIsNone(evidence(self.row(company='NordBridge INTERNAL SYNTHETIC TEST')))
    def test_test_mode_accepts_only_owner_synthetic_records(self):
        self.assertIsNone(evidence(self.row(),True))
        row=self.row(company='NordBridge INTERNAL SYNTHETIC TEST',email='info@nordbridge-global.com',status='INTERNAL_TEST')
        item=evidence(row,True);self.assertTrue(item['synthetic']);self.assertEqual(item['business_stream'],'TEST')
    def test_financing_is_separate_and_never_becomes_zhikal(self):
        self.assertEqual(evidence(self.row(source_page='/business-financing.html'))['business_stream'],'FINANCING')
        self.assertEqual(evidence(self.row(source_page='/buyer-request.html'))['business_stream'],'NORDBRIDGE')
    def test_enquiry_is_not_a_paid_or_qualified_customer(self):
        item=evidence(self.row());self.assertFalse(item['paid_client']);self.assertFalse(item['fit_verified']);self.assertEqual(item['external_sent'],0)
    def test_source_path_cannot_be_an_external_url(self):
        for path in ['https://attacker.example','//attacker.example','']:
            self.assertIsNone(evidence(self.row(source_page=path)))

if __name__=='__main__':unittest.main()
