import os
from typing import Dict, List
import requests

LUNCHMONEY_API_URL = "https://api.lunchmoney.app/v1/transactions"
LUNCHMONEY_CATEGORIES_URL = "https://api.lunchmoney.app/v1/categories"
LUNCHMONEY_ASSETS_URL = "https://api.lunchmoney.app/v1/assets"
LUNCHMONEY_TX_URL = "https://api.lunchmoney.app/v1/transactions/{id}"
LUNCHMONEY_ASSET_URL = "https://api.lunchmoney.app/v1/assets/{id}"

def create_transactions(transactions: List[Dict]) -> Dict:
    """Create transactions in Lunch Money.

    Expects transaction objects already in Lunch Money format. Supports idempotency
    via the `external_id` field when provided in each transaction.
    """
    if not transactions:
        return {"status": "ok", "num_objects_created": 0}

    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"transactions": transactions, "apply_rules": True}
    response = requests.post(LUNCHMONEY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def list_transactions(
    start_date: str,
    end_date: str,
    debit_as_negative: bool = True,
) -> Dict:
    """Fetch transactions from Lunch Money.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        debit_as_negative: If True, debits will be returned as negative numbers

    Returns:
        Dict containing "transactions" list and other metadata
    """
    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "debit_as_negative": "true" if debit_as_negative else "false",
    }
    response = requests.get(LUNCHMONEY_API_URL, headers=headers, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def list_categories() -> Dict:
    """Fetch categories from Lunch Money.

    Returns the raw JSON payload which typically includes keys like
    "categories" and "category_groups".
    """
    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.get(LUNCHMONEY_CATEGORIES_URL, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def list_assets(include_archived: bool = False) -> Dict:
    """Fetch assets (accounts) from Lunch Money.

    Args:
        include_archived: If True, include archived assets

    Returns:
        Raw JSON payload that includes key "assets".
    """
    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {"archived": "true" if include_archived else "false"}
    response = requests.get(LUNCHMONEY_ASSETS_URL, headers=headers, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def update_transaction(transaction_id: int, updates: Dict) -> Dict:
    """Update a transaction in Lunch Money.

    Args:
        transaction_id: The Lunch Money transaction id
        updates: Dict of fields to update, e.g., {"notes": "...", "exclude_from_totals": True, "asset_id": 123}

    Returns:
        Raw JSON response
    """
    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    url = LUNCHMONEY_TX_URL.format(id=int(transaction_id))
    payload = {"transaction": updates}
    response = requests.put(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()



def update_asset(asset_id: int, updates: Dict) -> Dict:
    """Update a Lunch Money asset (account), e.g., its balance.

    Example updates:
    {"balance": 123.45}
    {"balance": 123.45, "balance_as_of": "2025-09-17"}
    """
    access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing LUNCHMONEY_ACCESS_TOKEN in environment")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    url = LUNCHMONEY_ASSET_URL.format(id=int(asset_id))
    # Prefer PUT with {"asset": {...}} wrapper per LM API; fallback to PATCH for compatibility
    try:
        response = requests.put(url, headers=headers, json={"asset": updates}, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as err:  # type: ignore[name-defined]
        # Fallback to PATCH if PUT is not supported in the current API version
        if getattr(err.response, "status_code", None) in {404, 405, 415}:  # noqa: PLR2004
            resp2 = requests.patch(url, headers=headers, json=updates, timeout=60)
            resp2.raise_for_status()
            return resp2.json()
        raise


