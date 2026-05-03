"""
api_retry.py — Shared HTTP retry utility
─────────────────────────────────────────
Drop-in replacement for requests.get / requests.post / requests.request
with exponential backoff on transient failures.

Retryable conditions:
  • 429 Too Many Requests  — respects Retry-After header if present
  • 500 / 502 / 503 / 504  — server-side transient errors
  • ConnectionError        — network blip
  • Timeout               — server took too long

Non-retryable (raised immediately):
  • 4xx other than 429     — bad request, auth failure, not found
  • RequestException       — malformed request

Usage:
    from api_retry import retry_request

    # Same signature as requests.request()
    resp = retry_request("GET", url, headers=hdrs, timeout=30)
    resp = retry_request("POST", url, json=body, timeout=60)

    # Convenience wrappers
    from api_retry import rget, rpost, rput
    resp = rget(url, headers=hdrs, timeout=30)
    resp = rpost(url, json=body, timeout=60)
    resp = rput(url, json=body, timeout=30)
"""

from __future__ import annotations

import time
from typing import Any

import requests

# ── Config ────────────────────────────────────────────────────────────────────
MAX_RETRIES      = 3
BACKOFF_BASE     = 2   # seconds — delays are 2s, 4s, 8s
MAX_BACKOFF      = 60  # cap so we never wait longer than a minute
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def retry_request(
    method: str,
    url: str,
    *,
    _label: str = "",          # optional human-readable label for log lines
    **kwargs: Any,
) -> requests.Response:
    """
    Make an HTTP request with automatic retry and exponential backoff.

    Args:
        method:  HTTP method string — "GET", "POST", "PUT", etc.
        url:     Full URL.
        _label:  Optional label shown in retry log lines (e.g. "Etsy create listing").
        **kwargs: Passed directly to requests.request() — headers, json, data, timeout, etc.

    Returns:
        requests.Response on any non-retryable response (including final-attempt failures).

    Raises:
        requests.ConnectionError / requests.Timeout after all retries exhausted.
    """
    label = f"[{_label}] " if _label else ""
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, **kwargs)

            if resp.status_code not in RETRYABLE_STATUS:
                return resp  # success or a non-retryable error (4xx)

            # Retryable HTTP status
            if attempt == MAX_RETRIES:
                # Exhausted — return the failure response so callers can inspect it
                return resp

            # Honour Retry-After header (Etsy and Canva both send it on 429)
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = min(int(retry_after), MAX_BACKOFF)
                except ValueError:
                    wait = min(BACKOFF_BASE ** (attempt + 1), MAX_BACKOFF)
            else:
                wait = min(BACKOFF_BASE ** (attempt + 1), MAX_BACKOFF)

            print(
                f"  {label}HTTP {resp.status_code} — "
                f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
            )
            time.sleep(wait)

        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                raise

            wait = min(BACKOFF_BASE ** (attempt + 1), MAX_BACKOFF)
            print(
                f"  {label}Connection error — "
                f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES}): {exc}"
            )
            time.sleep(wait)

    # Should never reach here, but satisfy the type checker
    if last_exc:
        raise last_exc
    raise requests.ConnectionError("retry_request: exhausted without response")


# ── Convenience wrappers ──────────────────────────────────────────────────────

def rget(url: str, **kwargs: Any) -> requests.Response:
    return retry_request("GET", url, **kwargs)


def rpost(url: str, **kwargs: Any) -> requests.Response:
    return retry_request("POST", url, **kwargs)


def rput(url: str, **kwargs: Any) -> requests.Response:
    return retry_request("PUT", url, **kwargs)
