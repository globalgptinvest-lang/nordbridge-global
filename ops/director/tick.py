"""Runs in the Director container. Atomic five-minute health and bounded schedules."""
import datetime
import json
import director as d
from psycopg.types.json import Jsonb

def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    specs=[('crm',now.strftime('crm-%Y%m%d%H'),'Count CRM records and report factual state.'),
           ('tenders',now.strftime('ted-%Y%m%d%H'),'Import official TED candidates; do not qualify as paid clients.')]
    if now.hour==6:
        specs.append(('website',now.strftime('website-%Y%m%d'),'Check website public HTTP endpoints.'))
    created=[]
    with d.db() as c:
        # A transaction-scoped lock prevents parallel tick processes.
        if not c.execute('SELECT pg_try_advisory_xact_lock(71887925) ok').fetchone()['ok']:
            return {'overlap':'SKIPPED'}
        pending=c.execute("SELECT count(*) n FROM director.jobs WHERE status IN('QUEUED','RUNNING','WAITING')").fetchone()['n']
        if pending>20:return {'backpressure':'SKIPPED','pending':pending}
        for role,slot,task in specs:
            first=c.execute('INSERT INTO director.schedule_runs(slot,role) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING slot',(slot,role)).fetchone()
            if not first:continue
            c.execute('''INSERT INTO director.jobs(id,role,stream,task,fingerprint)
              VALUES(%s,%s,'NORDBRIDGE',%s,%s) ON CONFLICT DO NOTHING''',
              (d.uuid.uuid4(),role,task,'SCHEDULE-'+slot));created.append(slot)
        c.execute('INSERT INTO director.audit(kind,data) VALUES(%s,%s)',('scheduler_tick',Jsonb({'created':created,'time_utc':now.isoformat()})))
    return {'db':'PASS','created':created,'time_utc':now.isoformat()}

if __name__=='__main__':print(json.dumps(main()))
