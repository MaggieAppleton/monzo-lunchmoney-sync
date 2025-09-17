#!/usr/bin/env python3
import os
import sys
import json
from typing import Any, Dict, List

from dotenv import load_dotenv

from lunchmoney import create_transactions


def build_txn(date: str, amount: float, note: str, asset_id: int) -> Dict[str, Any]:
    # Lunch Money expects expenses as positive and income as negative.
    # Interest is income, so send a negative amount. Use absolute value for idempotency key.
    abs_amount = abs(float(amount))
    pence = int(round(abs_amount * 100))
    ext = f"monzo_pot_interest:{date[:7]}:{pence}"
    return {
        "date": date,
        "amount": -abs_amount,
        "payee": "Monzo Savings Interest",
        "notes": note or "Monzo Savings Interest",
        "asset_id": asset_id,
        "external_id": ext,
        "category_id": None,
        "status": "cleared",
    }


def main() -> int:
    load_dotenv()

    savings_asset_env = os.getenv("LM_SAVINGS_ASSET_ID")
    if not savings_asset_env:
        print("LM_SAVINGS_ASSET_ID is not set.")
        return 1
    asset_id = int(savings_asset_env)

    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "data", "interest.json")
    if not os.path.exists(path):
        # Backward-compatibility: fall back to repo-root interest.json
        legacy = os.path.join(base_dir, "interest.json")
        if os.path.exists(legacy):
            path = legacy
        else:
            print("interest.json not found.")
            return 1

    with open(path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        print("interest.json must be a JSON array.")
        return 1

    txns: List[Dict[str, Any]] = []
    for e in entries:
        date = e.get("date")
        amount = e.get("amount")
        note = e.get("note") or ""
        if not date or amount is None:
            continue
        try:
            amt_float = float(amount)
        except Exception:
            continue
        txns.append(build_txn(date, amt_float, note, asset_id))

    if not txns:
        print("No entries to post.")
        return 0

    if os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on", "y"}:
        print("DRY RUN - would post:")
        for t in txns:
            print(f"  {t['date']} | £{t['amount']:.2f} | {t['payee']} | ext={t['external_id']} | asset={t['asset_id']}")
        return 0

    res = create_transactions(txns)
    created = res.get("num_objects_created")
    if created is None:
        ids = res.get("ids")
        created = len(ids) if isinstance(ids, list) else 0
    print(f"Posted {created}/{len(txns)} interest entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


