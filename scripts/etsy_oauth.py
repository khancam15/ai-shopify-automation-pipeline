"""
etsy_oauth.py  —  One-time Etsy Open API v3 OAuth setup
──────────────────────────────────────────────────────────
Runs Etsy's PKCE OAuth flow in your browser, exchanges the code for
access + refresh tokens, auto-fetches your shop ID, and saves everything
to .env.

Run (💻 HOST — Mac only, needs a browser):
    python scripts/etsy_oauth.py

Prerequisites:
  1. Create an Etsy app at https://www.etsy.com/developers/register
  2. Set the redirect URI to: http://localhost:8888/callback
  3. Copy your API Key (keystring) when prompted

After running:
  • .env gains ETSY_API_KEY, ETSY_ACCESS_TOKEN,
    ETSY_REFRESH_TOKEN, ETSY_SHOP_ID
  • etsy_api_uploader.py uses these automatically
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
from dotenv import dotenv_values

_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _ROOT / ".env"

REDIRECT_URI = "http://localhost:8888/callback"
AUTH_URL     = "https://www.etsy.com/oauth/connect"
TOKEN_URL    = "https://api.etsy.com/v3/public/oauth/token"
SCOPES       = "listings_w listings_r shops_r transactions_r"


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier  = secrets.token_urlsafe(64)
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Local callback server ─────────────────────────────────────────────────────

_auth_code: str | None    = None
_server_error: str | None = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        global _auth_code, _server_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            _server_error = params["error"][0]
            self._respond("Authorization denied — you can close this tab.")
        elif "code" in params:
            _auth_code = params["code"][0]
            self._respond("Authorization successful! You can close this tab.")
        else:
            self._respond("Unexpected response — check terminal for details.")

    def _respond(self, body: str):
        html = f"<html><body><h2>{body}</h2></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())


def _wait_for_code() -> str:
    server = HTTPServer(("localhost", 8888), _Handler)
    server.timeout = 120
    while _auth_code is None and _server_error is None:
        server.handle_request()
    server.server_close()
    if _server_error:
        raise RuntimeError(f"OAuth error: {_server_error}")
    return _auth_code  # type: ignore[return-value]


# ── Token exchange ─────────────────────────────────────────────────────────────

def _exchange_code(api_key: str, code: str, verifier: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type":    "authorization_code",
            "client_id":     api_key,
            "redirect_uri":  REDIRECT_URI,
            "code":          code,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _fetch_shop_id(api_key: str, access_token: str) -> str:
    resp = requests.get(
        "https://openapi.etsy.com/v3/application/users/me/shops",
        headers={
            "x-api-key":     api_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to fetch shop ID ({resp.status_code}): {resp.text}")
    data = resp.json()
    shops = data.get("results", [data]) if "results" in data else [data]
    if not shops:
        raise RuntimeError("No shop found for this Etsy account.")
    return str(shops[0]["shop_id"])


# ── .env updater ───────────────────────────────────────────────────────────────

def _update_env(updates: dict[str, str]) -> None:
    existing = {}
    if ENV_PATH.exists():
        existing = dict(dotenv_values(ENV_PATH))
    existing.update(updates)
    lines = [f"{k}={v}\n" for k, v in existing.items()]
    ENV_PATH.write_text("".join(lines), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Etsy Open API v3 OAuth Setup")
    print("=" * 60)
    print()
    print("Step 1: Register an Etsy app (if you haven't already)")
    print("  → https://www.etsy.com/developers/register")
    print("  → Callback URL: http://localhost:8888/callback")
    print()

    api_key = input("Enter your Etsy API Key (keystring): ").strip()
    if not api_key:
        print("[error] API Key is required.")
        sys.exit(1)

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_params = urllib.parse.urlencode({
        "response_type":         "code",
        "redirect_uri":          REDIRECT_URI,
        "scope":                 SCOPES,
        "client_id":             api_key,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    url = f"{AUTH_URL}?{auth_params}"

    print()
    print("Opening Etsy authorization in your browser...")
    print(f"  {url}")
    print()
    print("Waiting for callback on http://localhost:8888/callback ...")
    webbrowser.open(url)

    try:
        code = _wait_for_code()
    except RuntimeError as e:
        print(f"[error] {e}")
        sys.exit(1)

    print("Code received. Exchanging for tokens...")
    tokens = _exchange_code(api_key, code, verifier)

    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")

    print("Fetching your Etsy shop ID...")
    try:
        shop_id = _fetch_shop_id(api_key, access_token)
        print(f"  Shop ID: {shop_id}")
    except RuntimeError as e:
        print(f"[warning] Could not auto-fetch shop ID: {e}")
        shop_id = input("Enter your Etsy Shop ID manually: ").strip()

    _update_env({
        "ETSY_API_KEY":       api_key,
        "ETSY_ACCESS_TOKEN":  access_token,
        "ETSY_REFRESH_TOKEN": refresh_token,
        "ETSY_SHOP_ID":       shop_id,
    })

    print()
    print("✓ Tokens saved to .env")
    print(f"  ETSY_API_KEY      = {api_key[:8]}...")
    print(f"  ETSY_ACCESS_TOKEN = {access_token[:20]}...")
    print(f"  ETSY_SHOP_ID      = {shop_id}")
    print()
    print("Etsy API setup complete. Phase 5 will use these credentials automatically.")


if __name__ == "__main__":
    main()
