#!/usr/bin/env python3
"""
Script to sync transactions from a Monzo snapshot to Lunch Money.
This reads from the local snapshot file instead of hitting the Monzo API.
"""
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv

from transform import batch_transform
from lunchmoney import create_transactions, list_transactions

def group_by_month(transactions: List[Dict]) -> Dict[str, List[Dict]]:
    """Group transactions by YYYY-MM."""
    months = {}
    for t in transactions:
        # Use created date for grouping
        created = t.get("created", "")
        if not created:
            continue
        # Extract YYYY-MM
        month_key = created[:7]  # "2025-01" from "2025-01-15T..."
        months.setdefault(month_key, []).append(t)
    return months

def get_existing_monzo_ids(
    start_date: str,
    end_date: str,
) -> Set[str]:
    """Get set of external_ids for existing Monzo transactions in Lunch Money."""
    try:
        result = list_transactions(start_date, end_date)
        existing = set()
        for txn in result.get("transactions", []):
            ext_id = txn.get("external_id")
            if ext_id and ext_id.startswith("tx_"):
                existing.add(ext_id)
        return existing
    except Exception as e:
        print(f"Warning: Failed to fetch existing transactions: {e}")
        return set()

def sync_month(
    transactions: List[Dict],
    month: str,
    account_id: str,
    monzo_ids_set: set,
    asset_map: Dict[str, int],
    existing_ids: Set[str],
    bank_transfer_category_id: Optional[int] = None,
    savings_pot_id: Optional[str] = None,
    lm_savings_asset_id: Optional[int] = None,
    dry_run: bool = False
) -> int:
    """
    Sync one month of transactions to Lunch Money.
    Returns number of transactions posted.
    """
    print(f"\nProcessing {month} for account {account_id}:")
    print(f"Found {len(transactions)} transactions")
    
    # Filter out transactions that already exist
    new_txns = [
        t for t in transactions 
        if t.get("id") not in existing_ids
    ]
    
    if len(new_txns) < len(transactions):
        print(f"Skipping {len(transactions) - len(new_txns)} existing transactions")
    
    if not new_txns:
        print("No new transactions to sync")
        return 0
    
    # Transform for Lunch Money
    lm_txns = batch_transform(
        new_txns,
        bank_transfer_category_id,
        monzo_ids_set,
        savings_pot_id=savings_pot_id,
        lm_savings_asset_id=lm_savings_asset_id,
        flip_sign=True,
    )

    # Create mirrored entries for internal transfers between Monzo accounts
    internal_mirrors: List[Dict] = []
    for idx, t in enumerate(new_txns):
        scheme = (t.get("scheme") or "").lower()
        if scheme == "uk_retail_pot":
            # Pot mirrors handled in transform
            continue
        cp = (t.get("counterparty") or {}).get("account_id")
        if not cp or cp not in monzo_ids_set or cp == account_id:
            continue
        target_asset_id = asset_map.get(cp)
        if target_asset_id is None:
            continue
        base = dict(lm_txns[idx])
        # Mirror notes
        phrase = "Transfer between Monzo accounts"
        existing_notes = (base.get("notes") or "").strip()
        base["notes"] = f"{existing_notes} | {phrase}" if existing_notes else phrase
        # Flip sign for the mirrored leg
        if isinstance(base.get("amount"), (int, float)):
            base["amount"] = -float(base["amount"])
        if bank_transfer_category_id is not None:
            base["category_id"] = bank_transfer_category_id
        if base.get("external_id"):
            base["external_id"] = f"{base['external_id']}:mirror_internal:{cp}"
        base["asset_id"] = target_asset_id
        internal_mirrors.append(base)
    if internal_mirrors:
        lm_txns.extend(internal_mirrors)
    
    # Add asset IDs (required)
    asset_id = asset_map.get(account_id)
    for t in lm_txns:
        if t.get("asset_id") is None:
            t["asset_id"] = asset_id
    # Refuse to proceed if any asset is missing
    missing_asset_rows = [t for t in lm_txns if t.get("asset_id") is None]
    if missing_asset_rows:
        print("Refusing to post transactions without asset_id. Check LM_ASSET_IDS_MAP.")
        return 0
    
    if dry_run:
        print("DRY RUN - would post transactions:")
        for t in lm_txns:
            date = t.get("date", "")
            amount = float(t.get("amount", 0))
            payee = t.get("payee", "")
            asset_id = t.get("asset_id", "no asset")
            print(f"  {date} | £{amount:>8.2f} | {payee} | Asset: {asset_id}")
        return 0
    
    # Post to Lunch Money
    try:
        result = create_transactions(lm_txns)
        created = result.get("num_objects_created")
        if created is None:
            ids = result.get("ids")
            if isinstance(ids, list):
                created = len(ids)
            else:
                txr = result.get("transactions")
                created = len(txr) if isinstance(txr, list) else 0
        
        print(f"Posted {created}/{len(lm_txns)} transactions")
        return created
    except Exception as e:
        print(f"Error posting to Lunch Money: {e}")
        if "already exists" not in str(e):
            raise
        return 0

def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Sync from Monzo snapshot to Lunch Money")
    parser.add_argument("--month", type=str, default="", help="Filter to month YYYY-MM (e.g., 2024-08)")
    args = parser.parse_args()
    
    # Get account IDs and asset mapping
    account_ids_env = os.getenv("MONZO_ACCOUNT_IDS", "")
    account_ids = [a.strip() for a in account_ids_env.split(",") if a.strip()]
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty.")
        return 1
    
    # Get asset ID mapping
    raw_asset_map = os.getenv("LM_ASSET_IDS_MAP", "")
    asset_map: Dict[str, int] = {}
    if raw_asset_map:
        for pair in raw_asset_map.split(","):
            if ":" in pair:
                acc, aid = pair.split(":", 1)
                acc = acc.strip()
                try:
                    asset_map[acc] = int(aid.strip())
                except ValueError:
                    pass
    
    if not asset_map:
        print("Warning: LM_ASSET_IDS_MAP is not set. Transactions will be posted without asset IDs.")
        confirm = input("Continue? (y/n): ")
        if confirm.lower().strip() != "y":
            return 1
    
    # Find most recent snapshot (prefer data/monzo_snapshots, fallback to repo root)
    base_dir = os.path.dirname(__file__)
    snapshots_dir = os.path.join(base_dir, "data")
    snapshots: List[str] = []
    if os.path.isdir(snapshots_dir):
        snapshots = [
            os.path.join(snapshots_dir, f)
            for f in os.listdir(snapshots_dir)
            if f.startswith("monzo_snapshot_") and f.endswith(".json")
        ]
    if not snapshots:
        snapshots = [
            os.path.join(base_dir, f)
            for f in os.listdir(base_dir)
            if f.startswith("monzo_snapshot_") and f.endswith(".json")
        ]
    if not snapshots:
        print("No snapshot files found!")
        return 1
    
    latest = max(snapshots, key=lambda p: os.path.basename(p))
    print(f"\nUsing snapshot: {latest}")
    
    # Load snapshot
    with open(latest, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    
    # Print summary
    print("\nSnapshot info:")
    fetched_at = snapshot.get("metadata", {}).get("fetched_at", "unknown")
    print(f"Fetched at: {fetched_at}")
    
    monzo_ids_set = set(account_ids)
    dry_run = os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on", "y"}
    savings_pot_id = os.getenv("MONZO_SAVINGS_POT_ID") or None
    lm_savings_asset_id_env = os.getenv("LM_SAVINGS_ASSET_ID")
    lm_savings_asset_id = int(lm_savings_asset_id_env) if lm_savings_asset_id_env else None
    
    # Get bank transfer category ID if set
    bank_transfer_category_id_env = os.getenv("LM_CATEGORY_BANK_TRANSFER_ID")
    bank_transfer_category_id = (
        int(bank_transfer_category_id_env) if bank_transfer_category_id_env else None
    )
    
    # Process each account
    total_synced = 0
    for account_id, account_data in snapshot.get("accounts", {}).items():
        if account_id not in account_ids:
            continue
            
        transactions = account_data.get("transactions", [])
        print(f"\nAccount {account_id}:")
        print(f"Total transactions: {len(transactions)}")
        
        # Group by month
        by_month = group_by_month(transactions)
        print("Transactions by month:")
        for month in sorted(by_month.keys()):
            print(f"  {month}: {len(by_month[month])}")
        
        # Sync each month
        account_synced = 0
        target_months = sorted(by_month.keys())
        if args.month:
            target_months = [m for m in target_months if m == args.month]
        for month in target_months:
            # Get existing transactions for this month
            start_date = f"{month}-01"
            end_date = f"{month}-31"  # LM API handles invalid days
            existing_ids = get_existing_monzo_ids(start_date, end_date)
            
            try:
                synced = sync_month(
                    by_month[month],
                    month,
                    account_id,
                    monzo_ids_set,
                    asset_map,
                    existing_ids,
                    bank_transfer_category_id,
                    savings_pot_id,
                    lm_savings_asset_id,
                    dry_run,
                )
                account_synced += synced
            except Exception as e:
                print(f"Error processing {month}: {e}")
                if input("Continue to next month? (y/n): ").lower().strip() != "y":
                    return 1
        
        print(f"\nAccount {account_id} complete: synced {account_synced} transactions")
        total_synced += account_synced
    
    print(f"\nAll done! Synced {total_synced} transactions")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())