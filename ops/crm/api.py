"""Private NordBridge CRM API; localhost-only by default. No mail or external send code."""
import os
import re
import secrets
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="NordBridge private CRM", docs_url=None, redoc_url=None, openapi_url=None)
AGENTS = frozenset("analysis supervisor tenders financing crm security contractors marketing products website independent_audit payments fulfillment legal sales".split())
TABLES = frozenset(("Deals", "Counterparties", "Activity Log", "Global Listings", "Website Leads", "Billing & Payments", "AI Office Bridge Queue"))
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,120}$")

def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=5)

def require_auth(authorization: str | None = Header(None)):
    expected = os.getenv("CRM_API_TOKEN", "")
    received = (authorization or "")
    if (not expected or len(expected) < 32 or not received.startswith("Bearer ")
            or not secrets.compare_digest(received[7:], expected)):
        raise HTTPException(401, "unauthorized")

def require_website_auth(authorization: str | None = Header(None)):
    received = (authorization or "")
    if not received.startswith("Bearer "):
        raise HTTPException(401, "unauthorized")
    token=received[7:]
    for key,scope in (("CRM_WEBSITE_INGEST_TOKEN","production"),("CRM_API_TOKEN","production"),("CRM_WEBSITE_TEST_TOKEN","test")):
        expected=os.getenv(key, "")
        if len(expected)>=32 and secrets.compare_digest(token,expected):
            return scope
    raise HTTPException(401, "unauthorized")

class JobIn(BaseModel):
    job_id: str = Field(min_length=8, max_length=120)
    agent: str
    task_summary: str = Field(min_length=10, max_length=4200)
    source_channel: Literal["GMAIL", "WHATSAPP", "CHATGPT", "VPS", "SYSTEM"] = "SYSTEM"
    source_message_id: str | None = Field(default=None, max_length=240)
    deal_record_id: str | None = Field(default=None, max_length=120)
    source_fingerprint: str | None = Field(default=None, max_length=240)
    no_external_send: Literal[True] = True

class FinishIn(BaseModel):
    claim_token: str = Field(min_length=10, max_length=120)
    status: Literal["DONE", "ERROR", "BLOCKED"]
    agent_response: str | None = Field(default=None, max_length=12000)
    response_status: Literal["READY_FOR_REVIEW", "NEEDS_OWNER", "ERROR", "DRAFT_ONLY"] = "READY_FOR_REVIEW"
    error_summary: str | None = Field(default=None, max_length=1000)

class WebsiteLeadIn(BaseModel):
    lead_id: str = Field(min_length=16, max_length=132)
    company: str = Field(min_length=1, max_length=180)
    email: str = Field(min_length=5, max_length=255)
    country: str = Field(default="", max_length=100)
    source_form: str = Field(default="", max_length=100)
    service: str = Field(default="", max_length=180)
    source_page: str = Field(min_length=2, max_length=250)
    privacy_consent: Literal[True]

@app.get("/health")
def health():
    # Publicly safe, no DB credentials, no customer records.
    try:
        with db() as cx:
            row = cx.execute("SELECT 1 AS ready").fetchone()
        return {"ready": row["ready"] == 1}
    except Exception:
        raise HTTPException(503, "unavailable")

@app.post("/v1/jobs", dependencies=[Depends(require_auth)])
def queue(job: JobIn):
    if not JOB_ID_RE.fullmatch(job.job_id) or job.agent not in AGENTS:
        raise HTTPException(422, "invalid agent or job ID")
    with db() as cx:
        found = cx.execute("""
           INSERT INTO bridge_jobs(job_id, agent, task_summary, source_channel, source_message_id,
                              deal_record_id, source_fingerprint)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING job_id
        """, (job.job_id, job.agent, job.task_summary, job.source_channel,
              job.source_message_id, job.deal_record_id, job.source_fingerprint)).fetchone()
        if not found:
            existing = cx.execute("""
                SELECT job_id FROM bridge_jobs WHERE job_id=%s OR source_fingerprint=%s LIMIT 1
            """, (job.job_id, job.source_fingerprint)).fetchone()
            return {"job_id": existing["job_id"] if existing else job.job_id, "created": False}
    return {"job_id": job.job_id, "created": True}

@app.get("/v1/jobs", dependencies=[Depends(require_auth)])
def list_jobs(status: Literal["QUEUED","CLAIMED","RUNNING","DONE","ERROR","BLOCKED","CANCELLED"] | None = None,
              limit: int = Query(20, ge=1, le=100)):
    sql = "SELECT job_id,direction,status,agent,task_summary,agent_response,response_status,error_summary,source_channel,source_message_id,deal_record_id,source_fingerprint,created_at,updated_at FROM bridge_jobs"
    with db() as cx:
        rows = cx.execute(sql + (" WHERE status=%s" if status else "") + " ORDER BY created_at DESC LIMIT %s",
                          ((status, limit) if status else (limit,))).fetchall()
    return {"jobs": rows}

@app.post("/v1/jobs/claim", dependencies=[Depends(require_auth)])
def claim():
    # Server-side transaction lock ensures only one worker owns a job.
    token = secrets.token_urlsafe(32)
    with db() as cx:
        # Give up cleanly after three timed-out attempts; never retry forever.
        cx.execute("""
          UPDATE bridge_jobs SET status='ERROR', response_status='ERROR',
            error_summary='Claim expired after maximum three attempts',updated_at=now()
          WHERE status='CLAIMED' AND claim_expires<now() AND attempts>=3
        """)
        row = cx.execute("""
          WITH selected AS (
             SELECT job_id FROM bridge_jobs
             WHERE status='QUEUED' OR (status='CLAIMED' AND claim_expires<now() AND attempts<3)
             ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
          ) UPDATE bridge_jobs AS j SET status='CLAIMED', claim_token=%s,
             claim_expires=now()+interval '20 minutes', attempts=j.attempts+1, updated_at=now()
          FROM selected WHERE j.job_id=selected.job_id
          RETURNING j.job_id,j.agent,j.task_summary,j.source_channel,j.source_message_id,j.claim_token
        """, (token,)).fetchone()
    return {"job": row}

@app.post("/v1/jobs/{job_id}/finish", dependencies=[Depends(require_auth)])
def finish(job_id: str, value: FinishIn):
    if not JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(400, "invalid job ID")
    if value.status == "DONE" and not (value.agent_response or "").strip():
        raise HTTPException(422, "empty agent answer")
    with db() as cx:
        row = cx.execute("""
          UPDATE bridge_jobs SET status=%s, agent_response=%s, response_status=%s,
            error_summary=%s, claim_token=NULL, claim_expires=NULL, updated_at=now()
          WHERE job_id=%s AND claim_token=%s AND status='CLAIMED'
            AND claim_expires>now() RETURNING job_id,status
        """, (value.status, value.agent_response, value.response_status,
              value.error_summary, job_id, value.claim_token)).fetchone()
    if not row:
        raise HTTPException(409, "claim invalid or expired")
    return row

@app.get("/v1/records/{table_name}", dependencies=[Depends(require_auth)])
def records(table_name: str, limit: int = Query(50, ge=1, le=200), after: str = ""):
    if table_name not in TABLES:
        raise HTTPException(404, "unknown table")
    with db() as cx:
        rows=cx.execute("""SELECT source_record_id,source_fields,imported_at
                            FROM crm_records WHERE source_table=%s AND source_record_id>%s
                            ORDER BY source_record_id LIMIT %s""",(table_name,after,limit)).fetchall()
    return {"records":rows, "next": rows[-1]["source_record_id"] if len(rows)==limit else None}

@app.post("/v1/website-leads")
def website_lead(value: WebsiteLeadIn, scope: str = Depends(require_website_auth)):
    if scope=='test' and not (value.lead_id.startswith('WEB-STAGING-') and
        value.company=='NordBridge INTERNAL SYNTHETIC TEST' and
        value.email.lower()=='info@nordbridge-global.com' and value.source_page=='/internal-test'):
        raise HTTPException(403, "test credential restricted to synthetic owner records")
    if not re.fullmatch(r"WEB-[A-Za-z0-9_-]{12,128}", value.lead_id):
        raise HTTPException(422, "invalid lead ID")
    email=value.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,24}",email) or not value.source_page.startswith("/") or value.source_page.startswith("//"):
        raise HTTPException(422, "invalid source or email")
    with db() as cx:
        row=cx.execute("""
          INSERT INTO website_leads(lead_id,company,email,country,source_form,service,source_page,privacy_consent,email_domain,status)
          VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s)
          ON CONFLICT(lead_id) DO NOTHING RETURNING lead_id
        """,(value.lead_id,value.company.strip(),email,value.country,value.source_form,
             value.service,value.source_page,email.split('@')[-1], 'INTERNAL_TEST' if scope=='test' else 'NEW')).fetchone()
    return {"lead_id":value.lead_id,"created":bool(row)}
