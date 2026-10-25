"""Root systemd health wrapper. Credentials stay in containers; notifications owner-only."""
import datetime
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import sqlite3

STATE=Path('/var/lib/nordbridge-director-monitor.json')

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
    fail=0 if healthy else old.get('consecutive_failures',0)+1
    out={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'healthy':healthy,
         'simulated':simulated,'consecutive_failures':fail,'restarts':restarts}
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
    if (fail>=2 or simulated) and not old.get('alerted',False):
        out['alert_sent']=notify('NordBridge Director monitoring: '+('CONTROLLED TEST FAILURE — no service stopped.' if simulated else 'critical health failure; bounded recovery attempted.'))
        out['alerted']=out['alert_sent']
    elif healthy and old.get('alerted'):
        out['recovery_alert_sent']=notify('NordBridge Director monitoring: health recovered; database and scheduler responded.')
        out['alerted']=False
    else:out['alerted']=old.get('alerted',False)
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(out));tmp.chmod(0o600);tmp.replace(STATE)
    cmd(['logger','-t','nordbridge-director',json.dumps({k:v for k,v in out.items() if k!='restarts'})])
    print(json.dumps(out))
    return out

if __name__=='__main__':main()
