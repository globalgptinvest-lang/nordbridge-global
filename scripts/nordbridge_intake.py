"""NordBridge Gmail FormSubmit -> Airtable intake. Standard library only.

Requires GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN,
AIRTABLE_PAT. Optional OPENAI_API_KEY for classification. No outbound email.
"""
import base64
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "appydbFU5sRHKbxdV"
LOG_TABLE = "tbl0KdkZtYVMtxqks"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
AIRTABLE_API = "https://api.airtable.com/v0/" + BASE + "/" + LOG_TABLE
FORM_SENDER = "submissions@formsubmit.co"

def request(url, method="GET", data=None, headers=None, form=False):
    payload = None
    if data is not None:
        payload = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=h, method=method), timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError("API request failed: HTTP " + str(exc.code)) from None
            time.sleep(2 ** attempt + 1)
    raise RuntimeError("API retry limit")

def gmail_token():
    result = request("https://oauth2.googleapis.com/token", "POST", {
        "client_id": os.environ["GMAIL_CLIENT_ID"],
        "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, form=True)
    return {"Authorization": "Bearer " + result["access_token"]}

def gmail_messages(headers):
    query = 'from:submissions@formsubmit.co to:info@nordbridge-global.com newer_than:45d'
    url = GMAIL_API + "/messages?" + urllib.parse.urlencode({"q": query, "maxResults": 100})
    while url:
        page = request(url, headers=headers)
        for msg in page.get("messages", []):
            yield msg["id"]
        token = page.get("nextPageToken")
        url = GMAIL_API + "/messages?" + urllib.parse.urlencode({"q": query, "maxResults": 100, "pageToken": token}) if token else None

def body_text(payload):
    parts = [payload]
    while parts:
        part = parts.pop(0)
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            raw = part["body"]["data"]
            return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
        parts.extend(part.get("parts", []))
    return ""

def extract_fields(body):
    # FormSubmit sends alternating field names and values separated by blank lines.
    text = body.split("Submitted at", 1)[0].split("Here's what they had to say:", 1)[-1]
    blocks = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    fields = {}
    for i in range(0, len(blocks) - 1, 2):
        key = blocks[i].strip().lower()
        if re.fullmatch(r"[a-z0-9_ /-]{2,60}", key):
            fields[key] = blocks[i + 1][:2000]
    return fields

def classify(subject, fields):
    text = (subject + " " + " ".join(fields.keys())).lower()
    category = "tender" if "tender" in text else ("company_profile" if "company" in text else "general")
    suspect = False
    if "years_in_business" in fields:
        try:
            suspect = int(fields["years_in_business"]) > 100
        except ValueError:
            pass
    if not fields.get("email") or fields.get("privacy_consent", "").lower() not in ("accepted", "yes", "true"):
        suspect = True
    return category, ("needs_review" if suspect else "new_unverified")

def existing_ids(headers):
    ids = set()
    url = AIRTABLE_API + "?" + urllib.parse.urlencode({"pageSize": 100, "fields[]": ["Message / Thread ID"]}, doseq=True)
    while url:
        page = request(url, headers=headers)
        for row in page.get("records", []):
            raw = row.get("fields", {}).get("Message / Thread ID", "")
            ids.update(re.findall(r"\b[0-9a-f]{16}\b", raw))
        offset = page.get("offset")
        url = AIRTABLE_API + "?" + urllib.parse.urlencode({"pageSize": 100, "fields[]": ["Message / Thread ID"], "offset": offset}, doseq=True) if offset else None
    return ids

def run():
    gh = gmail_token()
    ah = {"Authorization": "Bearer " + os.environ["AIRTABLE_PAT"]}
    seen = existing_ids(ah)
    added = 0
    for mid in gmail_messages(gh):
        if mid in seen:
            continue
        message = request(GMAIL_API + "/messages/" + urllib.parse.quote(mid) + "?format=full", headers=gh)
        meta = {x["name"].lower(): x["value"] for x in message.get("payload", {}).get("headers", [])}
        sender = meta.get("from", "").lower()
        if FORM_SENDER not in sender:
            continue
        subject = meta.get("subject", "Website form")
        fields = extract_fields(body_text(message.get("payload", {})))
        category, status = classify(subject, fields)
        date = dt.datetime.fromtimestamp(int(message["internalDate"]) / 1000, dt.timezone.utc).isoformat()
        summary = "Category: " + category + "; triage: " + status + "; source: FormSubmit; consent: " + str(fields.get("privacy_consent", "not confirmed")) + ". Manual validation required before outreach."
        record = {"fields": {
            "Activity": "Website lead intake | " + category,
            "Date / Time": date,
            "Counterparty": "Website FormSubmit (unverified)",
            "Message / Thread ID": mid,
            "Summary": summary,
            "Next Step": "Verify sender and lead details in Gmail; qualify; no automatic external outreach.",
        }}
        request(AIRTABLE_API, "POST", {"records": [record], "typecast": False}, ah)
        seen.add(mid)
        added += 1
    print("Intake complete. New Airtable records: " + str(added))

if __name__ == "__main__":
    run()
