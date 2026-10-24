#!/usr/bin/env python3
"""Offline gate for B2B prospect lists; never sends email or uploads lead data.

Input private JSON:
{"prospects":[{"company":"...", "email":"...", "evidence_url":"https://...",
               "evidence_date":"2026-10-17", "need":"...", "tender_ref":"...",
               "offer_type":"tender|finance|contractor", "finance_eur":150000}],
 "previously_contacted":["name@example.com"], "hard_bounces":["bad@example.com"],
 "opt_outs":["nothanks@example.com"]}

No personal/corporate records should be committed to the public GitHub repository.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

EMAIL = re.compile(r"^[^@\s<>]+@([A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,})$")
CATEGORIES = {"tender", "finance", "contractor"}

def norm_email(value):
    return str(value or "").strip().lower()

def norm_text(value):
    return " ".join(str(value or "").lower().split())

def domain_from_url(value):
    try:
        u = urlparse(str(value or ""))
        if u.scheme != "https" or not u.hostname:
            return None
        if u.username or u.password or u.hostname in ("localhost",):
            return None
        return u.hostname.casefold()
    except ValueError:
        return None

def assess(prospect, prior_emails, bounces, optouts, seen_pairs, now=None):
    """Conservative review gate: READY means manual review, never verified delivery."""
    now = now or dt.date.today()
    if not isinstance(prospect, dict):
        return {"status": "HOLD", "reasons": ["invalid_record"]}
    reasons = []
    email = norm_email(prospect.get("email"))
    company = norm_text(prospect.get("company"))
    evidence_url = prospect.get("evidence_url")
    source_host = domain_from_url(evidence_url)
    kind = prospect.get("offer_type")
    # Owner restrictions cannot be overridden by prospect records or model output.
    identity_text = " ".join((company, email, str(source_host or "")))
    if "bovendia" in identity_text:
        reasons.append("owner_specific_message_permission_required")
    if "zynthoro" in identity_text:
        reasons.append("legal_hold_no_investor_outreach")
    if not company:
        reasons.append("company_missing")
    if not EMAIL.fullmatch(email):
        reasons.append("email_unverified_format")
    if email in bounces:
        reasons.append("permanent_bounce")
    if email in optouts:
        reasons.append("opt_out")
    if email in prior_emails:
        reasons.append("already_contacted")
    if not source_host:
        reasons.append("official_source_or_https_evidence_missing")
    if not norm_text(prospect.get("need")):
        reasons.append("actual_service_need_unverified")
    if kind not in CATEGORIES:
        reasons.append("invalid_service_type")
    date = prospect.get("evidence_date")
    try:
        d = dt.date.fromisoformat(date)
        if d > now or (now - d).days > 90:
            reasons.append("source_not_current")
    except (ValueError, TypeError):
        reasons.append("source_date_missing")
    if kind == "finance":
        amount = prospect.get("finance_eur")
        if not isinstance(amount, (float, int)) or isinstance(amount, bool) or amount < 100000:
            reasons.append("financing_amount_not_verified_100k_eur")
    if kind == "tender" and not norm_text(prospect.get("tender_ref")):
        reasons.append("tender_reference_missing")
    identity = (company, norm_text(prospect.get("tender_ref")) or norm_text(kind))
    if identity in seen_pairs:
        reasons.append("duplicate_opportunity")
    seen_pairs.add(identity)
    # Format + a source URL are not proof that an inbox exists or the company consents.
    return {"status": "HOLD" if reasons else "READY_FOR_HUMAN_REVIEW",
            "reasons": sorted(set(reasons)), "record_key": f"{kind or 'unknown'}:{company}"}

def evaluate(payload, today=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("prospects"), list):
        raise ValueError("Expected JSON object with prospects array")
    contacted = {norm_email(e) for e in payload.get("previously_contacted", [])}
    bounced = {norm_email(e) for e in payload.get("hard_bounces", [])}
    optouts = {norm_email(e) for e in payload.get("opt_outs", [])}
    seen = set()
    return [assess(item, contacted, bounced, optouts, seen, today)
            for item in payload["prospects"]]

def main(argv=None):
    parser = argparse.ArgumentParser(description="Private, no-send lead qualification gate")
    parser.add_argument("--input", type=Path, required=True, help="Private local JSON; never check into Git")
    parser.add_argument("--output", type=Path, required=True, help="Write sanitized decisions only")
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        parser.error("Output path must differ from source to protect lead data")
    try:
        data = json.loads(args.input.read_text(encoding="utf8"))
        decisions = evaluate(data)
        result = {"checked": len(decisions),
                  "ready_for_manual_review": sum(x["status"] == "READY_FOR_HUMAN_REVIEW" for x in decisions),
                  "held": sum(x["status"] == "HOLD" for x in decisions),
                  "decisions": decisions,
                  "automatically_sent": 0,
                  "deliverability_confirmed": 0}
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
        print(f"Reviewed {result['checked']}; ready for human review: {result['ready_for_manual_review']}; held: {result['held']}. No email sent.")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Lead input error: {type(exc).__name__} (see private input)", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
