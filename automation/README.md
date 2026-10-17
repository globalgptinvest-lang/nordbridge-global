# NordBridge — global procurement and safe lead review

## Public monitor (active only after merging)

The hourly read-only GitHub workflow **nordbridge-public-monitor.yml** checks the website and searches official **EU TED** and **UK Find a Tender** procurement notices.

- TED: nine relevant sectors, three searches each hourly run, completing the rotation in three hours. https://docs.ted.europa.eu/api/latest/search.html
- UK: read-only OCDS Release Packages endpoint, filtering recent tender-stage notices: https://www.find-tender.service.gov.uk/apidocumentation/1.0/GET-ocdsReleasePackages
- UNGM: the official Notices API requires authorization; it has not been connected. https://developer.ungm.org/Article/GetNotices

Temporary source failures, HTTP 429/503 and incomplete runs are explicitly reported. Notices from different sources use source-prefixed IDs to avoid collisions. Prior IDs are retained when only some sources succeed. Expired UK notices with a known UTC deadline are excluded. UK GBP values remain GBP, not guessed EUR. Every opportunity still requires human verification of actual budget, deadline, eligibility, completeness and buyer requirements. No private or confidential tender claims.

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

## Intake and payment blockers that cannot safely be switched on automatically

The website is currently static GitHub Pages. The live forms submit to FormSubmit, which does NOT currently create Airtable/monday records. The pre-existing workflow nordbridge-crm-intake.yml deliberately does not write to CRM because an earlier monday.com call failed with USER_UNAUTHORIZED. Do not silently switch CRM providers or embed API tokens in browser code or a public repository.

To complete end-to-end CRM integration:
1. Authorize a least-privilege private CRM writer and choose one authoritative CRM (monday or Airtable).
2. Build a server-side authenticated webhook or permitted Gmail parser with replay protection and idempotent upsert by Deal ID, source event ID, company/email and tender reference.
3. Implement compliance/privacy, anti-spam, signed request authentication, event logs, error/retry queue and duplicate checks.
4. Test a synthetic authorized site enquiry: form submitted, provider confirms receipt, exactly one CRM record appears, notification received and repeated webhook cannot duplicate it.
5. Only after these tests, change the production website forms or integrations.

Stripe Live payouts were reported enabled on 17 October, but the public buy.stripe.com links have NOT been reconciled to the accessible Live account. This patch does not alter those links, payment pricing, bank details or legal terms.

## Testing and operation

Run Python tests without access to real data:

~~~sh
python -m unittest discover -s automation/tests -v
~~~

The quality gates workflow runs mock tests in a clean environment. Use GitHub Actions → NordBridge public opportunities monitor to view real run summaries. Automated monitoring can be delayed, and a successful unit test is not proof of production lead delivery or an awarded tender.

Separate reporting stages: found, verified, contacted with SENT ID, bounced, replied, paid scope agreed, invoice issued, payment verified. A real contract win or revenue requires independent evidence.
