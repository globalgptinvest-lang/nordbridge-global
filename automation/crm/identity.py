"""NordBridge deterministic identity and outbound idempotency helpers.

No network, mail sending, or database access. Safe to import in agents.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

def normalize_domain(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    raw = value.strip().lower()
    parsed = urlparse(raw if "://" in raw else "//" + raw)
    hostname = (parsed.hostname or "").rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if not hostname or any(c.isspace() for c in hostname) or "." not in hostname:
        raise ValueError("Invalid domain")
    return hostname.encode("idna").decode("ascii")

def normalize_email(value: str) -> str:
    result = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result):
        raise ValueError("Invalid email")
    return result

def normalize_company_name(value: str) -> str:
    result = re.sub(r"\s+", " ", value.strip()).casefold()
    if not result:
        raise ValueError("Missing company name")
    return result

def company_identity(legal_name: str, country: str | None = None,
                     registration_number: str | None = None,
                     domain: str | None = None) -> tuple[str, ...]:
    if country and registration_number and registration_number.strip():
        return ("registry", country.strip().upper(), re.sub(r"[\s-]+", "", registration_number).upper())
    if domain:
        return ("domain", normalize_domain(domain) or "")
    return ("name", country.strip().upper() if country else "", normalize_company_name(legal_name))

def outbound_key(opportunity_id: str, email: str, action: str) -> str:
    """Stable logical key: store under a UNIQUE constraint before attempting send.

    Do not retry an uncertain provider outcome without reconciling Sent and message ID.
    """
    import hashlib
    raw = "|".join((opportunity_id.strip(), normalize_email(email), action.strip().lower()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
