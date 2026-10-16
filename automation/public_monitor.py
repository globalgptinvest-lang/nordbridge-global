#!/usr/bin/env python3
"""Read-only NordBridge public procurement signals and website health check.

No authenticated services. No sending. No sensitive data. Standard library only.
"""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

TED_API = "https://api.ted.europa.eu/v3/notices/search"
SITE = "https://nordbridge-global.com/"
QUERIES = ['FT~"freight"', 'FT~"logistics"', 'FT~"industrial equipment"']
MAX_IDS = 1500

def http_json(url, payload=None, timeout=25):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": "NordBridge-public-monitor/1.0 (read-only)", "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            try:
                delay = int(retry_after)
            except (TypeError, ValueError):
                delay = 3 * (attempt + 1)
            time.sleep(max(1, min(delay, 15)))

def check_website(url=SITE):
    request = urllib.request.Request(url, headers={"User-Agent": "NordBridge-site-monitor/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            mime = response.headers.get("content-type", "")
            snippet = response.read(8192)
            return {"url": url, "ok": response.status == 200 and bool(snippet),
                    "status": response.status, "content_type": mime}
    except Exception as exc:
        return {"url": url, "ok": False, "error": str(exc)[:300]}

def parse_notice(raw):
    if not isinstance(raw, dict):
        return None
    publication = raw.get("publication-number") or raw.get("publicationNumber")
    if isinstance(publication, list):
        publication = publication[0] if publication else None
    if not isinstance(publication, (str, int)) or not publication:
        return None
    title = raw.get("notice-title") or raw.get("noticeTitle") or "Title unavailable"
    if isinstance(title, dict):
        title = title.get("eng") or next(iter(title.values()), "Title unavailable")
    if isinstance(title, list):
        title = title[0] if title else "Title unavailable"
    if isinstance(title, dict):
        title = next(iter(title.values()), "Title unavailable")
    buyer = raw.get("buyer-name") or raw.get("buyerName") or "Unverified buyer"
    if isinstance(buyer, dict):
        buyer = buyer.get("eng") or next(iter(buyer.values()), "Unverified buyer")
    if isinstance(buyer, list):
        buyer = buyer[0] if buyer else "Unverified buyer"
    number = str(publication)
    return {"id": number, "title": str(title)[:250], "buyer": str(buyer)[:150],
            "url": "https://ted.europa.eu/en/notice/-/detail/" + number,
            "source": "TED (public)", "estimated_value_eur": None,
            "note": "Value, deadline, eligibility and fit require verification."}

def query_ted(term, today=None):
    day = today or dt.datetime.now(dt.timezone.utc).date()
    start = (day - dt.timedelta(days=7)).strftime("%Y%m%d")
    payload = {"query": f"{term} AND PD>={start} SORT BY publication-date DESC",
               "fields": ["publication-number", "notice-title", "buyer-name"],
               "limit": 25, "scope": "ACTIVE", "paginationMode": "PAGE_NUMBER", "page": 1}
    response = http_json(TED_API, payload)
    rows = response.get("notices") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Unexpected TED response; no verified notices list")
    return [n for row in rows if (n := parse_notice(row)) is not None]

def read_state(path):
    try:
        with open(path, encoding="utf8") as handle:
            data = json.load(handle)
            if isinstance(data, dict) and isinstance(data.get("seen"), list):
                return set(str(s) for s in data["seen"][:MAX_IDS]), False
    except (OSError, ValueError):
        pass
    return set(), True

def safe_summary(report):
    lines = ["## NordBridge — public-only monitor", "", f"Time: {report['checked_at']}",
             f"Website: {'OK' if report['site']['ok'] else 'CHECK NEEDED'}", "",
             f"Public TED opportunities checked: {report['total_checked']}",
             f"New since previous run: {len(report['new'])}", "",
             "These are public leads, **not verified contracts or private tenders**."]
    if report["first_run"]:
        lines.append("First run: existing notices saved as baseline; no false 'new' alerts.")
    if report["new"]:
        lines.append("\n### New public leads\n")
        for x in report["new"][:15]:
            clean = x["title"].replace("\n", " ").replace("\r", " ").replace("|", "-").replace("[", "(").replace("]", ")")
            lines.append(f"- {clean[:120]} — {x['url']}")
    if report.get("partial"):
        lines.append("\nPartial TED scan: some queries failed; do not treat results as comprehensive.")
    if report["errors"]:
        lines.append("\n### Source errors\n")
        for x in report["errors"]:
            lines.append("- " + x.replace("\n", " ")[:300])
    return "\n".join(lines) + "\n"

def main():
    output = Path(os.getenv("NORDBRIDGE_REPORT", "public_monitor_report.json"))
    state_path = Path(os.getenv("NORDBRIDGE_STATE", "public_monitor_state.json"))
    prior, first = read_state(state_path)
    site = check_website()
    found, errors = {}, []
    successful_queries = 0
    for term in QUERIES:
        try:
            for n in query_ted(term):
                found[n["id"]] = n
            successful_queries += 1
        except Exception as exc:
            errors.append(f"TED {term}: {type(exc).__name__}: {str(exc)[:200]}")
    incoming = set(found)
    new = [] if first else [found[x] for x in sorted(incoming - prior)]
    if incoming:
        updated_seen = list(dict.fromkeys(sorted(incoming) + sorted(prior)))[:MAX_IDS]
        state_path.write_text(json.dumps({"seen": updated_seen}, ensure_ascii=False), encoding="utf8")
    report = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "site": site,
              "first_run": first, "total_checked": len(incoming), "new": new, "errors": errors,
              "successful_queries": successful_queries, "partial": bool(errors) and successful_queries > 0,
              "sources": ["TED Search API (anonymous, public notices)"]}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    summary = safe_summary(report)
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf8") as handle:
            handle.write(summary)
    if not site["ok"] or successful_queries == 0:
        print("Monitor failed: site unreachable or every TED query failed.", file=sys.stderr)
        return 1
    if errors:
        print("Partial TED results: review source errors in the saved report.", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
