import os
from typing import Dict, List

import requests


def refresh_access_token() -> str:
    """Refresh Monzo OAuth2 access token using refresh token from env."""
    client_id = os.getenv("MONZO_CLIENT_ID")
    client_secret = os.getenv("MONZO_CLIENT_SECRET")
    refresh_token = os.getenv("MONZO_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("Missing MONZO_CLIENT_ID/SECRET/REFRESH_TOKEN in environment")

    url = "https://api.monzo.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()
    payload: Dict = response.json()
    return str(payload["access_token"]) 


def fetch_transactions(access_token: str, account_id: str, since_iso: str) -> List[Dict]:
    """Fetch Monzo transactions since a timestamp for a specific account."""
    if not access_token:
        raise ValueError("access_token is required")
    if not account_id:
        raise ValueError("account_id is required")
    params = {
        "account_id": account_id,
        "since": since_iso,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.monzo.com/transactions"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    data: Dict = response.json()
    txns = data.get("transactions", [])
    # Only include finalized (settled) and not-declined transactions
    return [t for t in txns if not t.get("declined") and t.get("settled")]


def list_accounts(access_token: str) -> List[Dict]:
    """List Monzo accounts accessible by the provided token (open accounts only)."""
    if not access_token:
        raise ValueError("access_token is required")
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.monzo.com/accounts"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data: Dict = response.json()
    accounts = data.get("accounts", [])
    return [a for a in accounts if not a.get("closed")]


