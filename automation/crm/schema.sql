-- NordBridge CRM foundation: PostgreSQL 15+
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS companies (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), legal_name text NOT NULL,
 domain text, country text, registration_number text, website text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT domain_lower CHECK (domain IS NULL OR domain = lower(domain))
);
CREATE UNIQUE INDEX IF NOT EXISTS companies_domain_unique ON companies(domain) WHERE domain IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS companies_reg_unique ON companies(country,registration_number) WHERE registration_number IS NOT NULL;
CREATE TABLE IF NOT EXISTS opportunities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
 stream text NOT NULL CHECK (stream IN ('TENDER','FINANCING','ZHIKAL','MATCHING','INTRODUCTION','BUSINESS','OTHER')),
 service text NOT NULL, external_ref text, source_url text, evidence text,
 amount_eur numeric(18,2), amount_is_estimate boolean NOT NULL DEFAULT true,
 lead_score integer CHECK (lead_score BETWEEN 0 AND 100),
 stage text NOT NULL DEFAULT 'NEW', next_action text, next_action_at timestamptz,
 owner text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS opportunities_external_ref_unique ON opportunities(stream,external_ref) WHERE external_ref IS NOT NULL;
CREATE TABLE IF NOT EXISTS contacts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES companies(id),
 email text NOT NULL, full_name text, role text, verified_source text, opted_out boolean NOT NULL DEFAULT false,
 bounced_permanently boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(company_id,email), CHECK(email=lower(email))
);
CREATE TABLE IF NOT EXISTS correspondence (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), opportunity_id uuid NOT NULL REFERENCES opportunities(id),
 contact_id uuid REFERENCES contacts(id), provider text NOT NULL, provider_message_id text,
 provider_thread_id text, direction text NOT NULL CHECK(direction IN ('IN','OUT')),
 status text NOT NULL CHECK(status IN ('DRAFT','ATTEMPTED','SENT','BOUNCED','REPLIED','FAILED')),
 subject text, occurred_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(provider,provider_message_id)
);
CREATE TABLE IF NOT EXISTS action_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, occurred_at timestamptz NOT NULL DEFAULT now(),
 workflow text NOT NULL, opportunity_id uuid REFERENCES opportunities(id),
 action text NOT NULL, outcome text NOT NULL, evidence_url text, provider_message_id text,
 error text, next_action text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS action_log_opportunity_idx ON action_log(opportunity_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS opportunities_next_action_idx ON opportunities(next_action_at);
-- Protect ZHIKAL records with separate DB roles/RLS in production before connecting agents.
