import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('monitor',Path(__file__).with_name('monitor.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BackupStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=dt.datetime(2026,10,26,6,tzinfo=dt.timezone.utc).timestamp()
    def tearDown(self):self.temp.cleanup()
    def report(self,statuses,age=1,name='20261026T050000000000Z'):
        p=self.root/name;p.mkdir()
        stamp=dt.datetime.fromtimestamp(self.now-age*3600,dt.timezone.utc).isoformat()
        (p/'result.json').write_text(json.dumps({'time_utc':stamp,'postgres':[{'restore':{'status':s}} for s in statuses]}))
    def test_no_completed_backup_is_unhealthy(self):self.assertFalse(m.backup_status(self.root,self.now)['healthy'])
    def test_both_instances_must_restore(self):
        self.report(['WORKING','FAILED'])
        self.assertEqual(m.backup_status(self.root,self.now)['reason'],'restore_test_failed')
    def test_a_single_restored_instance_is_insufficient(self):
        self.report(['WORKING']);self.assertFalse(m.backup_status(self.root,self.now)['healthy'])
    def test_old_verified_backup_cannot_mask_new_failure(self):
        self.report(['WORKING','WORKING'],name='20261025T050000000000Z')
        self.report(['FAILED','WORKING'])
        self.assertFalse(m.backup_status(self.root,self.now)['healthy'])
    def test_stale_backup_is_unhealthy(self):
        self.report(['WORKING','WORKING'],age=27)
        self.assertEqual(m.backup_status(self.root,self.now)['reason'],'backup_stale')
    def test_verified_recent_backup_is_healthy(self):
        self.report(['WORKING','WORKING']);self.assertTrue(m.backup_status(self.root,self.now)['healthy'])
    def test_invalid_report_is_unhealthy(self):
        p=self.root/'bad';p.mkdir();(p/'result.json').write_text('broken')
        self.assertFalse(m.backup_status(self.root,self.now)['healthy'])

if __name__=='__main__':unittest.main()
