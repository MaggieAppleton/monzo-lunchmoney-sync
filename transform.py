"""
Transaction transformation utilities for Monzo to Lunch Money conversion.

This module provides functions to transform Monzo transaction data into
Lunch Money format, including category mapping, internal transfer detection,
and savings pot mirroring. It handles the core business logic for converting
between the two systems' data formats.

Key features:
- Monzo to Lunch Money transaction format conversion
- Internal transfer and pot transfer detection
- Category mapping application
- Savings pot transaction mirroring
- Idempotent external_id generation
- Batch processing with comprehensive transformation
"""
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

def _is_internal_or_pot_transfer(txn: Dict, monzo_account_ids: Set[str]) -> bool:
    """Determine if a transaction is an internal transfer or pot transfer.
    
    Args:
        txn: Monzo transaction dictionary
        monzo_account_ids: Set of known Monzo account IDs
        
    Returns:
        True if the transaction is an internal transfer or pot transfer
    """
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
    category_map: Optional[Dict[str, int]] = None,
    savings_pot_id: Optional[str] = None,
    lm_savings_asset_id: Optional[int] = None,
    flip_sign: bool = False,
) -> Dict:
    """Transform a single Monzo transaction to Lunch Money format.
    
    Args:
        txn: Monzo transaction dictionary
        bank_transfer_category_id: Lunch Money category ID for bank transfers
        monzo_account_ids: Set of known Monzo account IDs for internal transfer detection
        category_map: Optional mapping from Monzo categories to Lunch Money category IDs
        savings_pot_id: Optional Monzo savings pot ID for pot transfer detection
        lm_savings_asset_id: Optional Lunch Money asset ID for savings account
        flip_sign: Whether to flip the transaction amount sign
        
    Returns:
        Dictionary representing a Lunch Money transaction
    """
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

    # Build notes from user-entered Monzo notes and tags only; otherwise omit
    metadata = txn.get("metadata") or {}
    scheme = (txn.get("scheme") or "").lower()
    user_notes_raw = (txn.get("notes") or "").strip()
    tags_raw = metadata.get("tags")
    tags_text = ""
    if tags_raw:
        if isinstance(tags_raw, list):
            tags_text = " ".join(f"#{str(t).lstrip('#')}" for t in tags_raw if str(t).strip())
        else:
            tokens = [s for s in str(tags_raw).replace(",", " ").split() if s]
            if tokens:
                tags_text = " ".join(f"#{t.lstrip('#')}" for t in tokens)
    combined_notes = None
    if user_notes_raw and tags_text:
        combined_notes = f"{user_notes_raw} {tags_text}"
    elif user_notes_raw:
        combined_notes = user_notes_raw
    elif tags_text:
        combined_notes = tags_text

    lm: Dict = {
        "date": date_value,
        "amount": amount_value,
        "payee": payee,
        "status": "cleared",
    }
    if combined_notes:
        lm["notes"] = combined_notes

    # Provide idempotency key so retries don't duplicate
    if txn.get("id"):
        lm["external_id"] = str(txn["id"])  # Lunch Money supports external_id for de-dupe

    if bank_transfer_category_id is not None:
        if _is_internal_or_pot_transfer(txn, monzo_account_ids):
            lm["category_id"] = bank_transfer_category_id

    # Apply Monzo -> Lunch Money category mapping only for non-transfer transactions
    if category_map and lm.get("category_id") is None:
        monzo_category = txn.get("category")
        if isinstance(monzo_category, str):
            mapped = category_map.get(monzo_category)
            if isinstance(mapped, int):
                lm["category_id"] = mapped

    return lm


def batch_transform(
    txns: List[Dict],
    bank_transfer_category_id: Optional[int],
    monzo_account_ids: Set[str],
    category_map: Optional[Dict[str, int]] = None,
    savings_pot_id: Optional[str] = None,
    lm_savings_asset_id: Optional[int] = None,
    flip_sign: bool = False,
) -> List[Dict]:
    """Transform a batch of Monzo transactions to Lunch Money format.
    
    Processes multiple transactions and optionally creates mirrored entries
    for savings pot transfers. This is the main entry point for transaction
    transformation in the sync process.
    
    Args:
        txns: List of Monzo transaction dictionaries
        bank_transfer_category_id: Lunch Money category ID for bank transfers
        monzo_account_ids: Set of known Monzo account IDs for internal transfer detection
        category_map: Optional mapping from Monzo categories to Lunch Money category IDs
        savings_pot_id: Optional Monzo savings pot ID for pot transfer detection
        lm_savings_asset_id: Optional Lunch Money asset ID for savings account
        flip_sign: Whether to flip the transaction amount sign
        
    Returns:
        List of dictionaries representing Lunch Money transactions
    """
    out: List[Dict] = []
    for t in txns:
        base = transform_monzo_to_lunchmoney(
            t,
            bank_transfer_category_id,
            monzo_account_ids,
            category_map=category_map,
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
            # Friendlier label for pot mirrors
            friendly = "Transfer to savings"
            existing_notes = (base.get("notes") or "").strip()
            mirror["notes"] = f"{existing_notes} | {friendly}" if existing_notes else friendly
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


