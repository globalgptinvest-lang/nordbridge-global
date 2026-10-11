-- NordBridge CRM verification. Run inside a transaction; rollback preserves existing data.
BEGIN;
DO $$
DECLARE cid uuid; oid uuid; contact_id uuid; msg_id uuid; dup_count int;
BEGIN
 INSERT INTO companies(legal_name,domain,country,registration_number)
 VALUES ('CRM Test Company','crm-test.invalid','DK','CRM-TEST-001') RETURNING id INTO cid;
 INSERT INTO opportunities(company_id,stream,service,external_ref,stage)
 VALUES(cid,'TENDER','Tender support','CRM-TEST-OPP','NEW') RETURNING id INTO oid;
 INSERT INTO contacts(company_id,email,verified_source)
 VALUES(cid,'crm-test@crm-test.invalid','internal test') RETURNING id INTO contact_id;
 INSERT INTO correspondence(opportunity_id,contact_id,provider,provider_message_id,direction,status)
 VALUES(oid,contact_id,'test-provider','CRM-TEST-MESSAGE','OUT','SENT') RETURNING id INTO msg_id;
 INSERT INTO action_log(workflow,opportunity_id,action,outcome,provider_message_id)
 VALUES('CRM_TEST',oid,'TEST_INSERT','OK','CRM-TEST-MESSAGE');
 SELECT count(*) INTO dup_count FROM correspondence WHERE provider='test-provider' AND provider_message_id='CRM-TEST-MESSAGE';
 IF dup_count <> 1 THEN RAISE EXCEPTION 'Correspondence idempotency failed'; END IF;
 BEGIN
   INSERT INTO correspondence(opportunity_id,contact_id,provider,provider_message_id,direction,status)
   VALUES(oid,contact_id,'test-provider','CRM-TEST-MESSAGE','OUT','SENT');
   RAISE EXCEPTION 'Duplicate message unexpectedly accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
   INSERT INTO companies(legal_name,domain) VALUES ('Duplicate','crm-test.invalid');
   RAISE EXCEPTION 'Duplicate domain unexpectedly accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 RAISE NOTICE 'CRM test passed: company, opportunity, contact, correspondence, action log and duplicate constraints';
END $$;
ROLLBACK;
