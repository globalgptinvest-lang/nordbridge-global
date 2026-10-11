# NordBridge CRM foundation (not deployed)

This folder contains a PostgreSQL schema for a shared company registry, distinct opportunities per service/stream, verified contacts, provider-confirmed correspondence, and append-only action logging.

## Required deployment steps
1. Provision private PostgreSQL and secure backups. Do not place credentials in GitHub or website client code.
2. Run schema.sql in a privileged migration session.
3. Configure least-privilege API credentials, row-level security / segregated access for Zhikal, and data retention policies.
4. In n8n: search companies by normalized domain and registry number; check contacts, correspondence, Gmail Sent/Inbox/Drafts/Spam, opt-outs and bounces BEFORE any outreach.
5. Use transactional upsert for company and opportunity, write action_log for all attempts and errors. Record SENT only after a provider-confirmed message ID. Handle retry idempotency with a stable per-opportunity contact/action key.
6. Keep contracts, fees, payments and confidential opportunity details behind manual approval and access control.
7. Validate migration, deduplication, concurrent workflows, backups and permission boundaries before production activation.

**Status:** Schema source only. No database, scheduler, mail sender or live CRM has been deployed by this commit.
