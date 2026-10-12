# NordBridge — GitHub-first CRM and AI rollout

## What is implemented in this branch
- `scripts/nordbridge_intake.py`: read FormSubmit notifications from the NordBridge Gmail account using Gmail OAuth refresh-token credentials, list existing Airtable Activity Log message IDs across all pages, create only missing intake records, and classify each lead conservatively.
- `.github/workflows/nordbridge-crm-intake.yml`: manual and three-hourly runs, single-run concurrency, minimal GitHub permissions.
- No changes to public GitHub Pages, FormSubmit, domain DNS, mail DNS, or current Google Ads.
- No automatic marketing emails, signatures, financial commitments, or disclosure of tender identities.
- No raw customer emails, names or message bodies in public GitHub Actions logs. Airtable receives classification and Gmail message ID; authorized staff inspect details in Gmail.

## Secrets — add under GitHub > Settings > Secrets and variables > Actions
1. `NB_GMAIL_CLIENT_ID`: Google OAuth client ID for authorized NordBridge mailbox.
2. `NB_GMAIL_CLIENT_SECRET`: matching OAuth client secret.
3. `NB_GMAIL_REFRESH_TOKEN`: OAuth refresh token granted Gmail read-only scope (`https://www.googleapis.com/auth/gmail.readonly`) for the account receiving `info@nordbridge-global.com`.
4. `NB_AIRTABLE_PAT`: Airtable PAT limited to base `appydbFU5sRHKbxdV` with `data.records:read` and `data.records:write`.

Never post tokens in chat, issues, PRs or commits. Do not copy Gmail connector tokens into GitHub.

## Activation and verification
1. Merge PR after review.
2. Configure secrets using the GitHub interface.
3. Run `NordBridge CRM intake` manually in Actions.
4. Check the workflow output and Airtable Activity Log table `tbl0KdkZtYVMtxqks`.
5. Run again: expected newly created record count is 0 for already-imported Gmail IDs.
6. Submit a controlled test through the live form; verify its arrival in Gmail and its record after the next run.
7. Only then rely on scheduled intake. Scheduled GitHub runs may be delayed or skipped.

## AI scope
The initial triage is deterministic and does not call an external AI API. Future AI enrichment should be optional and enabled only after reviewing data privacy, cost caps, input minimization, prompt-injection handling, and quality checks. It must not automatically email, quote prices, sign agreements or release protected tenders.

## Limitations
- The existing Airtable base has Deals, Counterparties and Activity Log but no dedicated Leads table. This first phase records intake in Activity Log only.
- The Gmail account receiving the FormSubmit emails must be the account authorized by the OAuth refresh token.
- Historical test submissions are logged for deduplication, not counted as paying leads.
- Airtable API plan limits apply; monitor quota.
- A full autonomous sales engine requires further approved stages for lead qualification, pipeline tracking, draft generation and explicit human approval for binding commitments.
