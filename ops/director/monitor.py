"""Root systemd health wrapper. Credentials stay in containers; notifications owner-only."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import sqlite3
import shutil
import socket
import ssl

STATE=Path('/var/lib/nordbridge-director-monitor.json')

def backup_status(base=Path('/var/backups/nordbridge-maintenance'),now=None):
    now=time.time() if now is None else now
    try:
        paths=sorted(base.glob('*/result.json'))
        if not paths:return {'healthy':False,'reason':'no_completed_backup'}
        data=json.loads(paths[-1].read_text())
        stamp=datetime.datetime.fromisoformat(data['time_utc']).timestamp()
        age=round((now-stamp)/3600,2)
        good=len(data.get('postgres',[]))==2 and all(x.get('restore',{}).get('status')=='WORKING' for x in data['postgres'])
        return {'healthy':good and 0<=age<=26,'age_hours':age,'backup_directory':data.get('backup_directory'),
                'reason':None if good and 0<=age<=26 else 'restore_test_failed' if not good else 'backup_stale'}
    except (OSError,ValueError,KeyError,TypeError):return {'healthy':False,'reason':'backup_report_unreadable'}

def cmd(args,timeout=30):
    return subprocess.run(args,text=True,capture_output=True,timeout=timeout)

def notify(text):
    # Reuses the existing authenticated owner's Telegram destination only.
    code="import os,json,urllib.request; t=os.getenv('TG_TOKEN'); c=os.getenv('TG_CHAT_ID'); assert t and c; r=urllib.request.urlopen(urllib.request.Request('https://api.telegram.org/bot'+t+'/sendMessage',data=json.dumps({'chat_id':c,'text':"+repr(text)+"}).encode(),headers={'Content-Type':'application/json'}),timeout=15); assert r.status==200"
    return cmd(['docker','exec','nordbridge-office-core-1','python3','-c',code]).returncode==0

def main():
    lock=open('/run/nordbridge-director-monitor.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return {'overlap':'SKIPPED'}
    old=json.loads(STATE.read_text()) if STATE.exists() else {}
    simulated='--simulate-failure' in sys.argv
    r=cmd(['docker','exec','nordbridge-director-director-1','python3','/app/tick.py'])
    healthy=r.returncode==0 and not simulated
    now=time.time();restarts=[x for x in old.get('restarts',[]) if x>now-3600]
    mem={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if len(x.split())>=2 and x.split()[1].isdigit()}
    resources={'disk_free_gib':round(shutil.disk_usage('/').free/1024**3,2),
               'memory_available_mib':round(mem.get('MemAvailable',0)/1024),
               'load_1m':os.getloadavg()[0]}
    resource_ok=resources['disk_free_gib']>=2 and resources['memory_available_mib']>=300 and resources['load_1m']<24
    backup=backup_status(now=now);backup_ok=backup['healthy']
    ssl_checks=old.get('ssl_checks',{})
    ssl_check_at=old.get('ssl_check_at',0)
    if now-ssl_check_at>3600:
        ssl_checks={}
        for host in ['office.57.129.182.200.sslip.io','nordbridge-global.com']:
            try:
                with socket.create_connection((host,443),timeout=5) as s:
                    with ssl.create_default_context().wrap_socket(s,server_hostname=host) as secured:
                        cert=secured.getpeercert();days=int((ssl.cert_time_to_seconds(cert['notAfter'])-now)/86400)
                        ssl_checks[host]={'verified':True,'days_remaining':days}
            except Exception as e:ssl_checks[host]={'verified':False,'error':type(e).__name__}
        ssl_check_at=now
    tls_ok=bool(ssl_checks) and all(x.get('verified') and x.get('days_remaining',0)>14 for x in ssl_checks.values())
    fail=0 if healthy else old.get('consecutive_failures',0)+1
    out={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'healthy':healthy,
         'simulated':simulated,'consecutive_failures':fail,'restarts':restarts}
    out.update(resources=resources,resource_ok=resource_ok,ssl_checks=ssl_checks,ssl_check_at=ssl_check_at,
               daily_report_date=old.get('daily_report_date'),daily_report_test_date=old.get('daily_report_test_date'))
    out['backup']=backup
    out['healthy']=healthy and resource_ok and tls_ok and backup_ok
    mail=Path('/opt/nordbridge-mail-agent/state.db')
    if healthy and mail.is_file():
        try:
            with sqlite3.connect('file:'+str(mail)+'?mode=ro',uri=True,timeout=5) as c:
                summary={'classification_counts':dict(c.execute('SELECT category,count(*) FROM messages GROUP BY category').fetchall()),
                         'last_processed':c.execute('SELECT max(processed_at) FROM messages').fetchone()[0],
                         'source':'Existing authorized corporate mailbox review agent','mode':'REVIEW_ONLY',
                         'message_level_crm_sync':False}
            code="import director as d,json,sys; d.audit('mail_review_snapshot',json.load(sys.stdin))"
            p=subprocess.run(['docker','exec','-i','nordbridge-director-director-1','python3','-c',code],input=json.dumps(summary),text=True,capture_output=True,timeout=20)
            out['mail_snapshot_saved']=p.returncode==0
        except Exception:out['mail_snapshot_saved']=False
    if healthy:
        try:out['schedule']=json.loads(r.stdout)
        except:out['schedule']='INVALID_RESPONSE';out['healthy']=False
    if not healthy and not simulated and len(restarts)<3:
        restart=cmd(['docker','restart','nordbridge-director-director-1'],timeout=50)
        if restart.returncode==0:out['restarts'].append(now)
    if (fail>=2 or simulated or not resource_ok or not tls_ok or not backup_ok) and not old.get('alerted',False):
        out['alert_sent']=notify('NordBridge Director monitoring: '+('CONTROLLED TEST FAILURE — no service stopped.' if simulated else 'critical check failed; inspect the private monitoring state and recorded recovery attempts.'))
        out['alerted']=out['alert_sent']
    elif healthy and resource_ok and tls_ok and backup_ok and old.get('alerted'):
        out['recovery_alert_sent']=notify('NordBridge Director monitoring: health recovered; database and scheduler responded.')
        out['alerted']=False
    else:out['alerted']=old.get('alerted',False)
    day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    daily_test='--send-daily-test' in sys.argv
    if healthy and ((daily_test and old.get('daily_report_test_date')!=day) or (datetime.datetime.now(datetime.timezone.utc).hour==8 and old.get('daily_report_date')!=day)):
        code="import director as d,json; c=d.db(); print(json.dumps({'jobs':c.execute(\"SELECT status,count(*) n FROM director.jobs WHERE created_at>now()-interval '24 hours' GROUP BY status\").fetchall(),'tender_candidates':c.execute('SELECT count(*) n FROM director.tenders').fetchone()['n'],'product_drafts':c.execute(\"SELECT count(*) n FROM director.proposals WHERE stage='DRAFT_OWNER_REVIEW' AND data->>'kind'='product_research'\").fetchone()['n'],'lead_candidates':c.execute(\"SELECT count(*) n FROM director.leads WHERE stream='NORDBRIDGE'\").fetchone()['n'],'contractor_candidates':c.execute(\"SELECT count(*) n FROM director.contractors WHERE stream='NORDBRIDGE'\").fetchone()['n'],'funding_programmes':c.execute(\"SELECT count(*) n FROM director.opportunities WHERE stream='FINANCING' AND data->'source_evidence'->>'record_kind'='FUNDING_PROGRAMME_NOT_BORROWER'\").fetchone()['n']},default=str)); c.close()"
        report=cmd(['docker','exec','nordbridge-director-director-1','python3','-c',code])
        if report.returncode==0:
            data=json.loads(report.stdout)
            text=('NORDBRIDGE — '+('ТЕСТ ЩОДЕННОГО ЗВІТУ' if daily_test else 'ЩОДЕННИЙ ЗВІТ')+' '+day+' UTC\n'
                  +'Завдання: '+json.dumps(data['jobs'],ensure_ascii=False)+'\n'
                  +'Неперевірені тендерні можливості в CRM: '+str(data['tender_candidates'])+'; це не підтверджені платні клієнти.\n'
                  +'Потреби на кваліфікацію: '+str(data['lead_candidates'])+'; постачальники для перевірки: '+str(data['contractor_candidates'])+'; програми фінансування: '+str(data['funding_programmes'])+'\n'
                  +'Продуктові чернетки на погодження: '+str(data['product_drafts'])+'\n'
                  +'Директор не має інструментів зовнішнього відправлення. Надходження коштів: NOT VERIFIED.\n'
                  +'Джерела UK/Grants.gov підключені. Потрібна перевірка відповідності. Грантові програми не є компаніями, які шукають фінансування; приватний потік Zhikal окремий.\n'
                  +'https://office.57.129.182.200.sslip.io\nhttps://nordbridge-global.com')
            out['daily_report_sent']=notify(text)
            if out['daily_report_sent']:
                if daily_test:out['daily_report_test_date']=day
                else:out['daily_report_date']=day
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(out));tmp.chmod(0o600);tmp.replace(STATE)
    cmd(['logger','-t','nordbridge-director',json.dumps({k:v for k,v in out.items() if k!='restarts'})])
    print(json.dumps(out))
    return out

if __name__=='__main__':main()
