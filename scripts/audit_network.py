"""Small, bounded read-only network retries for NordBridge browser monitoring.

Retries transport faults and explicit temporary HTTP responses only; persistent
failures still fail the monitoring run. No credentials, form submissions or writes.
"""
import asyncio
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

RETRYABLE_HTTP = frozenset((429, 502, 503, 504))
RETRYABLE_BROWSER = ("ERR_CONNECTION_CLOSED", "ERR_CONNECTION_RESET",
                     "ERR_SSL_PROTOCOL_ERROR", "ERR_EMPTY_RESPONSE",
                     "ERR_TIMED_OUT", "ERR_NAME_NOT_RESOLVED", "Timeout")

def read_bytes(url, *, attempts=3, timeout=22, sleep=time.sleep, opener=urlopen):
    """Fetch with 2s and 4s backoff for transient transport failures."""
    last = None
    for index in range(attempts):
        try:
            with opener(url, timeout=timeout) as response:
                code = getattr(response, "status", 200)
                if code is not None and not 200 <= code < 300:
                    raise HTTPError(url, code, "Unexpected HTTP status", {}, None)
                return response.read()
        except HTTPError as error:
            if error.code not in RETRYABLE_HTTP:
                raise
            last = error
        except (URLError, TimeoutError, ConnectionError, OSError) as error:
            last = error
        if index < attempts - 1:
            sleep(2 * (index + 1))
    raise RuntimeError(
        "Upstream unavailable after {} attempts: {}: {}".format(
            attempts, type(last).__name__, str(last)[:170])) from last

async def goto_with_retry(page, url, *, attempts=3, timeout=25000, sleep=asyncio.sleep):
    """Retry Chromium navigation only for recognized transient network faults."""
    for index in range(attempts):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # Leave permanent 4xx and 5xx page failures to the audit's status check.
            if response is not None and response.status in RETRYABLE_HTTP and index < attempts-1:
                await sleep(2 * (index + 1))
                continue
            return response
        except Exception as error:
            if index >= attempts-1 or not any(t in str(error) for t in RETRYABLE_BROWSER):
                raise
            await sleep(2 * (index + 1))
    raise RuntimeError("Unexpected retry termination")
