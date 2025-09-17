import os
import json
import sys
import unicodedata
import argparse
from datetime import datetime, timezone
from typing import Dict, List
from dotenv import load_dotenv

from monzo import fetch_transactions, fetch_account_balance, list_pots
from auth import refresh_access_token
from state import get_since_for_account, write_last_sync
from transform import batch_transform
from lunchmoney import create_transactions, list_categories, list_transactions, update_asset


def _normalize_category_name(name: str) -> str:
    """Normalize a Lunch Money category name for comparison.

    - Removes emoji/symbols by keeping only alphanumerics and spaces
    - Collapses whitespace and lowercases
    Examples:
      "🥬 Groceries" -> "groceries"
      "Pubs and Restaurants" -> "pubs and restaurants"
    """
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name.strip())
    buf = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            buf.append(ch)
    joined = "".join(buf).lower()
    return " ".join(joined.split())


def _parse_since_date_to_iso(start_date: str) -> str:
    """Convert YYYY-MM-DD to ISO8601 at UTC midnight with Z suffix.

    Example: "2025-01-01" -> "2025-01-01T00:00:00Z"
    """
    dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    return dt.isoformat().replace("+00:00", "Z")


def main() -> int:
    load_dotenv()
    dry_run = os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on", "y"}

    parser = argparse.ArgumentParser(description="Sync Monzo transactions into Lunch Money")
    parser.add_argument(
        "--since",
        type=str,
        default="",
        help="Backfill start date in YYYY-MM-DD (UTC midnight)",
    )
    parser.add_argument(
        "--before",
        type=str,
        default="",
        help="End date in YYYY-MM-DD (UTC midnight)",
    )
    args = parser.parse_args()

    since_override_iso = None
    if args.since.strip():
        try:
            since_override_iso = _parse_since_date_to_iso(args.since.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"Invalid --since date (expected YYYY-MM-DD): {exc}")
            return 2
            
    before_override_iso = None
    if args.before.strip():
        try:
            before_override_iso = _parse_since_date_to_iso(args.before.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"Invalid --before date (expected YYYY-MM-DD): {exc}")
            return 2
    account_ids_env = os.getenv("MONZO_ACCOUNT_IDS", "")
    account_ids: List[str] = [a.strip() for a in account_ids_env.split(",") if a.strip()]
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty.")
        return 1

    # Use OAuth2 flow to get access token
    try:
        from auth import ensure_valid_auth
        access_token = ensure_valid_auth()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to get Monzo access token: {exc}")
        return 1

    totals_by_account: Dict[str, int] = {}
    posted_by_account: Dict[str, int] = {}
    monzo_ids_set = set(account_ids)
    bank_transfer_category_id_env = os.getenv("LM_CATEGORY_BANK_TRANSFER_ID")
    bank_transfer_category_id = (
        int(bank_transfer_category_id_env) if bank_transfer_category_id_env else None
    )
    savings_pot_id = os.getenv("MONZO_SAVINGS_POT_ID") or None
    lm_savings_asset_id_env = os.getenv("LM_SAVINGS_ASSET_ID")
    lm_savings_asset_id = int(lm_savings_asset_id_env) if lm_savings_asset_id_env else None

    # Optional mapping of Monzo account_id -> Lunch Money asset_id
    # Example: LM_ASSET_IDS_MAP="acc_1:123,acc_2:456,acc_3:789"
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
    # Enforce asset mapping for all configured accounts to prevent cash transactions
    missing_assets = [acc for acc in account_ids if acc not in asset_map]
    if missing_assets:
        print(
            "LM_ASSET_IDS_MAP is missing mappings for these Monzo account_ids: "
            + ", ".join(missing_assets)
        )
        return 1
    # Optional labels for Monzo accounts to phrase mirror notes nicely
    # Example: MONZO_ACCOUNT_LABELS="acc_personal:personal,acc_joint:joint"
    raw_label_map = os.getenv("MONZO_ACCOUNT_LABELS", "")
    account_labels: Dict[str, str] = {}
    if raw_label_map:
        for pair in raw_label_map.split(","):
            if ":" in pair:
                acc, label = pair.split(":", 1)
                acc = acc.strip()
                label = label.strip()
                if acc and label:
                    account_labels[acc] = label
    # Optional Monzo -> Lunch Money category map (from category_map.json in repo root)
    category_map_path = os.path.join(os.path.dirname(__file__), "category_map.json")
    category_map: Dict[str, int] = {}
    if os.path.exists(category_map_path):
        try:
            with open(category_map_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
                if isinstance(raw, dict):
                    # If values are not ints, we will resolve names to ids below
                    # First, attempt direct int mapping for any numeric values
                    numeric_map: Dict[str, int] = {}
                    name_keys: Dict[str, str] = {}
                    for k, v in raw.items():
                        key = str(k)
                        if key:
                            try:
                                numeric_map[key] = int(v)
                            except Exception:
                                name_keys[key] = str(v)
                    # If any name values exist, fetch LM categories and resolve
                    if name_keys or numeric_map:
                        try:
                            cats = list_categories()
                            # Build normalization map: name (with and without emoji) -> id
                            norm_to_id: Dict[str, int] = {}
                            assignable_ids: Dict[int, bool] = {}
                            for c in cats.get("categories", []):
                                cid = c.get("id")
                                name = c.get("name") or ""
                                group_id = c.get("group_id")
                                # Treat only items with a group_id as assignable categories
                                if isinstance(cid, int) and name and group_id is not None:
                                    norm_name = _normalize_category_name(name)
                                    if norm_name:
                                        norm_to_id[norm_name] = cid
                                    assignable_ids[cid] = True
                            # Resolve names to ids
                            for monzo_key, lm_name in name_keys.items():
                                norm = _normalize_category_name(lm_name)
                                cid = norm_to_id.get(norm)
                                if isinstance(cid, int):
                                    numeric_map[monzo_key] = cid
                            # Drop any numeric ids that are not assignable (likely category groups)
                            invalid_keys = [k for k, v in numeric_map.items() if v not in assignable_ids]
                            for k in invalid_keys:
                                print(f"Warning: mapping for '{k}' points to a category group or invalid id; ignoring.")
                                numeric_map.pop(k, None)
                        except Exception as exc:  # noqa: BLE001
                            print(f"Warning: failed to resolve category names via Lunch Money API: {exc}")
                    category_map = numeric_map
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to load category_map.json: {exc}")

    for account_id in account_ids:
        since = since_override_iso or get_since_for_account(account_id)
        try:
            txns = fetch_transactions(access_token, account_id, since, before_override_iso)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to fetch transactions for {account_id}: {exc}")
            return 1
        lm_txns = batch_transform(
            txns,
            bank_transfer_category_id,
            monzo_ids_set,
            category_map=category_map or None,
            savings_pot_id=savings_pot_id,
            lm_savings_asset_id=lm_savings_asset_id,
            flip_sign=True,
        )

        # Create mirrored entries for internal transfers between Monzo accounts
        internal_mirrors = []
        for idx, t in enumerate(txns):
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
            # Build friendlier mirror notes
            source_label = account_labels.get(account_id)
            target_label = account_labels.get(cp)
            if source_label and target_label:
                phrase = f"Transfer to {target_label} from {source_label}"
            else:
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
        # Attach asset_id for all transactions that don't already have it
        asset_id = asset_map.get(account_id)
        for t in lm_txns:
            if t.get("asset_id") is None:
                t["asset_id"] = asset_id

        # Preflight existing LM external_ids for the date window and de-dup before POST
        # Determine a conservative date range to check: from 'since' date to either
        # provided 'before' or today.
        start_date = (since or "")[:10]
        if before_override_iso:
            end_date = before_override_iso[:10]
        else:
            # If we fetched any Monzo txns, use their newest created date as end
            end_date = ""
            if txns:
                newest_created = max(t.get("created", "") for t in txns)
                end_date = newest_created[:10] if newest_created else ""
            if not end_date:
                end_date = datetime.now(timezone.utc).date().isoformat()

        existing_ids: set[str] = set()
        try:
            resp = list_transactions(start_date=start_date, end_date=end_date, debit_as_negative=True)
            for row in resp.get("transactions", []):
                ext = row.get("external_id")
                if isinstance(ext, str) and ext:
                    existing_ids.add(ext)
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to preflight existing LM external_ids: {exc}")

        if existing_ids:
            before_count = len(lm_txns)
            lm_txns = [t for t in lm_txns if not t.get("external_id") or t["external_id"] not in existing_ids]
            after_count = len(lm_txns)
            skipped = before_count - after_count
            if skipped > 0:
                print(f"{account_id}: skipping {skipped} already-present transactions (by external_id)")

        # Final safety: ensure no transaction will post without an asset_id
        missing_asset_rows = [t for t in lm_txns if t.get("asset_id") is None]
        if missing_asset_rows:
            print(f"{account_id}: refusing to post {len(missing_asset_rows)} transactions without asset_id. Check LM_ASSET_IDS_MAP.")
            return 1

        totals_by_account[account_id] = len(lm_txns)

        if dry_run:
            posted_by_account[account_id] = 0
            print(f"{account_id}: DRY-RUN would post {len(lm_txns)} transactions since {since}")
            # Still fetch and print intended balance updates in dry-run
            try:
                bal = fetch_account_balance(access_token, account_id)
                asset_id_for_account = asset_map.get(account_id)
                if asset_id_for_account is not None:
                    print(f"{account_id}: DRY-RUN would set LM asset {asset_id_for_account} balance to {bal['balance']:.2f} {bal['currency']}")
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: failed to fetch Monzo balance for {account_id}: {exc}")
            continue

        # Post to Lunch Money
        try:
            result = create_transactions(lm_txns)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to POST to Lunch Money for {account_id}: {exc}")
            return 1

        created = result.get("num_objects_created")
        errors = result.get("errors")
        if created is None:
            ids = result.get("ids")
            if isinstance(ids, list):
                created = len(ids)
            else:
                txr = result.get("transactions")
                created = len(txr) if isinstance(txr, list) else 0
        if errors:
            print(f"Lunch Money returned {len(errors)} errors for {account_id} (first): {errors[0]}")
        if not created:
            print(f"Lunch Money raw response for {account_id}: {result}")
        posted_by_account[account_id] = int(created)
        print(f"{account_id}: posted {created}/{len(lm_txns)} transactions since {since}")

        # Update last_sync to newest created timestamp we attempted to send
        if txns:
            newest_created = max(t.get("created", "") for t in txns)
            if newest_created:
                write_last_sync({account_id: str(newest_created)})

        # After posting transactions, sync LM asset balance with Monzo current balance
        try:
            bal = fetch_account_balance(access_token, account_id)
            asset_id_for_account = asset_map.get(account_id)
            if asset_id_for_account is not None:
                # Lunch Money expects balance in major units
                update_asset(int(asset_id_for_account), {"balance": float(bal["balance"])})
                print(f"{account_id}: updated LM asset {asset_id_for_account} balance to {bal['balance']:.2f} {bal['currency']}")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to update LM balance for {account_id}: {exc}")

    overall = sum(totals_by_account.values())
    # Optionally sync a specific Monzo pot's balance to a separate LM asset
    if savings_pot_id and lm_savings_asset_id:
        try:
            pots = list_pots(access_token)
            target = None
            for p in pots:
                if str(p.get("id")) == str(savings_pot_id):
                    target = p
                    break
            if target is not None:
                pot_balance_minor = int(target.get("balance", 0) or 0)
                pot_currency = str(target.get("currency") or "GBP")
                pot_balance = pot_balance_minor / 100.0
                if dry_run:
                    print(
                        f"pot {savings_pot_id}: DRY-RUN would set LM asset {lm_savings_asset_id} balance to {pot_balance:.2f} {pot_currency}"
                    )
                else:
                    update_asset(int(lm_savings_asset_id), {"balance": float(pot_balance)})
                    print(
                        f"pot {savings_pot_id}: updated LM asset {lm_savings_asset_id} balance to {pot_balance:.2f} {pot_currency}"
                    )
            else:
                print(f"Warning: savings pot id {savings_pot_id} not found when syncing balance")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to sync savings pot balance: {exc}")

    if dry_run:
        print(f"DRY-RUN fetched {overall} transactions across {len(account_ids)} accounts.")
    else:
        overall_posted = sum(posted_by_account.values())
        print(
            f"Posted {overall_posted}/{overall} transactions across {len(account_ids)} accounts."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())


