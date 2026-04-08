"""
Etsy OAuth 1.0a helper.
Handles signature generation for the three-legged OAuth flow.

Etsy uses OAuth 1.0a (not 2.0). The flow:
1. Get temporary request token
2. Redirect user to Etsy to authorize
3. Exchange request token for access token (after user authorizes)
4. Use access token for API calls

Once you have a long-lived access token, you store it and skip steps 1-3.
"""

import time
import random
import hashlib
import hmac
import base64
import urllib.parse
import secrets


def generate_nonce(length: int = 32) -> str:
    """Generate a random nonce for OAuth signature."""
    return secrets.token_hex(length)


def url_encode_params(params: dict) -> str:
    """Sort and percent-encode all OAuth parameters."""
    sorted_params = sorted(params.items())
    return "&".join(f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
                    for k, v in sorted_params)


def generate_signature(method: str, url: str, params: dict, consumer_secret: str, token_secret: str = "") -> str:
    """
    Generate HMAC-SHA1 OAuth 1.0a signature.

    Signature base string format:
    METHOD&url_encoded&sorted_param_string
    """
    # Sort and encode params
    param_string = url_encode_params(params)

    # Signature base string
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        param_string,
    ])

    # Signing key = consumer_secret&token_secret
    signing_key = f"{consumer_secret}&{token_secret}"

    # HMAC-SHA1
    hashed = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    )
    return base64.b64encode(hashed.digest()).decode("utf-8")


def build_authorization_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    oauth_token: str = "",
    oauth_secret: str = "",
    extra_params: dict = None,
) -> str:
    """
    Build a complete OAuth 1.0a Authorization header value.
    Includes all required OAuth parameters with correct signature.
    """
    timestamp = str(int(time.time()))
    nonce = generate_nonce()

    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_version": "1.0",
        "oauth_nonce": nonce,
    }

    if oauth_token:
        params["oauth_token"] = oauth_token

    if extra_params:
        params.update(extra_params)

    # Generate signature
    signature = generate_signature(method, url, params, consumer_secret, oauth_secret)
    params["oauth_signature"] = signature

    # Build Authorization header
    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(str(k), safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(params.items())
    )
    return auth_header


def build_signed_params(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    oauth_token: str = "",
    oauth_secret: str = "",
    extra_params: dict = None,
) -> dict:
    """
    Build a dict of all params including the OAuth signature.
    Useful for POST bodies where params go in the request body, not header.
    """
    timestamp = str(int(time.time()))
    nonce = generate_nonce()

    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_version": "1.0",
        "oauth_nonce": nonce,
    }

    if oauth_token:
        params["oauth_token"] = oauth_token

    if extra_params:
        params.update(extra_params)

    # Generate signature over all params including extras
    signature = generate_signature(method, url, params, consumer_secret, oauth_secret)
    params["oauth_signature"] = signature

    return params
