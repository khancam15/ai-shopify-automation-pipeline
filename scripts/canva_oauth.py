"""
canva_oauth.py  —  One-time Canva Connect API OAuth setup
──────────────────────────────────────────────────────────
Opens your browser to the Canva OAuth consent screen, catches the
callback on a local server, exchanges the code for tokens, and saves
CANVA_CLIENT_ID / CANVA_CLIENT_SECRET / CANVA_ACCESS_TOKEN /
CANVA_REFRESH_TOKEN into your .env file.

Run (💻 HOST — Mac only, needs a browser):
    python scripts/canva_oauth.py

Prerequisites:
  1. Create a Canva app at https://www.canva.com/developers/apps
  2. Set the redirect URI to: http://localhost:8888/callback
  3. Copy Client ID and Client Secret when prompted

After running:
  • .env gains CANVA_CLIENT_ID, CANVA_CLIENT_SECRET,
    CANVA_ACCESS_TOKEN, CANVA_REFRESH_TOKEN
  • canva_image_generator.py uses these tokens automatically
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _ROOT / ".env"

REDIRECT_URI   = "http://localhost:8888/callback"
AUTH_URL       = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL      = "https://api.canva.com/rest/v1/oauth/token"
SCOPES         = "design:content:write design:content:read asset:read asset:write"


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest   = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Local callback server ─────────────────────────────────────────────────────

_auth_code: str | None = None
_server_error: str | None = None
_expected_state: str | None = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # silence default access log
        pass

    def do_GET(self):
        global _auth_code, _server_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "error" in params:
            _server_error = params["error"][0]
            self._respond("Authorization denied — you can close this tab.")
            return

        # Validate state to prevent CSRF
        returned_state = params.get("state", [None])[0]
        if returned_state != _expected_state:
            _server_error = "state_mismatch"
            self._respond("Authorization failed — state mismatch. You can close this tab.")
            return

        if "code" in params:
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


def _wait_for_code(expected_state: str) -> str:
    global _expected_state
    _expected_state = expected_state
    server = HTTPServer(("localhost", 8888), _Handler)
    server.timeout = 120
    while _auth_code is None and _server_error is None:
        server.handle_request()
    server.server_close()
    if _server_error:
        raise RuntimeError(f"OAuth error: {_server_error}")
    return _auth_code  # type: ignore[return-value]


# ── Token exchange ─────────────────────────────────────────────────────────────

def _exchange_code(client_id: str, client_secret: str, code: str, verifier: str) -> dict[str, Any]:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type":    "authorization_code",
            "client_id":     client_id,
            "client_secret": client_secret,
            "code":          code,
            "redirect_uri":  REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


# ── .env updater ───────────────────────────────────────────────────────────────

def _update_env(updates: dict[str, str]) -> None:
    existing = {}
    if ENV_PATH.exists():
        existing = dict(dotenv_values(ENV_PATH))

    existing.update(updates)

    lines: list[str] = []
    for k, v in existing.items():
        lines.append(f"{k}={v}\n")

    ENV_PATH.write_text("".join(lines), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Canva API OAuth Setup")
    print("=" * 60)
    print()
    print("Step 1: Create a Canva app (if you haven't already)")
    print("  → https://www.canva.com/developers/apps")
    print("  → Add redirect URI: http://localhost:8888/callback")
    print()

    client_id     = input("Enter your Canva Client ID: ").strip()
    client_secret = input("Enter your Canva Client Secret: ").strip()

    if not client_id or not client_secret:
        print("[error] Client ID and Secret are required.")
        sys.exit(1)

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_params = urllib.parse.urlencode({
        "client_id":             client_id,
        "redirect_uri":          REDIRECT_URI,
        "response_type":         "code",
        "scope":                 SCOPES,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    url = f"{AUTH_URL}?{auth_params}"

    print()
    print("Opening Canva authorization in your browser...")
    print(f"  {url}")
    print()
    print("Waiting for callback on http://localhost:8888/callback ...")
    webbrowser.open(url)

    try:
        code = _wait_for_code(state)
    except RuntimeError as e:
        print(f"[error] {e}")
        sys.exit(1)

    print("Authorization code received. Exchanging for tokens...")
    tokens = _exchange_code(client_id, client_secret, code, verifier)

    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")

    _update_env({
        "CANVA_CLIENT_ID":     client_id,
        "CANVA_CLIENT_SECRET": client_secret,
        "CANVA_ACCESS_TOKEN":  access_token,
        "CANVA_REFRESH_TOKEN": refresh_token,
    })

    print()
    print("✓ Tokens saved to .env")
    print(f"  CANVA_CLIENT_ID     = {client_id[:8]}...")
    print(f"  CANVA_ACCESS_TOKEN  = {access_token[:20]}...")
    if refresh_token:
        print(f"  CANVA_REFRESH_TOKEN = {refresh_token[:20]}...")
    print()
    print("Canva API setup complete. Run canva_image_generator.py to generate designs.")


if __name__ == "__main__":
    main()
