# NordBridge GitHub-first automation
The public website remains on GitHub Pages. These GitHub Actions run periodic checks without changing DNS, forms, customer records, or sending emails.

## Workflows
- Site health check: every 6 hours, validates HTTP 2xx on home, contact and privacy pages.
- Form safety audit: every Monday and when forms.js or its audit workflow changes. Checks syntax and static guardrails.
- Both workflows can be started manually from GitHub > Actions.
- Failures are visible in GitHub Actions logs. Notifications depend on repository notification settings.

## Limitations
GitHub Actions is not a permanent application server or guaranteed exact-time scheduler. These workflows do not ingest or store personal lead data, do not verify FormSubmit delivery, and do not send marketing email. A secure external endpoint is needed for direct form API submissions, webhook receipt and transactional Resend notifications.

## Safety
Keep secrets in GitHub Actions secrets, never commit API keys. No secret is required for the current checks. Preserve Spaceship DNS records for Spacemail, Resend and GitHub Pages. Do not change production forms until an alternative is tested.
