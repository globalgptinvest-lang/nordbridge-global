#!/usr/bin/env python3
"""Private VPS backups and bounded diagnostics. No sending, billing or cutover."""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request

BASE = Path('/var/backups/nordbridge-maintenance')

class RestoreVerificationError(RuntimeError):
    def __init__(self, phase, exit_code=None, sqlstates=None, reason=None):
        super().__init__('restore_verification_failed')
        self.details={'phase':phase,'exit_code':exit_code,'sqlstates':sqlstates or [],'reason':reason}

def command(argv, timeout=60, stdin=None):
    r = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError('command_failed:' + Path(argv[0]).name)
    return r.stdout.strip()

def private_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    path.chmod(0o600)

def kind(c):
    name=c.get('Name','').lower()
    image=c['Config']['Image'].lower()
    if 'worker' in name: return 'worker'
    return next((x for x in ['postgres','n8n','ollama','redis','qdrant','caddy','crm','core'] if x in name+' '+image),'other')

def db_exec(container, database, sql):
    return command(['docker','exec','-i','-e','NB_AUDIT_DB='+database,container,'sh','-c',
        'exec psql -X -A -t -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" -d "$NB_AUDIT_DB"'], stdin=sql, timeout=120)

def databases(container):
    return json.loads(db_exec(container,'postgres',"SELECT coalesce(json_agg(datname),'[]') FROM pg_database WHERE NOT datistemplate;"))

def schema_counts(container, database):
    return json.loads(db_exec(container,database,"SELECT json_build_object('tables',count(*),'n8n',count(*) FILTER (WHERE table_name='workflow_entity'),'crm',count(*) FILTER (WHERE table_name IN ('leads','companies','contacts','website_leads','opportunities'))) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema');"))

def restore_verify(c, dump, expected):
    tag='nb-verify-'+secrets.token_hex(6)
    user='audit_'+secrets.token_hex(4)
    phase='create_isolated_container'
    try:
        command(['docker','run','-d','--name',tag,'--network','none','--memory','768m','--cpus','1','--pids-limit','128',
            '--tmpfs','/var/lib/postgresql/data:rw,nosuid,size=1g','-e','PGDATA=/var/lib/postgresql/data',
            '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_USER='+user,c['Image']])
        phase='wait_for_database';ready=False
        for _ in range(30):
            # The image's temporary initialization server accepts Unix sockets only.
            # Require TCP so restore cannot race its shutdown/restart transition.
            r=subprocess.run(['docker','exec',tag,'pg_isready','-h','127.0.0.1','-U',user],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
            if r.returncode==0: ready=True; break
            time.sleep(1)
        if not ready: raise RuntimeError('restore_container_not_ready')
        phase='restore_sql'
        with dump.open('rb') as stream:
            r=subprocess.run(['docker','exec','-i',tag,'psql','-h','127.0.0.1','-X','-v','ON_ERROR_STOP=1','-v','VERBOSITY=sqlstate','-v','SHOW_CONTEXT=never','-U',user,'-d','postgres'],
                stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=900)
        if r.returncode:
            codes=re.findall(r'(?:ERROR|FATAL|PANIC):\s+([A-Z0-9]{5})\b',r.stderr or '')
            reason='server_connection_unavailable' if any(x in (r.stderr or '').lower() for x in ['server closed the connection','connection to server was lost','server terminated abnormally','connection to server','no such file or directory']) else 'psql_restore_error'
            raise RestoreVerificationError(phase,r.returncode,codes,reason)
        phase='verify_restored_databases'
        restored=json.loads(command(['docker','exec',tag,'psql','-h','127.0.0.1','-X','-A','-t','-U',user,'-d','postgres','-c',
            "SELECT coalesce(json_agg(datname),'[]') FROM pg_database WHERE NOT datistemplate;"]))
        if not set(expected).issubset(restored): raise RuntimeError('restored_databases_missing')
        phase='verify_restored_application';checks=[]
        for database in expected:
            q=['docker','exec',tag,'psql','-h','127.0.0.1','-X','-A','-t','-U',user,'-d',database,'-c']
            tables=json.loads(command(q+["SELECT json_build_object('director',to_regclass('director.jobs') IS NOT NULL,'n8n',to_regclass('public.workflow_entity') IS NOT NULL);"]))
            if tables['director']:
                counts=json.loads(command(q+["SELECT json_build_object('jobs',(SELECT count(*) FROM director.jobs),'test_results',(SELECT count(*) FROM director.jobs WHERE role='self_test' AND status='DONE'),'test_companies',(SELECT count(*) FROM director.companies WHERE stream='TEST'),'contractors',(SELECT count(*) FROM director.contractors),'lead_candidates',(SELECT count(*) FROM director.leads WHERE stream='NORDBRIDGE'),'lead_briefs',(SELECT count(*) FROM director.proposals WHERE data->'source_evidence'->>'kind'='lead_qualification_brief'),'funding_programmes',(SELECT count(*) FROM director.opportunities WHERE stream='FINANCING' AND data->'source_evidence'->>'record_kind'='FUNDING_PROGRAMME_NOT_BORROWER'),'website_enquiries',(SELECT count(*) FROM public.website_leads),'website_contacts',(SELECT count(*) FROM director.contacts WHERE fingerprint LIKE 'WEBCONTACT:%'),'website_test_drafts',(SELECT count(*) FROM director.proposals WHERE stream='TEST' AND data->>'kind'='website_request_brief' AND length(coalesce(data->'draft'->>'draft',''))>35));"]))
                if counts['test_results']<1 or counts['test_companies']<1:raise RuntimeError('restored_director_test_evidence_missing')
                checks.append({'director_restored':counts})
            if tables['n8n']:
                n=int(command(q+['SELECT count(*) FROM public.workflow_entity;']))
                if n<1:raise RuntimeError('restored_n8n_workflows_missing')
                checks.append({'n8n_workflows_restored':n})
        return {'status':'WORKING','source_databases_present':len(expected),'scope':'logical_restore_database_and_application_evidence','application_checks':checks}
    except RestoreVerificationError:raise
    except Exception as exc:
        reason=str(exc) if isinstance(exc,RuntimeError) and re.fullmatch(r'[a-z_]+(?::[a-z_]+)?',str(exc)) else type(exc).__name__
        raise RestoreVerificationError(phase,reason=reason) from None
    finally:
        subprocess.run(['docker','rm','-f','-v',tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)

def http_probe(c):
    k=kind(c)
    if k not in ['n8n','core','crm','ollama']: return {'status':'NOT TESTED'}
    ips=[n.get('IPAddress') for n in c.get('NetworkSettings',{}).get('Networks',{}).values() if n.get('IPAddress')]
    configured=set(c['Config'].get('ExposedPorts') or {})|set(c.get('NetworkSettings',{}).get('Ports') or {})
    ports=[int(p.split('/')[0]) for p in configured if p.endswith('/tcp') and p.split('/')[0] in ['5678','8000','8080','3000','11434']]
    if k=='ollama' and not ports: ports=[11434]
    if k=='core' and not ports: ports=[8000]
    paths=['/healthz'] if k=='n8n' else ['/api/tags'] if k=='ollama' else ['/health','/healthz','/openapi.json']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    found=[]
    for ip in ips[:2]:
        for port in ports[:2]:
            for path in paths:
                try:
                    with opener.open('http://'+ip+':'+str(port)+path,timeout=3) as response:
                        body=response.read(500000)
                        item={'port':port,'path':path,'http':response.status}
                        try:
                            obj=json.loads(body)
                            if isinstance(obj,dict) and k=='ollama':item['installed_models']=len(obj.get('models',[]))
                            if isinstance(obj,dict) and path=='/openapi.json':item['documented_routes']=sorted(obj.get('paths',{}))[:50]
                        except ValueError:pass
                        found.append(item)
                except Exception:pass
    return {'status':'WORKING' if found else 'NOT VERIFIED','scope':'http_endpoint_only','checks':found}

def run():
    if os.geteuid()!=0: raise RuntimeError('root_required')
    os.umask(0o077)
    lock=open('/run/nordbridge-maintenance.lock','w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if shutil.disk_usage('/').free<4*1024**3: raise RuntimeError('backup_requires_4g_free')
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest=BASE/stamp;dest.mkdir(mode=0o700)
    ids=command(['docker','ps','-aq']).splitlines()
    if not ids: raise RuntimeError('no_containers')
    cs=json.loads(command(['docker','inspect']+ids))
    # Full inspect is retained only in memory; never print Config.Env or dump its values.
    inventory=[{'name':c['Name'].lstrip('/'),'image':c['Config']['Image'],'kind':kind(c),
                'state':c['State']['Status'],'labels':c['Config'].get('Labels',{}),'mounts':c.get('Mounts',[])} for c in cs]
    private_json(dest/'inventory-private.json',inventory)
    report={'time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'backup_directory':str(dest),
            'containers_total':len(cs),'containers_running':sum(c['State']['Running'] for c in cs),
            'postgres':[],'http':[],'changes_to_production':[], 'outgoing_messages':0,'payments_changed':False}
    # Back up all PostgreSQL instances before any database test.
    pgs=[c for c in cs if kind(c)=='postgres']
    dump_map=[]
    for index,c in enumerate(pgs,1):
        if not c['State']['Running']: raise RuntimeError('stopped_postgres_requires_private_recovery_plan')
        dump=dest/('postgres-'+str(index)+'.sql')
        with dump.open('wb') as stream:
            r=subprocess.run(['docker','exec',c['Id'],'sh','-c','exec pg_dumpall -U "${POSTGRES_USER:-postgres}"'],
                stdout=stream,stderr=subprocess.DEVNULL,timeout=1200)
        dump.chmod(0o600)
        if r.returncode or not dump.stat().st_size: raise RuntimeError('postgres_backup_failed')
        dump_map.append((index,c,dump))
    configs=set()
    sqlite_copies=0
    for c in cs:
        labels=c['Config'].get('Labels') or {}
        for value in labels.get('com.docker.compose.project.config_files','').split(','):
            path=Path(value)
            if value and path.is_file():
                configs.add(path)
                for name in ['.env','Caddyfile','Dockerfile']:
                    p=path.parent/name
                    if p.is_file():configs.add(p)
        # Consistent backup for n8n only when a host-visible SQLite database exists.
        if kind(c)=='n8n':
            for mount in c.get('Mounts',[]):
                if mount.get('Type') not in ['bind','volume']:continue
                path=Path(mount['Source'])/'database.sqlite'
                if path.is_file():
                    target=dest/('n8n-sqlite-'+str(sqlite_copies)+'.sqlite')
                    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:src.backup(dst)
                    target.chmod(0o600);sqlite_copies+=1
    for p in [Path('/root/nordbridge-office-agent.json'),Path('/root/nordbridge-smtp.env')]:
        if p.is_file():configs.add(p)
    mailstate=Path('/opt/nordbridge-mail-agent/state.db')
    if mailstate.is_file():
        with sqlite3.connect('file:'+str(mailstate)+'?mode=ro',uri=True) as src, sqlite3.connect(dest/'mail-state.sqlite') as dst:src.backup(dst)
        (dest/'mail-state.sqlite').chmod(0o600)
    for base in [Path('/opt/nordbridge-director'),Path('/opt/nordbridge-office/caddy')]:
        if base.is_dir():
            configs.update(p for p in base.iterdir() if p.is_file() and p.suffix in ['.py','.yaml','.yml','.env','.sh'])
    for p in [Path('/opt/nordbridge-office/caddy/Caddyfile'),Path('/root/nordbridge-director-owner.txt')]:
        if p.is_file():configs.add(p)
    for unit in Path('/etc/systemd/system').glob('nordbridge-director-*'):
        if unit.is_file():configs.add(unit)
    with tarfile.open(dest/'configuration.tar.gz','w:gz') as archive:
        for p in sorted(configs):archive.add(p,arcname=str(p).lstrip('/'),recursive=False)
    (dest/'configuration.tar.gz').chmod(0o600)
    report['configuration_files_backed_up']=len(configs)
    report['sqlite_backups']=sqlite_copies
    hashes={}
    for p in dest.iterdir():
        if p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            hashes[p.name]=h.hexdigest()
    private_json(dest/'checksums.json',hashes)
    for index,c,dump in dump_map:
        dbs=databases(c['Id'])
        item={'index':index,'backup_bytes':dump.stat().st_size,'database_count':len(dbs),'databases':[]}
        for database in dbs:
            try:
                counts=schema_counts(c['Id'],database)
                db_exec(c['Id'],database,"BEGIN; CREATE TEMP TABLE nb_test(id text PRIMARY KEY); INSERT INTO nb_test VALUES ('test') ON CONFLICT DO NOTHING; INSERT INTO nb_test VALUES ('test') ON CONFLICT DO NOTHING; DO $$ BEGIN IF (SELECT count(*) FROM nb_test)<>1 THEN RAISE EXCEPTION 'dedupe'; END IF; END $$; ROLLBACK;")
                result={'schema':counts,'temporary_write_read_dedupe':'WORKING'}
                if counts['n8n']:
                    try:
                        n=db_exec(c['Id'],database,'SELECT json_build_object(\'total\',count(*),\'active\',count(*) FILTER (WHERE active)) FROM workflow_entity;')
                        result['n8n_workflows']=json.loads(n)
                    except Exception:result['n8n_workflows']='NOT VERIFIED'
                item['databases'].append(result)
            except Exception:item['databases'].append({'status':'FAILED'})
        try:item['restore']=restore_verify(c,dump,dbs)
        except RestoreVerificationError as exc:item['restore']={'status':'FAILED','scope':'isolated_restore_test',**exc.details}
        except Exception as exc:item['restore']={'status':'FAILED','scope':'isolated_restore_test','reason':type(exc).__name__}
        report['postgres'].append(item)
    for c in cs:
        if kind(c) in ['n8n','worker','core','crm','ollama']:
            report['http'].append({'kind':kind(c),'result':http_probe(c)})
    active_units=command(['systemctl','list-timers','--all','--no-pager'])
    report['timer_counts']={k:sum(k in line.lower() for line in active_units.splitlines()) for k in ['nordbridge','ted','backup','mail']}
    creds=[]
    for c in cs:
        names={line.partition('=')[0] for line in c['Config'].get('Env',[]) if line.partition('=')[2]}
        creds.append({'kind':kind(c),'configured_variable_categories':{kind_:any(re.search(pattern,n,re.I) for n in names) for kind_,pattern in {
            'mail':'smtp|imap|gmail','whatsapp':'whatsapp|wa_token','ai_external':'openai|anthropic|gemini|ai_gateway','stripe':'stripe','telegram':'telegram|bot_token'}.items()}})
    report['integration_configuration_presence_only']=creds
    report['mail_secret_file_present']=Path('/root/nordbridge-smtp.env').is_file()
    report['crm_form_end_to_end']='NOT VERIFIED'
    private_json(dest/'result.json',report)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    if any(p.get('restore',{}).get('status')!='WORKING' for p in report['postgres']):raise RuntimeError('restore_test_incomplete')
    # Retain the latest 14 verified sets generated by this script. Incomplete sets are never pruned.
    verified=[]
    for folder in BASE.iterdir():
        if not folder.is_dir() or folder.is_symlink() or not re.fullmatch(r'\d{8}T\d{12}Z',folder.name):continue
        try:
            old=json.loads((folder/'result.json').read_text())
            if old.get('backup_directory')==str(folder) and len(old.get('postgres',[]))==2 and all(p.get('restore',{}).get('status')=='WORKING' for p in old['postgres']):verified.append(folder)
        except (OSError,ValueError):pass
    for folder in sorted(verified)[:-14]:shutil.rmtree(folder)

if __name__=='__main__':
    try:run()
    except Exception as exc:
        print(json.dumps({'status':'FAILED','reason':str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__}),flush=True)
        sys.exit(1)
