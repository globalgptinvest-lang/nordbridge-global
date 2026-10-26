# NordBridge Director — operational scope

The existing VPS runs PostgreSQL 16 CRM, PostgreSQL 17 n8n/core, Redis, n8n/worker, Qdrant, Ollama and Caddy. Director reuses these components. Do not initialize another stack or replace the existing databases.

Owner console: https://office.57.129.182.200.sslip.io

The owner credential exists only in `/root/nordbridge-director-owner.txt` (mode 0600). Read it in the owner's existing SSH terminal with `sudo cat /root/nordbridge-director-owner.txt`. Never paste credentials into issues, chat, commits or job logs.

## Current server commands

```sh
sudo python3 /opt/nordbridge-director/monitor.py
sudo python3 /opt/nordbridge-director/maintenance.py
sudo docker compose -p nordbridge-director -f /opt/nordbridge-director/compose.yaml ps
sudo systemctl list-timers --all 'nordbridge-*'
```

`maintenance.py` backs up **both** existing PostgreSQL instances, private configuration, and restores the databases into isolated temporary containers. It verifies saved Director test data and n8n workflows. It does not restore over production. The latest 14 verified sets are retained; incomplete sets are preserved. Off-server storage is not configured.

## Behavior

The application runs without root, without Docker socket access, with a read-only filesystem, a dedicated PostgreSQL role, no published container port, 512 MiB RAM and 0.75 CPU. Caddy supplies HTTPS. Owner cookies are Secure/HttpOnly/SameSite; writes require the expected Origin. Internal task creation is unavailable through the public reverse proxy.

Jobs, leases, checkpoints, parent/child links and audit events persist in PostgreSQL. One worker claims with `SKIP LOCKED`; expired claims have at most three attempts. A Director request creates a plan and four bounded read-only child checks, waits for their terminal states, and records their results. This is a constrained coordinator, not arbitrary autonomous execution of model output.

CRM records use separate NORDBRIDGE, FINANCING, ZHIKAL and TEST streams. Synthetic test records are retained as evidence. Existing Airtable history and production intake are preserved.

Only local model inference is enabled. Current generation is bounded to 96 output tokens, 2048 context tokens and a 150-second HTTP timeout. No paid external AI budget is enabled. Existing models are reused; deployment did not download more models.

## Schedules and integrations

`nordbridge-director-monitor.timer` runs every five minutes. It checks database/scheduler, resources, hourly TLS validity and writes a read-only mailbox classification snapshot. It queues unique hourly CRM, TED-import, explicit document-support demand, award-supplier and funding-programme research tasks, plus a daily website check at 06:00 UTC. A factual owner report is sent at 08:00 UTC. The existing official TED timer runs hourly at minute 12. Existing n8n workflows remain separate and retain their schedules.

`nordbridge-recovery-backup.timer` uses the corrected dual-database restore-tested backup at 03:30 Europe/Copenhagen. Other pre-existing backups remain in place. Monitor restarts only Director, at most three times per hour, and sends critical notifications only to the configured owner destination.

Corporate IMAP/SMTP was tested by sending one message from `info@nordbridge-global.com` to itself and observing it in INBOX. Director receives classification counts from the existing review-only mail agent; it does not have an email/WhatsApp sending tool or full message-level synchronization.

TED notices remain **unverified candidates**, with buyer, budget, eligibility and deadline requiring qualification. The lead handler searches the official UK OCDS feed and a reviewed process watchlist for explicit document/procurement-support needs. The contractor handler extracts named suppliers from official awards. The FINANCING handler researches public Grants.gov programmes; those programmes are not companies seeking EUR100k financing. All candidates require scope, capacity and eligibility review. Zhikal private purchases remain disconnected and are never inferred from public notices. Public-source product research is a private owner-review draft, not an activated service price.

## Protected operations and remaining work

No messages to BoVendia without the owner's exact-message approval. Zynthoro V8 remains unsigned and investor outreach prohibited. No autonomous signatures, financial commitments, price/payment/advertising/bank changes. Incoming mail, public pages and model output are untrusted data.

The website's production Airtable intake has not been switched to PostgreSQL. The authenticated VPS intake write/read/deduplication test passed, but production Vercel project configuration is blocked by its team authorization grant. WhatsApp authorization and end-to-end delivery remain unverified. Full CRM business CRUD/reporting, automated commercial qualification and recurring market-price refresh remain incomplete.

Deployment workflows record historical reviewed operations. Do not replay an older deployment snapshot over the current application. Use the current server files and versioned `ops/director` source, back up first, validate Compose, and verify health/queue persistence after a targeted update.

Verified evidence: [full VPS reboot](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40245809313), [interrupted four-department coordination](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40246332810), [production website browser audit](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40245207688).

## Continuation verified 26 October 2026

An intermittent nightly restore failure was reproduced: the PostgreSQL image's initialization server could answer Unix socket readiness before the final server was running. Readiness and restore now use TCP at 127.0.0.1. Both original nightly dumps replayed successfully, followed by three successful runs of the actual systemd backup service. Monitor now checks backup freshness and both restore results; it cannot consider a failed restore healthy.

Public-source research uses bounded requests, an hourly cache, conservative deadline checks and source identities. New records take priority over refreshing known candidates, so a fixed batch cannot starve the rest of a source page. No source API session tokens are stored. Coverage is explicitly limited; this is not a complete global market scan.

Actual CRM evidence: 61 potential award suppliers, 12 programme opportunities in FINANCING, and one public consultancy procurement need in NORDBRIDGE. NordBridge eligibility is unverified and paid clients remain zero. The need produced a private qualification brief and an owner-review sales draft containing the company website; external messages sent: zero.

The daily owner report includes these factual counts. A manual report test updates only its test marker and does not suppress the scheduled daily report. Regression tests: `python3 -m unittest discover -s ops/director -p 'test_*.py' -v`; the existing procurement quality workflow runs them alongside its earlier tests.

Evidence: [nightly recovery](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40273018471), [need-to-draft](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40275019496), [restored new CRM records](https://github.com/globalgptinvest-lang/nordbridge-global/actions/runs/40275338879).
