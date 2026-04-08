#!/usr/bin/env python3
"""
Etsy OAuth Authorization Script.

Run this once to obtain a long-lived Etsy access token.
The token is stored in your .env file automatically.

Usage:
    python -m src.marketplaces.etsy_auth

Prerequisites:
    1. Create an Etsy developer app at https://developers.etsy.com
    2. Get your Consumer Key and Consumer Secret
    3. Set your app's OAuth Callback URL to http://localhost:8765
       (any URL works for the manual flow — we intercept it locally)
"""

import sys
import os
import urllib.parse
import urllib.request
import http.server
import threading
import time
import json
import secrets

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.marketplaces.etsy_oauth import build_signed_params


# ── Configuration ───────────────────────────────────────────────────────────────

ETSY_BASE_URL = "https://api.etsy.com"
REQUEST_TOKEN_URL = f"{ETSY_BASE_URL}/v3/oauth/request_token"
AUTHORIZE_URL = f"{ETSY_BASE_URL}/v3/oauth/authorize"
ACCESS_TOKEN_URL = f"{ETSY_BASE_URL}/v3/oauth/access_token"

# ── .env helpers ────────────────────────────────────────────────────────────────

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")


def load_env() -> dict:
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def save_env(values: dict) -> None:
    env = load_env()
    env.update(values)
    with open(ENV_PATH, "w") as f:
        for key, val in sorted(env.items()):
            if val:
                f.write(f'{key}="{val}"\n')
    print(f"Saved to {ENV_PATH}")


# ── OAuth flow ─────────────────────────────────────────────────────────────────

class OAuthInterceptServer(http.server.BaseHTTPRequestHandler):
    """Lightweight HTTP server to intercept the OAuth callback."""

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "oauth_verifier" in query:
            self.server.oauth_verifier = query["oauth_verifier"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization successful!</h1><p>You can close this window and return to the terminal.</p></body></html>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Bad request")

    def log_message(self, format, *args):
        pass  # Suppress request logging


def start_callback_server(port: int = 8765) -> tuple[threading.Thread, int]:
    """Start the OAuth callback server on a port."""
    server = http.server.HTTPServer(("localhost", port), OAuthInterceptServer)
    server.oauth_verifier = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def get_request_token(consumer_key: str, consumer_secret: str, callback: str) -> tuple[str, str]:
    """Step 1: Get a temporary request token from Etsy."""
    params = build_signed_params(
        method="GET",
        url=REQUEST_TOKEN_URL,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        extra_params={"oauth_callback": callback},
    )

    query_string = "&".join(f'{urllib.parse.quote(k)}={urllib.parse.quote(v)}' for k, v in params.items())
    url = f"{REQUEST_TOKEN_URL}?{query_string}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Templar/1.0")

    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")

    parsed = urllib.parse.parse_qs(body)
    return parsed["oauth_token"][0], parsed["oauth_token_secret"][0]


def get_access_token(
    consumer_key: str,
    consumer_secret: str,
    oauth_token: str,
    oauth_secret: str,
    oauth_verifier: str,
) -> tuple[str, str]:
    """Step 3: Exchange request token + verifier for access token."""
    params = build_signed_params(
        method="GET",
        url=ACCESS_TOKEN_URL,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        oauth_token=oauth_token,
        oauth_secret=oauth_secret,
        extra_params={"oauth_verifier": oauth_verifier},
    )

    query_string = "&".join(f'{urllib.parse.quote(k)}={urllib.parse.quote(v)}' for k, v in params.items())
    url = f"{ACCESS_TOKEN_URL}?{query_string}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Templar/1.0")

    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")

    parsed = urllib.parse.parse_qs(body)
    return parsed["oauth_token"][0], parsed["oauth_token_secret"][0]


def get_etsy_user_info(consumer_key: str, consumer_secret: str, access_token: str, access_secret: str) -> dict:
    """Verify the access token by fetching user info."""
    url = f"{ETSY_BASE_URL}/v3/application/user"
    params = build_signed_params(
        method="GET",
        url=url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        oauth_token=access_token,
        oauth_secret=access_secret,
    )

    query_string = "&".join(f'{urllib.parse.quote(k)}={urllib.parse.quote(v)}' for k, v in params.items())
    req = urllib.request.Request(f"{url}?{query_string}")
    req.add_header("x-api-key", consumer_key)

    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Templar — Etsy OAuth Authorization")
    print("=" * 60)
    print()

    env = load_env()

    # Gather credentials
    consumer_key = env.get("ETSY_CONSUMER_KEY", "").strip('"').strip()
    consumer_secret = env.get("ETSY_CONSUMER_SECRET", "").strip('"').strip()

    if not consumer_key:
        consumer_key = input("Enter your Etsy Consumer Key: ").strip()
    if not consumer_secret:
        consumer_secret = input("Enter your Etsy Consumer Secret: ").strip()

    if not consumer_key or not consumer_secret:
        print("ERROR: Consumer Key and Consumer Secret are required.")
        print("Create an app at https://developers.etsy.com")
        sys.exit(1)

    callback_port = 8765
    callback_url = f"http://localhost:{callback_port}"

    print(f"\nCallback URL set to: {callback_url}")
    print("NOTE: In your Etsy app settings, set the OAuth Callback URL to:")
    print(f"  {callback_url}")
    print()

    # Step 1: Get request token
    print("[1/3] Getting request token from Etsy...")
    try:
        request_token, request_secret = get_request_token(consumer_key, consumer_secret, callback_url)
        print("  Got request token.")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("\nTroubleshooting:")
        print("  - Is your Consumer Key/Secret correct?")
        print("  - Is the OAuth Callback URL set in your Etsy app?")
        sys.exit(1)

    # Step 2: Get user authorization
    print("[2/3] Opening Etsy authorization page...")
    auth_url = (
        f"{AUTHORIZE_URL}?oauth_token={request_token}"
        f"&perms=listings_rw"
    )
    print(f"  Visit this URL to authorize:")
    print(f"  {auth_url}")
    print()

    # Start callback server
    server, thread = start_callback_server(callback_port)
    print(f"  Listening on {callback_url} for the callback...")

    # Try to auto-open browser
    try:
        import webbrowser
        webbrowser.open(auth_url)
        print("  Opened in your browser.")
    except Exception:
        pass

    print()
    print("  After you authorize, Etsy will redirect you back here.")
    print("  Waiting...", end="", flush=True)

    # Poll for callback
    start = time.time()
    while server.oauth_verifier is None:
        time.sleep(0.5)
        print(".", end="", flush=True)
        if time.time() - start > 300:  # 5 minute timeout
            print("\n\nTIMEOUT: Authorization took too long. Please try again.")
            sys.exit(1)

    oauth_verifier = server.oauth_verifier
    server.shutdown()
    print(f"\n  Got verifier: {oauth_verifier[:20]}...")

    # Step 3: Exchange for access token
    print("[3/3] Exchanging for access token...")
    try:
        access_token, access_secret = get_access_token(
            consumer_key, consumer_secret,
            request_token, request_secret,
            oauth_verifier,
        )
        print("  Got access token!")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Step 4: Verify the token
    print("\nVerifying token by fetching your Etsy user info...")
    try:
        user_info = get_etsy_user_info(consumer_key, consumer_secret, access_token, access_secret)
        user_id = user_info.get("user_id", "?")
        login_name = user_info.get("login_name", "?")
        shop_id = user_info.get("shop_id", "")
        print(f"  Authenticated as: {login_name} (user_id: {user_id})")
        if shop_id:
            print(f"  Shop ID: {shop_id}")
    except Exception as e:
        print(f"  WARNING: Could not verify token — {e}")
        print("  Token may still be valid. Check manually at developers.etsy.com")
        user_id = "?"
        login_name = "?"
        shop_id = input("Enter your Shop ID manually (or press Enter to skip): ").strip()

    # Save to .env
    print("\nSaving credentials to .env...")
    save_env({
        "ETSY_CONSUMER_KEY": consumer_key,
        "ETSY_CONSUMER_SECRET": consumer_secret,
        "ETSY_ACCESS_TOKEN": access_token,
        "ETSY_ACCESS_SECRET": access_secret,
        "ETSY_SHOP_ID": shop_id,
    })

    print()
    print("=" * 60)
    print("SUCCESS! Etsy OAuth is configured.")
    print()
    print("Your .env now contains:")
    print("  ETSY_CONSUMER_KEY     = [set]")
    print("  ETSY_CONSUMER_SECRET   = [set]")
    print("  ETSY_ACCESS_TOKEN     = [set]")
    print("  ETSY_ACCESS_SECRET    = [set]")
    print(f"  ETSY_SHOP_ID           = {shop_id or '[not found — check manually]'}")
    print()
    print("Etsy is now enabled in Templar. Run `python -m src` to start.")
    print("=" * 60)


if __name__ == "__main__":
    main()
