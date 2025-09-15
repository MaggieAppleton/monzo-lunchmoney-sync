import os
from typing import Dict, List

import requests


LUNCHMONEY_API_URL = "https://api.lunchmoney.app/v1/transactions"
LUNCHMONEY_CATEGORIES_URL = "https://api.lunchmoney.app/v1/categories"


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


