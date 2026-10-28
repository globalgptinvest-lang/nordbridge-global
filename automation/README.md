# NordBridge — global procurement and safe lead review

## Public monitor (active only after merging)

The hourly read-only GitHub workflow **nordbridge-public-monitor.yml** checks the website and searches official **EU TED**, **UK Find a Tender**, and **Ukraine Prozorro public API** procurement notices.

- TED: 36 industry topics spanning infrastructure, logistics, industrial supplies, IT, energy, humanitarian procurement and consulting. Six bounded searches per hourly run, completing the rotation in six hours. https://docs.ted.europa.eu/api/latest/search.html
- UK: read-only OCDS Release Packages endpoint, filtering recent tender-stage notices: https://www.find-tender.service.gov.uk/apidocumentation/1.0/GET-ocdsReleasePackages
- Ukraine: official Prozorro public feed with `descending=1`, a page of up to 40 updated tenders, up to 8 detail reads and **at most 4 active opportunity candidates per hourly run**. UA ID, title, status, buyer, amount/currency and deadline must come from source detail. https://prozorro-api-docs.readthedocs.io/en/master/basic-actions/feed.html
- World Bank public procurement data, UNGM, national tender portals across Africa/Asia/Americas, private supplier networks and financing leads are **not yet included** in this GitHub runner. They require independently verified APIs or private workflows; links to public portals are not evidence of active API integration.
- UNGM: the official Notices API requires authorization; it has not been connected. https://developer.ungm.org/Article/GetNotices

Temporary source failures, HTTP 429/503 and incomplete runs are explicitly reported. Notices from different sources use source-prefixed IDs to avoid collisions. Prior IDs are retained when only some sources succeed. Expired UK notices with a known UTC deadline are excluded. UK GBP and Ukraine UAH values remain in their original currencies, not guessed EUR. Every opportunity still requires human verification of actual budget, deadline, eligibility, completeness and buyer requirements. No private or confidential tender claims.

No emails, bids, signed contracts, Stripe payments or CRM writes run in this public workflow. GitHub caches and artifacts only contain public notice titles and links; never add private company/contact records.

## Private lead/contact guard

Run automation/contact_guard.py only on a private trusted machine and private data files. The script NEVER sends messages or accesses email/CRM/Stripe. It checks input records for obvious duplicates, prior outreach, permanent bounces, opt-outs, dated evidence, service fit and the finance EUR 100k minimum.

Create a **synthetic** example file, outside this public repo, such as:

~~~json
{
  "prospects": [{
    "company": "Example Advisory",
    "email": "procurement@example.org",
    "offer_type": "tender",
    "tender_ref": "RFQ-12345",
    "evidence_url": "https://example.org/notice",
    "evidence_date": "2026-10-17",
    "need": "Paid tender document compliance review"
  }],
  "previously_contacted": [],
  "hard_bounces": [],
  "opt_outs": []
}
~~~

Run:

~~~sh
python3 automation/contact_guard.py --input /secure/leads.json --output /secure/review.json
~~~

READY_FOR_HUMAN_REVIEW means only that records passed basic automated checks. It does NOT mean an email exists, a company needs the proposed service, consent/legal basis exists, tender requirements are satisfied, financing will be arranged, or a paid service has been agreed.

Before lawful personalized outreach, review corporate sources, real needs, business email validity, opt-outs, duplicates in Gmail SENT/INBOX/SPAM, and CRM by domain/email/tender/deal ID. Do not resend to hard-bounced addresses or bypass sender limits. Confirm SENT only with provider message ID; DELIVERED only with delivery evidence.

## Production website intake and protected CRM (reviewed 2026-10-28)

The public NordBridge website is served through the Vercel project connected to this repository. Website forms enhance to Vercel `/api/lead` when `/api/intake-status` reports readiness. Readiness checks the selected provider and, in CRM server mode, its public `/health` endpoint before enabling the server route.

The current Vercel production configuration selects the NordBridge CRM API on the VPS, backed by PostgreSQL. CRM URL and token are private environment variables and must never be copied into GitHub Actions, reports, or this repository. If the CRM health check fails, the public status becomes not ready and the existing FormSubmit fallback remains available. If a lead write fails while CRM server mode is selected, the API returns an error instead of silently writing a duplicate to Airtable.

The configured direct CRM endpoint `crm.57.129.182.200.sslip.io` returned healthy during the 2026-10-28 review. The branded aliases `crm.nordbridge-global.com` and `office.nordbridge-global.com` were unreachable in external checks and remain unverified; do not rely on them until DNS and TLS are corrected and verified. A public `/health` result verifies only basic service/database availability, not authenticated lead creation or notification delivery.

A historical synthetic website form submission was confirmed in the private Airtable Website Leads table on 2026-10-17. That historical check does not establish current delivery behavior or make Airtable the canonical CRM. Do not submit real customer details as a test; use an approved synthetic lead and verify the private CRM record and delivery logs.

Invoice/payment state is private. Public checkout links and payment status require independent verification against the connected Stripe account. Never claim an invoice was paid or change beneficiary/payment details without verified evidence.

## ONE RUN — single command public-safe operation

GitHub Actions: **NordBridge ONE RUN — operations audit** → **Run workflow**. It also runs once on changes to its own workflow/source (PR and main), but adds **no new hourly schedule** to existing monitors.

The single command performs HTTP/HTTPS and CRM readiness checks, examines six forms and source-level security guards, counts public Stripe links, runs automated source/unit tests, validates desktop/mobile browser flows (when Playwright is installed), scans EU TED, UK Find a Tender and the bounded official Ukraine Prozorro public API using the existing dedupe cache, and produces one Markdown/JSON report:

~~~sh
python3 automation/nordbridge_one_run.py --browser \
  --state /tmp/nordbridge-state.json \
  --output /tmp/nordbridge-one-run.json \
  --summary /tmp/nordbridge-one-run.md \
  --public-report /tmp/nordbridge-public-report.json
~~~

For static/unit-test checks only: `python3 automation/nordbridge_one_run.py --offline`.

**Not automated by this public workflow:** private Gmail, real replies, client qualification/consent, Airtable content/transactions, invoices, private Stripe payments, bank changes, outgoing letters or bids. Those require separate authenticated **private** app checks and/or an explicit approved transaction. Public readiness never proves a signed contract or confirmed payment.

## Testing and operation

Run Python tests without access to real data:

~~~sh
python -m unittest discover -s automation/tests -v
~~~

The quality gates workflow runs mock tests in a clean environment. Use GitHub Actions → NordBridge public opportunities monitor to view real run summaries. Automated monitoring can be delayed, and a successful unit test is not proof of production lead delivery or an awarded tender.

Separate reporting stages: found, verified, contacted with SENT ID, bounced, replied, paid scope agreed, invoice issued, payment verified. A real contract win or revenue requires independent evidence.
