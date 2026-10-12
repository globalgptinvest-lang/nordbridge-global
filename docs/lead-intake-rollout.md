# NordBridge lead intake — staging checklist

Production currently uses GitHub Pages DNS and FormSubmit. Do not switch forms or DNS until Vercel production routing, Resend, Redis, rate limiting and bot protection are tested.

## Required checks

1. Verify Vercel project scope and permissions; verify preview domain and function deployment.
2. Configure secret environment variables only in Vercel, never in GitHub.
3. Deploy API endpoint on a preview branch, validate request size, origin, consent, rate limits, idempotency and retry logic.
4. Send synthetic lead to preview endpoint; confirm durable storage and Resend notification.
5. Verify Resend webhook signature and delivered/bounced statuses; confirm alerting for failures.
6. Validate actual site form fields against API schema; do not replace FormSubmit before end-to-end pass.
7. Verify DNS configuration and preserve existing Spaceship/Spacemail/Resend MX, SPF, DKIM and DNSSEC records.
8. Only after user-approved cutover, change website A and www CNAME records; confirm SSL, forms and analytics.

Current known website DNS: apex A records point to GitHub Pages 185.199.x.153; www CNAME points to globalgptinvest-lang.github.io. Vercel project custom domain status shown invalid. Do not assume Vercel serves the public site.

No production changes are authorized by this checklist.
