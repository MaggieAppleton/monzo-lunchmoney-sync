import os
import requests
from typing import Dict, List, Optional

class VerificationRequiredError(Exception):
    def __init__(self, message: str, start_time: Optional[str] = None, end_time: Optional[str] = None, auth_session_id: Optional[str] = None):
        super().__init__(message)
        self.start_time = start_time
        self.end_time = end_time
        self.auth_session_id = auth_session_id

def get_access_token() -> str:
    """Get a valid Monzo access token using OAuth flow.
    
    Returns:
        str: A valid access token
        
    Raises:
        ValueError: If OAuth flow fails
    """
    from auth import ensure_valid_auth
    return ensure_valid_auth()


def fetch_transactions(
    access_token: str,
    account_id: str,
    since_iso: str,
    before_iso: Optional[str] = None,
) -> List[Dict]:
    """Fetch Monzo transactions for a specific account within a time window.

    Required: since_iso. Optional: before_iso to limit the upper bound.
    """
    if not access_token:
        raise ValueError("access_token is required")
    if not account_id:
        raise ValueError("account_id is required")
    params = {
        "account_id": account_id,
        "since": since_iso,
    }
    if before_iso:
        params["before"] = before_iso
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.monzo.com/transactions"
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 403:
        # Attempt to parse verification payload
        try:
            payload = response.json()
            code = str(payload.get("code") or "")
            if code.endswith("verification_required"):
                params_obj = payload.get("params") or {}
                raise VerificationRequiredError(
                    payload.get("message") or "Verification required",
                    start_time=params_obj.get("start_time"),
                    end_time=params_obj.get("end_time"),
                    auth_session_id=params_obj.get("auth_session_id"),
                )
        except VerificationRequiredError:
            raise
        except Exception:
            pass
    try:
        response.raise_for_status()
    except requests.HTTPError as err:  # type: ignore[attr-defined]
        detail = ""
        try:
            detail = f" body={response.text[:500]}"
        except Exception:
            detail = ""
        raise requests.HTTPError(f"{err}{detail}")
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


def fetch_account_balance(access_token: str, account_id: str) -> Dict:
    """Fetch current balance for a Monzo account.

    Returns a dict with keys: balance_minor (int), currency (str), spend_today_minor (int),
    and balance (float) converted to major units.
    """
    if not access_token:
        raise ValueError("access_token is required")
    if not account_id:
        raise ValueError("account_id is required")
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.monzo.com/balance"
    params = {"account_id": account_id}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    payload: Dict = response.json()
    balance_minor = int(payload.get("balance", 0) or 0)
    spend_today_minor = int(payload.get("spend_today", 0) or 0)
    currency = str(payload.get("currency") or "GBP")
    # Convert minor units (pennies) to major units (pounds)
    balance = balance_minor / 100.0
    return {
        "balance_minor": balance_minor,
        "balance": balance,
        "currency": currency,
        "spend_today_minor": spend_today_minor,
    }


def list_pots(access_token: str, current_account_id: Optional[str] = None) -> List[Dict]:
    """List Monzo pots. Optionally scope to a current account id.

    Returns list of pot dicts as provided by Monzo API.
    """
    if not access_token:
        raise ValueError("access_token is required")
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.monzo.com/pots"
    params: Dict[str, str] = {}
    if current_account_id:
        params["current_account_id"] = current_account_id
    response = requests.get(url, headers=headers, params=params or None, timeout=30)
    response.raise_for_status()
    data: Dict = response.json()
    return data.get("pots", []) or []


