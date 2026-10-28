# NordBridge lead intake — production status and operating checks

## Current production route (verified 2026-10-28)

The public site is served through the Vercel project connected to `globalgptinvest-lang/nordbridge-global`. Website forms enhance to Vercel `/api/lead` when `/api/intake-status` reports readiness. The public readiness endpoint checks the configured CRM server's `/health` response before marking the server route ready; it exposes only a boolean and the public Turnstile site key.

Production Vercel configuration selects the NordBridge CRM API on the VPS, with PostgreSQL intake storage. The API URL and token are private Vercel environment variables; never copy tokens into GitHub, reports, or this document. If the CRM health check fails, readiness is false and the existing FormSubmit fallback remains available. When CRM server mode is configured but a lead write fails, the API does not silently duplicate the lead into Airtable.

The configured direct CRM host `crm.57.129.182.200.sslip.io` returned a healthy public `/health` response during review. The branded aliases `crm.nordbridge-global.com` and `office.nordbridge-global.com` did not respond in external checks; they are not required by the current configured website route and remain unverified. Confirm DNS and TLS with the infrastructure operator before using those aliases.

## Routine checks

1. Check `https://nordbridge-global.com/api/intake-status`; expect HTTP 200 and `ready: true` while Turnstile and the configured CRM health endpoint are available.
2. Check the configured CRM endpoint's `/health`; this is a read-only database connectivity check, not proof that authenticated intake writes or notifications work.
3. Review Vercel function logs for `/api/lead` failures without exporting customer data or secrets.
4. For an end-to-end lead delivery test, use an explicitly approved synthetic submission and verify one record in the private CRM. Do not use a real customer's details.
5. Preserve existing mail DNS records (MX, SPF, DKIM, DMARC and DNSSEC) during any domain changes.
6. Keep FormSubmit fallback configured until authenticated writes and customer notification delivery have been verified.

## Form and data safeguards

The API checks origin, consent, Turnstile, required fields, request size, and a honeypot. CRM credentials stay in Vercel environment variables. A configured CRM write failure returns an error rather than creating a second record through another provider. Do not put private leads or contact details into public GitHub Actions artifacts.

The public readiness endpoint does not expose the CRM host, token, or private lead data. It checks only whether the selected provider is configured and healthy.

## Deployment and infrastructure

Website changes land on `main` and deploy through the connected Vercel project. Confirm the Vercel production deployment reaches READY and inspect the public site and readiness endpoint after each deployment.

Changing VPS DNS, TLS, firewall, database, mail routing, or secrets requires access to the infrastructure provider. This repository change does not perform those server-side operations.
