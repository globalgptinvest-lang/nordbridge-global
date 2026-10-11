# NordBridge — public monitoring without additional subscription

This is a **read-only**, standard-Python GitHub Actions workflow. It checks public tenders and the website every hour (actual execution may be delayed by GitHub).

## What it checks

- Whether the NordBridge website responds.
- Public freight, logistics and industrial-equipment notices from the official EU TED Search API.
- Duplicate publication numbers between runs, using the GitHub Actions cache.
- New matches in an Actions summary and JSON artifact (retained 3 days).

## What it deliberately never does

- **No outgoing emails, bids, payments, contracts or site modifications.**
- No private/restricted tender claims. Access to invitation-only opportunities requires legitimate vendor registration and direct procurement contact.
- **No assumed contract value.** The €100,000 threshold, dates, eligibility and logistics fit require verification on source documents.
- No customer names, Zhikal deal history, private contacts, Gmail content, signed contracts, API keys or credentials. The site repository is **public**.
- Does not consume ChatGPT Work capacity or paid OpenAI API credits.

## Inspection

Open GitHub → nordbridge-global → Actions → NordBridge public opportunities monitor.
Scheduled workflows execute from the repository's default branch, after the change is merged. You can also select **Run workflow**.

## Limits

The free GitHub-hosted runner tier currently allows public repository workflows. Scheduled runs can be delayed, disabled on inactivity, or limited by GitHub conditions. The initial run establishes a deduplication baseline rather than falsely declaring all current tenders to be newly published.

Official API: https://docs.ted.europa.eu/api/latest/search.html
