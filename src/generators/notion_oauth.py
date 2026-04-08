"""
Notion OAuth 2.0 helpers for buyer authorization.

The flow:
1. Buyer clicks "Connect Notion" on purchase confirmation
2. We redirect them to Notion's OAuth authorize URL
3. Notion redirects back to our callback with a code
4. We exchange code for access_token + refresh_token
5. We store tokens and use them to create the template database

Notion uses OAuth 2.0 (different from Etsy's OAuth 1.0a).
"""

import os
import base64
import urllib.parse
import urllib.request
import urllib.error
import json
import secrets
from typing import Optional

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_OAUTH_URL = "https://api.notion.com/v1/oauth/authorize"


class NotionOAuth:
    """
    Handles the Notion OAuth 2.0 flow for buyer authorization.

    Buyer-facing usage:
      oauth = NotionOAuth(client_id, client_secret, redirect_uri)
      auth_url = oauth.get_authorization_url(state)  # send buyer here
      tokens = oauth.exchange_code(code)  # in callback handler
      user_info = oauth.get_bot_info(tokens)  # verify workspace
      refreshed = oauth.refresh_token(refresh_token)  # when access_token expires
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("NOTION_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("NOTION_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("NOTION_REDIRECT_URI")

    @staticmethod
    def generate_state() -> str:
        """Generate a CSRF-protection state token."""
        return secrets.token_urlsafe(32)

    def get_authorization_url(self, state: str) -> str:
        """
        Build the Notion OAuth authorization URL to redirect buyers to.
        buyer must visit this URL to authorize.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        return f"{NOTION_OAUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """
        Exchange an authorization code for access + refresh tokens.
        Called in the OAuth callback handler.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("NOTION_CLIENT_ID and NOTION_CLIENT_SECRET must be set")

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("utf-8")

        payload = json.dumps({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{NOTION_API_BASE}/oauth/token",
            data=payload,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise Exception(f"Notion token exchange failed ({e.code}): {body}")

    def refresh_token(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token.
        Notion access tokens expire; refresh tokens are long-lived.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("NOTION_CLIENT_ID and NOTION_CLIENT_SECRET must be set")

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("utf-8")

        payload = json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{NOTION_API_BASE}/oauth/token",
            data=payload,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise Exception(f"Notion token refresh failed ({e.code}): {body}")

    def get_bot_info(self, access_token: str) -> dict:
        """Get the bot/user info for an authorized workspace."""
        req = urllib.request.Request(
            f"{NOTION_API_BASE}/users/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}"}

    def is_token_expired(self, response_or_error: dict) -> bool:
        """Check if a token response indicates expiration."""
        # Notion returns this in error responses when token is expired
        return response_or_error.get("error") == "invalid_token"

    def make_notion_request(
        self,
        method: str,
        path: str,
        access_token: str,
        json_data: dict = None,
    ) -> dict:
        """Make an authenticated request to the Notion API."""
        url = f"{NOTION_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        body = json.dumps(json_data).encode("utf-8") if json_data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise Exception(f"Notion API error {e.code} on {method} {path}: {body}")
