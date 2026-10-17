# NordBridge website → private CRM integration

## Current state (2026-10-11)
- Production site is static HTML. `submit-tender.html` and `free-tender-fit-check.html` POST to FormSubmit. Preserve that delivery path until the CRM path is proven.
- Private CRM Lovable project `68cf64fc-a406-462c-be5b-c9886a838408` has a lead-ingestion endpoint (`/api/public/leads`) and traffic module, but is unpublished. Do not publish its admin interface.
- GA4 measurement ID is `G-KW3F5F27BX`. Existing analytics tracking is not evidence of verified conversions.

## Safe rollout checklist
1. Provision a **server-side-only**, independently secured CRM ingestion URL (private admin UI remains unpublished). Confirm TLS, CORS policy, endpoint reachability and server authentication. Never put an automation token or secret into public HTML/JS.
2. Confirm exact request schema, privacy notice, consent handling, rate limits, spam protection, PII retention, RLS and audit logging. Restrict Zhikal access separately.
3. Add a backend relay or verified webhook from the existing FormSubmit workflow. Keep FormSubmit email notifications intact; do not send personal data twice without a documented legal basis.
4. Dry-run with synthetic contact data. Verify a single submission reaches CRM exactly once and repeated retries are idempotent. Check failure handling and no public data leakage.
5. Only then enable production forwarding with monitoring and rollback. Verify a real owner-authorized test submission, confirmation email and CRM status.
6. Track `qualified_lead` or `application_confirmed` only on server-confirmed acceptance; do not equate button clicks/page views with conversions. Avoid duplicate GA4/Ads conversion imports.
7. Connect GA4, Google Ads, and Search Console with least-privilege owner OAuth; do not claim connection before live verification.

## Deployment restrictions
No modification to live forms, FormSubmit destination, paid ad budget, or public CRM publication until end-to-end verification. Site must remain available.
