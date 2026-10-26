import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('monitor_intake',Path(__file__).with_name('monitor.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class IntakeMonitorTests(unittest.TestCase):
    def checks(self,website,crm):
        return m.intake_status(lambda url:website if '/api/intake-status' in url else crm)
    def test_both_endpoints_must_be_ready(self):
        self.assertTrue(self.checks({'ready':True},{'ready':True})['healthy'])
        self.assertFalse(self.checks({'ready':True},{'ready':False})['healthy'])
        self.assertFalse(self.checks({'ready':False},{'ready':True})['healthy'])
    def test_production_cannot_be_marked_healthy_in_fixture_mode(self):
        self.assertFalse(self.checks({'ready':True,'testing':True},{'ready':True})['healthy'])
    def test_non_json_shape_cannot_be_healthy(self):
        self.assertFalse(self.checks([],{ 'ready':True})['healthy'])
    def test_transport_failure_is_recorded_without_details_or_secret(self):
        def broken(url):raise TimeoutError('potentially sensitive request details')
        result=m.intake_status(broken)
        self.assertFalse(result['healthy']);self.assertEqual(result['error_type'],'TimeoutError')
        self.assertNotIn('potentially sensitive',str(result))
if __name__=='__main__':unittest.main()
