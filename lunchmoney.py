import os
from typing import Dict, List

import requests


LUNCHMONEY_API_URL = "https://api.lunchmoney.app/v1/transactions"


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
    payload = {"transactions": transactions}
    response = requests.post(LUNCHMONEY_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


