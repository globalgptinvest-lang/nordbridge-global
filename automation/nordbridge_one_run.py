#!/usr/bin/env python3
"""NordBridge one-run operations audit (read-only, public-data safe).

One invocation verifies the public website, published CRM intake readiness,
local source safety, existing unit/browser tests, public procurement monitor,
and inventories payment links. It cannot reconcile private Gmail, actual Airtable
records, issued invoices or Stripe link ownership without private app access.
No client contact, CRM mutation, payment, bid, or financial change is performed.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SITE = "https://www.nordbridge-global.com"
SENSITIVE = re.compile(r"(?i)(Bearer\s+\S+|sk_(?:live|test)_[A-Za-z0-9]+|pat[A-Za-z0-9]{16,})")
PAGES = ("/", "/contact.html", "/privacy.html", "/free-tender-fit-check.html",
         "/business-financing.html", "/tender-subscription.html")
FORMS = ("submit-tender.html", "free-tender-fit-check.html",
         "business-financing.html", "buyer-request.html",
         "company-profile.html", "subscription-profile.html")
RETRYABLE_HTTP = frozenset((429, 502, 503, 504))
REVIEW_NOTES = (
    "Site readiness does not prove successful CRM record storage; a real form was tested separately.",
    "Mail delivery, duplicate outreach, client replies and consent require private Gmail/CRM access.",
    "Invoices, Stripe payments and payout reconciliation require authorized account evidence.",
    "Listed public tenders are candidates, NOT qualified bids, contractor matches, wins or contracts.",
)

def sanitized(message, limit=240):
    """Public report must never echo secret values, emails or provider responses."""
    value = SENSITIVE.sub("[REDACTED]", str(message))
    value = re.sub(r"[\r\n|]", " ", value)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL REDACTED]", value)
    return value[:limit]

def outcome(name, status, detail="", **extra):
    assert status in ("PASS", "FAIL", "REVIEW", "SKIP")
    result = {"name": name, "status": status, "detail": sanitized(detail)}
    result.update(extra)
    return result

def public_get(url, attempts=3, timeout=22, opener=urlopen, wait=time.sleep):
    """Bounded retries for network/5xx faults, not for permanent HTTP errors."""
    last = None
    for idx in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": "NordBridge-read-only-ops-audit/1.0"})
            with opener(req, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status is not None and not 200 <= status < 300:
                    raise HTTPError(url, status, "Unexpected status", {}, None)
                return response.read(110000), response.geturl()
        except HTTPError as error:
            if error.code not in RETRYABLE_HTTP:
                raise
            last = error
        except (OSError, URLError, TimeoutError, ConnectionError) as error:
            last = error
        if idx < attempts - 1:
            wait(2 * (idx + 1))
    raise RuntimeError("HTTPS unavailable after retries: " + type(last).__name__)

def check_public_site(getter=public_get):
    checks = []
    for path in PAGES:
        try:
            content, target = getter(PUBLIC_SITE + path)
            valid = len(content) > 50 and b"<html" in content.lower()
            checks.append(outcome("Site " + path, "PASS" if valid else "FAIL",
                                  "HTTP 2xx, HTML present" if valid else "Empty or invalid HTML"))
        except Exception as error:
            checks.append(outcome("Site " + path, "FAIL", type(error).__name__))
    try:
        _, target = getter("https://nordbridge-global.com/")
        canonical = target.startswith(PUBLIC_SITE + "/")
        checks.append(outcome("Apex HTTPS redirect", "PASS" if canonical else "REVIEW",
                              "Uses www canonical" if canonical else "Unexpected redirect target"))
    except Exception as error:
        checks.append(outcome("Apex HTTPS redirect", "FAIL", type(error).__name__))
    try:
        content, _ = getter(PUBLIC_SITE + "/api/intake-status")
        data = json.loads(content.decode("utf8"))
        ready = isinstance(data, dict) and data.get("ready") is True
        checks.append(outcome("Private CRM intake readiness", "PASS" if ready else "FAIL",
                              "Vercel has private CRM/Turnstile configuration" if ready else "Ready flag missing"))
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        checks.append(outcome("Private CRM intake readiness", "FAIL", type(error).__name__))
    return checks

def inspect_sources(root=ROOT):
    checks = []
    code = (root / "api/lead.js")
    client = (root / "forms-intake.js")
    if not code.is_file() or not client.is_file():
        return [outcome("Server-side intake code", "FAIL", "Missing server or browser integration")]
    server = code.read_text(encoding="utf8")
    frontend = client.read_text(encoding="utf8")
    guards = ("TURNSTILE_SECRET_KEY", "AIRTABLE_PERSONAL_ACCESS_TOKEN",
              "validateTurnstile", "ALLOWED_ORIGINS", "privacy_consent")
    secured = all(term in server for term in guards) and "cf-turnstile-response" in frontend
    checks.append(outcome("Intake source security gates", "PASS" if secured else "FAIL",
                          "Server-held secrets and consent/challenge guards present" if secured else "Missing required guard"))
    failed = []
    for name in FORMS:
        path = root / name
        if not path.exists():
            failed.append(name + " missing")
            continue
        html = path.read_text(encoding="utf8")
        if not all(s in html for s in ('class="lead-form', "privacy_consent",
                                     "forms-intake.js", "formsubmit.co/")):
            failed.append(name + " integration missing")
    checks.append(outcome("Six website forms wired", "PASS" if not failed else "FAIL",
                          "All forms retain consent, intake and fallback" if not failed else ", ".join(failed)))
    html_files = tuple(root.glob("*.html"))
    payment_urls = set()
    for page in html_files:
        for url in re.findall(r"https://buy\.stripe\.com/[A-Za-z0-9]+", page.read_text(encoding="utf8")):
            payment_urls.add(url)
    checks.append(outcome("Published Stripe payment links", "REVIEW" if payment_urls else "PASS",
                          f"{len(payment_urls)} unique public link(s); ownership and live settlement NOT confirmed",
                          public_stripe_link_count=len(payment_urls)))
    return checks

def command(name, argv, timeout=220):
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                timeout=timeout, check=False, encoding="utf8", errors="replace")
        # Avoid publishing private output; public tests should contain synthetic data.
        if result.returncode:
            detail = "Exit " + str(result.returncode) + ": " + sanitized((result.stderr or result.stdout)[-200:])
        else:
            detail = "Passed without modifying customer or billing data"
        return outcome(name, "PASS" if result.returncode == 0 else "FAIL", detail)
    except (OSError, subprocess.TimeoutExpired) as error:
        return outcome(name, "FAIL", type(error).__name__)

def run_public_monitor(state_path, report_path):
    env = os.environ.copy()
    env["NORDBRIDGE_STATE"] = str(state_path)
    env["NORDBRIDGE_REPORT"] = str(report_path)
    try:
        task = subprocess.run([sys.executable, "automation/public_monitor.py"],
                              cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=190, check=False)
        if not report_path.is_file():
            return outcome("EU TED and UK procurement scan", "FAIL",
                           "Monitor did not write a public-source report"), {}
        data = json.loads(report_path.read_text(encoding="utf8"))
        src = data.get("sources_checked", {})
        details = (f"TED {src.get('ted_ok',0)}/{src.get('ted_total',3)}, "
                   f"UK {src.get('uk_ok',0)}/1; "
                   f"{data.get('total_checked',0)} unverified candidate(s); "
                   f"{len(data.get('new',[]))} newly observed vs cached state")
        status = "FAIL" if task.returncode else ("REVIEW" if data.get("partial") else "PASS")
        return outcome("EU TED and UK procurement scan", status, details,
                       unverified_opportunities=data.get("total_checked",0),
                       first_run=data.get("first_run",False)), data
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return outcome("EU TED and UK procurement scan", "FAIL", type(error).__name__), {}

def markdown(report):
    lines = ["# NordBridge — one-run verified operations report", "",
             "UTC: " + report["checked_at"], "",
             "| Component | Result | Evidence |", "|---|---|---|"]
    for check in report["checks"]:
        lines.append("| " + sanitized(check["name"]) + " | " +
                     check["status"] + " | " + sanitized(check["detail"]) + " |")
    lines += ["", "## Private controls not asserted by this public workflow", ""]
    lines += ["- " + note for note in REVIEW_NOTES]
    lines += ["", "**No email sent, CRM record created, bid filed, invoice issued, charge collected, bank detail changed or paid service activated.**"]
    return "\n".join(lines) + "\n"

def run(args):
    root = ROOT
    results = []
    results.extend(inspect_sources(root))
    if args.offline:
        results.append(outcome("Public HTTPS and CRM readiness", "SKIP", "Offline test mode"))
    else:
        results.extend(check_public_site())
    results.append(command("Source safety unit tests",
                           [sys.executable, "-m", "unittest", "discover", "-s", "automation/tests", "-v"]))
    results.append(command("Network retry unit tests",
                           [sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests",
                            "-p", "test_*.py", "-v"]))
    results.append(command("Private CRM synthetic intake tests",
                           ["node", "--test", "scripts/tests/intake.test.cjs"]))
    if args.browser and not args.offline:
        for title, script in (("Responsive browser audit", "scripts/external_browser_audit.py"),
                              ("Financing calculator browser test", "scripts/calculator_browser_tests.py"),
                              ("Four-language browser test", "scripts/translation_browser_tests.py")):
            results.append(command(title, [sys.executable, script], timeout=240))
    else:
        results.append(outcome("Full browser tests", "SKIP", "Use --browser in GitHub Actions"))
    with tempfile.TemporaryDirectory(prefix="nb-unified-") as folder:
        state = Path(args.state) if args.state else Path(folder)/"state.json"
        public_report = Path(args.public_report) if args.public_report else Path(folder)/"public.json"
        if args.offline:
            results.append(outcome("Official public tenders", "SKIP", "Offline test mode"))
        else:
            row, _ = run_public_monitor(state, public_report)
            results.append(row)
    results.append(outcome("Private Gmail, invoices and Stripe account reconciliation",
                           "REVIEW", "Requires connected private-account checks; never guessed"))
    report = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "offline" if args.offline else "read_only_live",
        "checks": results,
        "counts": {status: sum(1 for entry in results if entry["status"] == status)
                   for status in ("PASS", "FAIL", "REVIEW", "SKIP")},
        "mutations": {"outreach_sent": 0, "crm_writes": 0, "invoices_created": 0,
                      "payments_created": 0, "financial_settings_changed": 0},
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    summary = markdown(report)
    Path(args.summary).write_text(summary, encoding="utf8")
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf8") as handle:
            handle.write(summary)
    return 1 if report["counts"]["FAIL"] else 0

def main(argv=None):
    p = argparse.ArgumentParser(description="All-in-one SAFE NordBridge audit; does not send/write/charge")
    p.add_argument("--browser", action="store_true", help="Run desktop/mobile Chromium checks")
    p.add_argument("--offline", action="store_true", help="Static and unit-test checks only")
    p.add_argument("--output", default="/tmp/nordbridge-one-run.json")
    p.add_argument("--summary", default="/tmp/nordbridge-one-run.md")
    p.add_argument("--public-report", default="/tmp/nordbridge-public-report.json")
    p.add_argument("--state", default="", help="Optional existing public-only tender dedupe state")
    args = p.parse_args(argv)
    return run(args)

if __name__ == "__main__":
    sys.exit(main())
