from typing import Dict, List, Optional, Set
from datetime import datetime, timezone


def _is_internal_or_pot_transfer(txn: Dict, monzo_account_ids: Set[str]) -> bool:
    counterparty = txn.get("counterparty") or {}
    metadata = txn.get("metadata") or {}
    description = (txn.get("description") or "").lower()
    scheme = (txn.get("scheme") or "").lower()

    # Internal transfer between own Monzo accounts
    counterparty_acct = counterparty.get("account_id")
    if counterparty_acct and counterparty_acct in monzo_account_ids:
        return True

    # Pot transfers (best-effort heuristics)
    if scheme == "uk_retail_pot":
        return True
    if any(k.startswith("pot_") for k in metadata.keys()):
        return True
    if "pot" in description:
        return True

    return False


def transform_monzo_to_lunchmoney(
    txn: Dict,
    bank_transfer_category_id: Optional[int],
    monzo_account_ids: Set[str],
    savings_pot_id: Optional[str] = None,
    lm_savings_asset_id: Optional[int] = None,
    flip_sign: bool = False,
) -> Dict:
    # Date (prefer created, fallback to settled, then today)
    created_or_settled = txn.get("created") or txn.get("settled") or ""
    date_value = created_or_settled[:10] if created_or_settled else datetime.now(timezone.utc).date().isoformat()

    # Payee extraction tolerant to merchant being a string or object
    merchant_val = txn.get("merchant")
    counterparty = txn.get("counterparty") or {}
    description = txn.get("description") or ""
    payee: str = ""
    if isinstance(merchant_val, dict):
        payee = merchant_val.get("name") or ""
    # If merchant is a string (merchant id), we can't resolve the name here; fallback
    if not payee:
        payee = counterparty.get("name") or description or ""

    amount_value = float(txn.get("amount", 0)) / 100.0
    if flip_sign:
        amount_value = -amount_value

    lm: Dict = {
        "date": date_value,
        "amount": amount_value,
        "payee": payee,
        "notes": "Synced from Monzo",
        "status": "cleared",
    }

    # Provide idempotency key so retries don't duplicate
    if txn.get("id"):
        lm["external_id"] = str(txn["id"])  # Lunch Money supports external_id for de-dupe

    if bank_transfer_category_id is not None:
        if _is_internal_or_pot_transfer(txn, monzo_account_ids):
            lm["category_id"] = bank_transfer_category_id

    return lm


def batch_transform(
    txns: List[Dict],
    bank_transfer_category_id: Optional[int],
    monzo_account_ids: Set[str],
    savings_pot_id: Optional[str] = None,
    lm_savings_asset_id: Optional[int] = None,
    flip_sign: bool = False,
) -> List[Dict]:
    out: List[Dict] = []
    for t in txns:
        base = transform_monzo_to_lunchmoney(
            t,
            bank_transfer_category_id,
            monzo_account_ids,
            savings_pot_id=savings_pot_id,
            lm_savings_asset_id=lm_savings_asset_id,
            flip_sign=flip_sign,
        )
        out.append(base)

        # Mirror savings pot transfers into the savings asset if configured
        metadata = t.get("metadata") or {}
        scheme = (t.get("scheme") or "").lower()
        is_pot = scheme == "uk_retail_pot" or bool(metadata.get("pot_id"))
        if savings_pot_id and lm_savings_asset_id and is_pot and metadata.get("pot_id") == savings_pot_id:
            mirror = dict(base)
            mirror["notes"] = (base.get("notes") or "") + " | Mirror to savings pot"
            # Flip the sign for the mirrored leg
            if isinstance(base.get("amount"), (int, float)):
                mirror["amount"] = -float(base["amount"])
            # Ensure category is Bank Transfers if provided
            if bank_transfer_category_id is not None:
                mirror["category_id"] = bank_transfer_category_id
            # Use a different external_id for the mirror to avoid dupes
            if base.get("external_id"):
                mirror["external_id"] = f"{base['external_id']}:mirror_savings"
            # Route to savings asset explicitly
            mirror["asset_id"] = lm_savings_asset_id
            out.append(mirror)

    return out


