#!/usr/bin/env python3
"""Read-only public procurement discovery: EU TED and UK Find a Tender.

No authenticated APIs, emailing, personal records or automatic qualification.
All notices remain unverified leads until source documents have been reviewed.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TED_API = "https://api.ted.europa.eu/v3/notices/search"
UK_API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
SITE = "https://nordbridge-global.com/"
# A rotating set of three searches avoids hammering TED each hour.
TOPICS = [
    ('freight', 'FT~"freight"'),
    ('logistics', 'FT~"logistics"'),
    ('industrial equipment', 'FT~"industrial equipment"'),
    ('engineering services', 'FT~"engineering services"'),
    ('renewable energy', 'FT~"renewable energy"'),
    ('bridge design', 'FT~"bridge design"'),
    ('business development', 'FT~"business development"'),
    ('consultancy services', 'FT~"consultancy services"'),
    ('water infrastructure', 'FT~"water infrastructure"'),
]
MAX_IDS = 2500
RELEVANT = ("freight", "logistic", "industrial", "engineer", "renewable",
            "solar", "bridge", "construction", "consult", "development",
            "agricultur", "warehous", "storage", "water", "transport")

def now_utc():
    return dt.datetime.now(dt.timezone.utc)

def http_json(url, payload=None, timeout=22):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": "NordBridge-public-research/1.1 (read-only)",
               "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt >= 2:
                raise
            value = exc.headers.get("Retry-After", "")
            try:
                delay = float(value)
            except (TypeError, ValueError):
                delay = 3 * (attempt + 1)
            # Respect server back-off as far as practical within Actions runtime.
            if delay > 15:
                raise RuntimeError(f"Source rate-limited; Retry-After {value}s, defer next run") from exc
            time.sleep(max(1, delay))
    raise RuntimeError("Source unavailable after retries")

def check_website(url=SITE):
    req = urllib.request.Request(url, headers={"User-Agent": "NordBridge-site-monitor/1.1"})
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            body = response.read(8192)
            return {"url": url, "ok": response.status == 200 and bool(body),
                    "status": response.status, "content_type": response.headers.get("Content-Type", "")}
    except Exception as exc:
        return {"url": url, "ok": False, "error": str(exc)[:160]}

def _text(value, fallback=""):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("eng") or value.get("en") or next(iter(value.values()), None)
    return str(value).strip() if value is not None else fallback

def parse_ted_notice(raw):
    if not isinstance(raw, dict):
        return None
    publication = _text(raw.get("publication-number") or raw.get("publicationNumber"))
    if not re.fullmatch(r"\d{6}-\d{4}", publication):
        return None
    return {"id": "TED:" + publication, "title": _text(raw.get("notice-title") or raw.get("noticeTitle"), "Title unavailable")[:250],
            "buyer": _text(raw.get("buyer-name") or raw.get("buyerName"), "Unverified buyer")[:150],
            "url": "https://ted.europa.eu/en/notice/-/detail/" + publication,
            "source": "TED", "deadline": None, "value": None, "currency": None,
            "verification": "Review official notice for value, bid deadline, buyer and eligibility."}

def rotating_ted_queries(at=None):
    moment = at or now_utc()
    offset = (moment.hour % 3) * 3
    return TOPICS[offset:offset + 3]

def query_ted(term, today=None):
    day = today or now_utc().date()
    start = (day - dt.timedelta(days=7)).strftime("%Y%m%d")
    payload = {"query": f"{term} AND PD>={start} SORT BY publication-date DESC",
               "fields": ["publication-number", "notice-title", "buyer-name"],
               "limit": 25, "scope": "ACTIVE", "paginationMode": "PAGE_NUMBER", "page": 1}
    response = http_json(TED_API, payload)
    notices = response.get("notices") if isinstance(response, dict) else None
    if not isinstance(notices, list):
        raise ValueError("TED response missing notices array")
    return [x for row in notices if (x := parse_ted_notice(row))]

def _deadline(raw):
    if not isinstance(raw, str):
        return None, None
    try:
        date = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return raw, None  # local time: cannot safely assert expiry
        return raw, date.astimezone(dt.timezone.utc)
    except ValueError:
        return None, None

def parse_uk_release(release, today=None):
    if not isinstance(release, dict) or not isinstance(release.get("tender"), dict):
        return None
    tender = release["tender"]
    if "tender" not in release.get("tag", []):
        return None
    if tender.get("status") in ("cancelled", "complete", "unsuccessful", "withdrawn", "planned"):
        return None
    notice = _text(release.get("id"))
    if not re.fullmatch(r"\d{6}-20\d{2}", notice):
        return None
    title = _text(tender.get("title"), "Title unavailable")
    if not title:
        return None
    period = tender.get("tenderPeriod") or {}
    date_string, parsed = _deadline(period.get("endDate"))
    if parsed and parsed < (today or now_utc()):
        return None
    value_obj = tender.get("value") or {}
    amount = value_obj.get("amount") if isinstance(value_obj, dict) else None
    currency = value_obj.get("currency") if isinstance(value_obj, dict) else None
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
        amount = None
        currency = None
    buyer = _text((release.get("buyer") or {}).get("name"), "Unverified buyer")
    return {"id": "UK:" + notice, "title": title[:250], "buyer": buyer[:150],
            "url": "https://www.find-tender.service.gov.uk/Notice/" + notice,
            "source": "UK Find a Tender", "deadline": date_string,
            "value": amount, "currency": currency if amount is not None else None,
            "verification": "Review official notice for open status, requirements, currency and eligibility."}

def query_uk(today=None):
    day = today or now_utc()
    start = (day - dt.timedelta(days=3)).strftime("%Y-%m-%dT00:00:00")
    params = urllib.parse.urlencode({"updatedFrom": start, "stages": "tender", "limit": 50})
    body = http_json(UK_API + "?" + params)
    if not isinstance(body, dict) or not isinstance(body.get("releases"), list):
        raise ValueError("UK OCDS response missing releases array")
    return [n for rel in body["releases"] if (n := parse_uk_release(rel, day))]

def rank_notice(notice):
    """Internal triage signal only: never claim a tender qualifies based on score."""
    title = notice["title"].casefold()
    hits = [token for token in RELEVANT if token in title]
    score = min(80, 20 + 15 * len(hits))
    if notice.get("value") is not None:
        score = min(90, score + 10)  # amount is sourced, not currency-converted
    return {**notice, "triage_score": score, "matched_keywords": hits}

def read_state(path):
    try:
        with Path(path).open(encoding="utf8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("seen"), list):
            return {("TED:" + x if re.fullmatch(r"\d{6}-\d{4}", x) else x)
                    for x in data["seen"][:MAX_IDS] if isinstance(x, str)}, False
    except (OSError, ValueError):
        pass
    return set(), True

def safe_summary(report):
    checks = report["sources_checked"]
    lines = ["## NordBridge — verified-source procurement scan", "",
             f"Checked: {report['checked_at']}",
             f"Website: {'OK' if report['site']['ok'] else 'CHECK NEEDED'}",
             f"Official sources queried: TED ({checks['ted_ok']}/{checks['ted_total']} rotating topics); UK Find a Tender ({checks['uk_ok']}/1)",
             f"Distinct notice candidates: {report['total_checked']}",
             f"First observed by this monitor: {len(report['new'])}", "",
             "Every result is an **unverified opportunity**. No claim of bidder eligibility, contract size, closing date or award."]
    if report["first_run"]:
        lines.append("First run: establishes baseline without announcing old notices as new.")
    if report["partial"]:
        lines.append("Partial scan: one or more official source queries failed.")
    if report["new"]:
        lines.append("\n### New public opportunities (triage only)")
        for n in report["new"][:20]:
            title = re.sub(r"[\r\n|[\]]", " ", n["title"])[:125]
            lines.append(f"- {title} [{n['source']}] — {n['url']}")
    if report["errors"]:
        lines.append("\n### Source errors")
        lines.extend("- " + e.replace("\n", " ")[:200] for e in report["errors"])
    return "\n".join(lines) + "\n"

def run_monitor(output, state_path, moment=None, website_checker=check_website):
    moment = moment or now_utc()
    prior, first = read_state(state_path)
    site = website_checker()
    found, errors = {}, []
    topics = rotating_ted_queries(moment)
    ted_ok = 0
    for label, term in topics:
        try:
            for notice in query_ted(term, moment.date()):
                found[notice["id"]] = rank_notice(notice)
            ted_ok += 1
        except Exception as exc:
            errors.append(f"TED/{label}: {type(exc).__name__}: {str(exc)[:140]}")
    uk_ok = 0
    try:
        for notice in query_uk(moment):
            found[notice["id"]] = rank_notice(notice)
        uk_ok = 1
    except Exception as exc:
        errors.append(f"UK OCDS: {type(exc).__name__}: {str(exc)[:140]}")
    incoming = set(found)
    new = [] if first else [found[x] for x in (incoming - prior)]
    new.sort(key=lambda x: (-x["triage_score"], x["id"]))
    if incoming:
        # Preserve prior IDs and avoid losing de-duplication on a partial run.
        merged = sorted(incoming) + sorted(prior - incoming)
        Path(state_path).write_text(json.dumps({"seen": merged[:MAX_IDS]}, ensure_ascii=False), encoding="utf8")
    report = {
        "checked_at": moment.isoformat(), "site": site,
        "first_run": first, "partial": bool(errors),
        "total_checked": len(found), "new": new, "errors": errors,
        "sources_checked": {"ted_ok": ted_ok, "ted_total": len(topics), "uk_ok": uk_ok},
        "sources": ["EU TED Search API", "UK Find a Tender OCDS release API"],
        "outreach_sent": 0, "automatic_crm_writes": 0
    }
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    summary = safe_summary(report)
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf8") as handle:
            handle.write(summary)
    if not site["ok"] or ted_ok + uk_ok == 0:
        print("Critical failure: site unreachable or all sources failed.", file=sys.stderr)
        return 1
    return 0

def main():
    return run_monitor(
        os.getenv("NORDBRIDGE_REPORT", "public_monitor_report.json"),
        os.getenv("NORDBRIDGE_STATE", "public_monitor_state.json")
    )

if __name__ == "__main__":
    sys.exit(main())
