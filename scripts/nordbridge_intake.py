"""Retired legacy Airtable intake.

The canonical NordBridge deal registry is now private Airtable (2026-10-17).
This script intentionally performs no network requests or CRM writes.
Do not restore scheduled execution or send data to monday.com; use the secure
Vercel intake and private Airtable app with dedupe, consent and authorized access.
"""
import sys

if __name__ == "__main__":
    print("Legacy Airtable intake retired. No records read or written.")
    sys.exit(0)
