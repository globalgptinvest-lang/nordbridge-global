"""Retired legacy Airtable intake.

The canonical NordBridge deal registry is monday.com board 5103432319.
This script intentionally performs no network requests or CRM writes.
Do not restore scheduled execution without verified Gmail and monday.com
credentials, message-id deduplication, consent checks and a dry-run test.
"""
import sys

if __name__ == "__main__":
    print("Legacy Airtable intake retired. No records read or written.")
    sys.exit(0)
