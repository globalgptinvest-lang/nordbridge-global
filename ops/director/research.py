"""Bounded official-source research. No external messages, bids or commercial promises."""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import math
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid

UK='https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages'
GRANTS='https://api.grants.gov/v1/api/search2'
MAX_BYTES=5*1024*1024
SERVICE_TERMS=('bid writing','bid-writing','tender writing','tender preparation',
               'procurement consultancy','procurement support','grant writing',
               'grant application support','funding application support')
SUPPLY_TERMS=('logistic','freight','warehouse','customs','industrial','manufactur',
              'steel','hydraulic','welding','cargo','transport','engineering','machinery')

class Plain(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden:self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def text(value,limit=4000):
    p=Plain();p.feed(value if isinstance(value,str) else '')
    return ' '.join(' '.join(p.parts).split())[:limit]

def moment(value):
    try:
        d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return d.astimezone(dt.timezone.utc) if d.tzinfo else None
    except (TypeError,ValueError,AttributeError):return None

def value(obj):
    if not isinstance(obj,dict):return None
    amount=obj.get('amount');currency=obj.get('currency')
    if isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<0:return None
    if not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency):return None
    return {'amount':amount,'currency':currency}

def normalize_uk(raw,now):
    if not isinstance(raw,dict):return None,'invalid_record'
    identifier=raw.get('id','')
    if not isinstance(identifier,str) or not re.fullmatch(r'\d{6}-20\d{2}',identifier):return None,'invalid_notice_id'
    tender=raw.get('tender') or {}
    if not isinstance(tender,dict):return None,'invalid_tender'
    title=text(tender.get('title'),300)
    if not title:return None,'missing_title'
    description=text(tender.get('description'),10000)
    classification=tender.get('classification') or {};period=tender.get('tenderPeriod') or {}
    cpv=classification.get('id') if isinstance(classification,dict) else None
    buyer=raw.get('buyer') or {};awards=raw.get('awards') or [];parties=raw.get('parties') or []
    return {'id':identifier,'ocid':raw.get('ocid'),'title':title,'description':description,
        'buyer':text(buyer.get('name'),240) if isinstance(buyer,dict) else '',
        'url':'https://www.find-tender.service.gov.uk/Notice/'+identifier,
        'status':tender.get('status'),'tag':raw.get('tag',[]) if isinstance(raw.get('tag',[]),list) else [],'deadline':period.get('endDate') if isinstance(period,dict) else None,
        'value':value(tender.get('value')),'cpv':str(cpv or ''),'awards':awards if isinstance(awards,list) else [],
        'parties':parties if isinstance(parties,list) else [],'checked_at':now.isoformat()},None

def is_current_tender(row,now):
    if 'tender' not in row.get('tag',[]) or row.get('status')!='active':return False,'not_active_tender'
    end=moment(row.get('deadline'))
    if not end:return False,'deadline_not_verified'
    if end<=now:return False,'closed'
    return True,None

def need_signal(row,now):
    ok,reason=is_current_tender(row,now)
    if not ok:return None,reason
    s=(row['title']+' '+row['description']).casefold()
    found=[term for term in SERVICE_TERMS if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',s)]
    if row.get('cpv')=='79418000':found.append('CPV 79418000 procurement consultancy')
    if not found:return None,'outside_document_support_scope'
    if not row.get('buyer'):return None,'buyer_missing'
    return {**row,'matched_need':found,'qualification':'EXPLICIT_PUBLIC_PROCUREMENT_NEED_REVIEW_REQUIRED',
            'fit_verified':False,'paid_client':False},None

def suppliers(row):
    s=(row['title']+' '+row['description']).casefold()
    relevant=any(re.search(r'(?<!\w)'+re.escape(term),s) for term in SUPPLY_TERMS) or row.get('cpv','').startswith(('34','42','44','45','60','63','71'))
    if not relevant:return []
    parties={p.get('id'):p for p in row.get('parties',[]) if isinstance(p,dict) and p.get('id')}
    result=[]
    for award in row.get('awards',[]):
        if not isinstance(award,dict) or award.get('status') not in ('active',):continue
        for supplier in award.get('suppliers',[]):
            if not isinstance(supplier,dict):continue
            name=text(supplier.get('name'),240)
            if not name:continue
            party=parties.get(supplier.get('id'),supplier);identity=party.get('identifier') or {}
            if not isinstance(identity,dict):identity={}
            scheme=identity.get('scheme');number=identity.get('id')
            key=scheme+':'+str(number) if isinstance(scheme,str) and number else row['url']+':'+str(supplier.get('id') or name)
            result.append({'identity_key':key,'name':name,'identifier':identity,
                'award_id':award.get('id'),'award_date':award.get('date'),'award_total_value':value(award.get('value')),
                'source_notice':row['url'],'contract_title':row['title'],'buyer':row['buyer'],
                'checked_at':row['checked_at'],'capacity_verified':False,'contact_verified':False,
                'note':'Named supplier in an official award; not a promise of present capacity or eligibility.'})
    return result

def grant_hit(row,now):
    if not isinstance(row,dict):return None,'invalid_record'
    identifier=str(row.get('id',''))
    if not identifier.isdigit():return None,'invalid_id'
    if str(row.get('oppStatus','')).lower()!='posted':return None,'not_posted'
    raw=row.get('closeDate')
    try:deadline=dt.datetime.strptime(raw,'%m/%d/%Y').date()
    except (TypeError,ValueError):return None,'deadline_not_verified'
    # The source returns a calendar date without timezone: exclude the closing day conservatively.
    if deadline<=now.date():return None,'closed_or_closing_today'
    title=text(row.get('title'),350)
    if not title:return None,'missing_title'
    return {'id':identifier,'title':title,'agency':text(row.get('agencyName'),240),
            'number':row.get('number'),'deadline_date':deadline.isoformat(),
            'deadline_timezone':'NOT VERIFIED','status':'posted','checked_at':now.isoformat(),
            'url':'https://www.grants.gov/search-results-detail/'+identifier,
            'record_kind':'FUNDING_PROGRAMME_NOT_BORROWER','award_value':None,
            'foreign_applicant_eligibility':'NOT VERIFIED','company_financing_need_eur_100k':'NOT VERIFIED'},None

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def fetch(url,payload=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,
        headers={'User-Agent':'NordBridgeOfficialSourceResearch/1.0','Accept':'application/json','Content-Type':'application/json'})
    with opener.open(req,timeout=22) as response:
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise RuntimeError('source_response_limit')
        return json.loads(raw)

def cache(key,loader):
    import director as d
    from psycopg.types.json import Jsonb
    with d.db() as c:
        row=c.execute('SELECT payload FROM director.research_cache WHERE key=%s AND expires>now()',(key,)).fetchone()
    if row:return row['payload']
    payload=loader()
    with d.db() as c:
        c.execute("INSERT INTO director.research_cache(key,payload,expires) VALUES(%s,%s,now()+interval '55 minutes') ON CONFLICT(key) DO UPDATE SET payload=EXCLUDED.payload,expires=EXCLUDED.expires",(key,Jsonb(payload)))
    return payload

def uk(stage,now):
    def load():
        params=urllib.parse.urlencode({'stages':stage,'updatedFrom':(now-dt.timedelta(days=14)).strftime('%Y-%m-%dT00:00:00'),'limit':100})
        body=fetch(UK+'?'+params);rows=body.get('releases')
        if not isinstance(rows,list):raise RuntimeError('uk_schema_changed')
        found=[];rejected={}
        for raw in rows:
            row,reason=normalize_uk(raw,now)
            if row:found.append(row)
            else:rejected[reason]=rejected.get(reason,0)+1
        return {'rows':found,'scanned':len(rows),'normalization_rejected':rejected,
                'has_more':bool((body.get('links') or {}).get('next')),'checked_at':now.isoformat()}
    return cache('uk-'+stage,load)

def grants(now):
    def load():
        body=fetch(GRANTS,{'rows':20,'keyword':'international','oppStatuses':'posted'})
        if body.get('errorcode')!=0 or not isinstance(body.get('data'),dict):raise RuntimeError('grants_schema_or_api_error')
        data=body['data'];hits=data.get('oppHits')
        if not isinstance(hits,list):raise RuntimeError('grants_hits_missing')
        rows=[];rejected={}
        for hit in hits:
            row,reason=grant_hit(hit,now)
            if row:rows.append(row)
            else:rejected[reason]=rejected.get(reason,0)+1
        # Discard API session token and other unused response fields.
        return {'rows':rows,'scanned':len(hits),'rejected':rejected,'total_hits':data.get('hitCount'),'checked_at':now.isoformat()}
    return cache('grants-international-posted',load)

def save(c,table,stream,key,source,evidence,stage,next_action):
    import director as d
    from psycopg.types.json import Jsonb
    if table not in ('leads','companies','contractors','opportunities','proposals'):raise ValueError('invalid_entity')
    fp='RESEARCH-'+hashlib.sha256(key.encode()).hexdigest()
    row=c.execute(f'''INSERT INTO director.{table}(id,stream,fingerprint,source,stage,next_action,data)
        VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(stream,fingerprint) DO NOTHING RETURNING id''',
        (uuid.uuid4(),stream,fp,source,stage,next_action,Jsonb({'source_evidence':evidence}))).fetchone()
    if row:return str(row['id']),True
    row=c.execute(f"UPDATE director.{table} SET data=jsonb_set(data,'{{source_evidence}}',%s),updated_at=now() WHERE stream=%s AND fingerprint=%s RETURNING id",(Jsonb(evidence),stream,fp)).fetchone()
    return str(row['id']),False

def scan(job):
    import director as d
    role=job['role'];stream=job['stream'];now=dt.datetime.now(dt.timezone.utc)
    if stream=='TEST':return {'status':'BLOCKED','reason':'Live research requires an explicit business stream; synthetic tests use parser fixtures.'}
    if stream=='ZHIKAL':return {'status':'BLOCKED','reason':'Public tender and grant feeds do not prove private Zhikal purchases; no cross-stream import.'}
    if role in ('leads','contractors') and stream!='NORDBRIDGE':return {'status':'BLOCKED','reason':'NordBridge public procurement research is separate from financing demand.'}
    if role=='financing' and stream!='FINANCING':return {'status':'BLOCKED','reason':'Use the FINANCING stream for funding programme research.'}
    try:source=grants(now) if role=='financing' else uk('tender' if role=='leads' else 'award',now)
    except Exception as exc:return {'status':'BLOCKED','reason':'Official source unavailable','error_type':type(exc).__name__,'external_sent':0}
    rejected={};items=[]
    if role=='leads':
        for row in source['rows']:
            item,reason=need_signal(row,now)
            if item:items.append(item)
            else:rejected[reason]=rejected.get(reason,0)+1
    elif role=='contractors':
        for row in source['rows']:items.extend(suppliers(row))
    else:
        for row in source['rows']:
            if row['deadline_date']>now.date().isoformat():items.append(row)
            else:rejected['closed_or_closing_today']=rejected.get('closed_or_closing_today',0)+1
    unique={}
    for item in items:unique.setdefault(item.get('identity_key') or item['id'],item)
    records=list(unique.values())[:30];inserted=0;ids=[]
    with d.db() as c:
        for item in records:
            if role=='leads':
                key='uk-need:'+item['id'];url=item['url']
                company,_=save(c,'companies',stream,'buyer:'+item['buyer'].casefold(),url,{'name':item['buyer'],'notice':url,'legal_entity_verification':'NOT VERIFIED'},'NEEDS_REVIEW','Verify official buyer identity and bidding eligibility')
                item['company_id']=company
                ident,new=save(c,'leads',stream,key,url,item,'PUBLIC_NEED_REVIEW','Verify scope, deadline, eligibility and permitted contact before proposal')
            elif role=='contractors':
                key='supplier:'+item['identity_key'];url=item['source_notice']
                ident,new=save(c,'contractors',stream,key,url,item,'AWARD_EVIDENCE_REVIEW','Verify legal identity, current capacity, eligibility and official contact')
            else:
                key='grants:'+item['id'];url=item['url']
                ident,new=save(c,'opportunities',stream,key,url,item,'FUNDING_PROGRAMME_REVIEW','Check full programme, foreign applicant eligibility and amount; identify genuine company need separately')
            inserted+=int(new);ids.append(ident)
    return {'status':'DONE','role':role,'stream':stream,'source':'Grants.gov public API' if role=='financing' else 'UK Find a Tender public OCDS API',
        'source_checked_at':source['checked_at'],'source_records_scanned':source['scanned'],'matched_candidates':len(unique),
        'records_saved':len(ids),'inserted':inserted,'existing_refreshed':len(ids)-inserted,
        'not_saved_due_to_batch_limit':max(0,len(unique)-len(ids)),'rejected':rejected or source.get('rejected',{}),
        'coverage_limited':source.get('has_more',False),'record_ids':ids[:5],
        'scope':'Funding programmes, not company financing needs >= EUR100k' if role=='financing' else 'Evidence candidates requiring human qualification; not confirmed paid clients',
        'qualified_clients':0,'external_sent':0,'paid_api_spend':0}
