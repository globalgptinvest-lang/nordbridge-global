import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('research',Path(__file__).with_name('research.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
NOW=dt.datetime(2026,10,26,6,tzinfo=dt.timezone.utc)

class ResearchParserTests(unittest.TestCase):
    def tender(self,**changes):
        row={'id':'000001-2026','title':'Grant writing support','description':'Support preparation of applications.',
             'buyer':'Example Public Body','status':'active','tag':['tender'],'deadline':'2026-10-28T12:00:00Z','cpv':''}
        row.update(changes);return row
    def test_explicit_need_is_candidate_not_customer(self):
        item,reason=r.need_signal(self.tender(),NOW)
        self.assertIsNone(reason);self.assertFalse(item['paid_client']);self.assertFalse(item['fit_verified'])
    def test_closed_and_unknown_deadline_cannot_qualify(self):
        for value in ['2026-10-25T12:00:00Z',None,'2026-10-28T12:00:00']:
            self.assertIsNone(r.need_signal(self.tender(deadline=value),NOW)[0])
    def test_generic_tender_is_not_a_client_need(self):
        self.assertEqual(r.need_signal(self.tender(title='Purchase of vehicles'),NOW)[1],'outside_document_support_scope')
    def test_script_content_is_not_business_evidence(self):
        row=self.tender(title='Equipment',description='<script>bid writing</script>Supply goods')
        normalized,_=r.normalize_uk({'id':'000001-2026','tender':row},NOW)
        self.assertNotIn('bid writing',normalized['description'])
    def test_cancelled_notice_is_rejected(self):
        self.assertIsNone(r.need_signal(self.tender(status='cancelled'),NOW)[0])
    def test_cpv_can_provide_explicit_service_category(self):
        self.assertIsNotNone(r.need_signal(self.tender(title='Consultancy',cpv='79418000'),NOW)[0])
    def test_budget_must_keep_source_currency(self):
        self.assertEqual(r.value({'amount':120000,'currency':'GBP'}),{'amount':120000,'currency':'GBP'})
        self.assertIsNone(r.value({'amount':True,'currency':'EUR'}))
        self.assertIsNone(r.value({'amount':'120000','currency':'EUR'}))
        self.assertIsNone(r.value({'amount':float('nan'),'currency':'EUR'}))
        self.assertIsNone(r.value({'amount':float('inf'),'currency':'EUR'}))
    def test_supplier_requires_actual_active_award(self):
        row={'title':'Industrial equipment','description':'','cpv':'','buyer':'Buyer','url':'https://www.find-tender.service.gov.uk/Notice/000001-2026','checked_at':NOW.isoformat(),'parties':[],'awards':[]}
        self.assertEqual(r.suppliers(row),[])
        row['awards']=[{'status':'active','suppliers':[{'id':'s1','name':'Example Manufacturer'}]}]
        item=r.suppliers(row)[0];self.assertFalse(item['capacity_verified']);self.assertFalse(item['contact_verified'])
        row['awards'][0]['status']='cancelled';self.assertEqual(r.suppliers(row),[])
    def test_supplier_registration_identity_is_preferred(self):
        row={'title':'Freight','description':'','cpv':'','buyer':'Buyer','url':'https://www.find-tender.service.gov.uk/Notice/000001-2026','checked_at':NOW.isoformat(),'parties':[{'id':'s1','identifier':{'scheme':'GB-COH','id':'12345678'}}],'awards':[{'status':'active','suppliers':[{'id':'s1','name':'Example Freight'}]}]}
        self.assertEqual(r.suppliers(row)[0]['identity_key'],'GB-COH:12345678')
    def test_funding_programme_is_not_financing_client(self):
        item,reason=r.grant_hit({'id':'123456','title':'International programme','oppStatus':'posted','closeDate':'11/30/2026'},NOW)
        self.assertIsNone(reason);self.assertEqual(item['record_kind'],'FUNDING_PROGRAMME_NOT_BORROWER')
        self.assertEqual(item['company_financing_need_eur_100k'],'NOT VERIFIED')
    def test_grants_missing_closed_and_forecasted_are_excluded(self):
        for status,date in [('posted',''),('posted','10/26/2026'),('closed','12/31/2026'),('forecasted','12/31/2026')]:
            self.assertIsNone(r.grant_hit({'id':'123','title':'Programme','oppStatus':status,'closeDate':date},NOW)[0])
    def test_invalid_notice_identifier_cannot_build_source_link(self):
        self.assertEqual(r.normalize_uk({'id':'../../../private','tender':{'title':'Test'}},NOW)[1],'invalid_notice_id')
    def test_bounded_batches_eventually_process_unseen_candidates(self):
        records=[{'identity_key':str(i)} for i in range(61)];known=set();seen=[]
        for _ in range(3):
            batch=r.prioritize(records,'contractors',known)
            seen.extend(x['identity_key'] for x in batch)
            known.update(r.fingerprint(r.record_key('contractors',x)) for x in batch)
        self.assertEqual(len(set(seen)),61)
    def test_old_records_refresh_when_no_new_candidates_exist(self):
        records=[{'id':str(i)} for i in range(40)]
        known={r.fingerprint(r.record_key('leads',x)) for x in records}
        self.assertEqual(r.prioritize(records,'leads',known),records[:30])
    def test_first_batch_is_bounded_and_preserves_source_order(self):
        records=[{'id':str(i)} for i in range(100)]
        self.assertEqual(r.prioritize(records,'financing',set()),records[:30])
    def test_lot_additional_cpv_is_not_ignored(self):
        raw={'id':'000001-2026','tag':['tender'],'buyer':{'name':'Buyer'},'tender':{'title':'Consultancy','status':'active','tenderPeriod':{'endDate':'2026-11-09T15:00:00Z'},'items':[{'additionalClassifications':[{'scheme':'CPV','id':'79418000'}]}]}}
        row,_=r.normalize_uk(raw,NOW)
        self.assertIsNotNone(r.need_signal(row,NOW)[0])
    def test_new_cancellation_does_not_revive_old_tender(self):
        records=[{'id':'000001-2026','date':'2026-10-20T00:00:00Z','tender':{'title':'Bid writing','status':'active'}},{'id':'000002-2026','date':'2026-10-25T00:00:00Z','tender':{'title':'Bid writing','status':'cancelled'}}]
        row,_=r.latest_process(records,NOW)
        self.assertEqual(row['status'],'cancelled')
        self.assertIsNone(r.need_signal(row,NOW)[0])

if __name__=='__main__':unittest.main()
