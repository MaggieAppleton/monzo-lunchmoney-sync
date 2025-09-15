import os
import sys
from typing import Dict, List
from dotenv import load_dotenv

from monzo import refresh_access_token, fetch_transactions
from state import get_since_for_account, write_last_sync
from transform import batch_transform
from lunchmoney import create_transactions


def main() -> int:
    load_dotenv()
    dry_run = os.getenv("DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on", "y"}
    test_suffix = os.getenv("LM_TEST_SUFFIX", "").strip()
    flip_sign_env = os.getenv("LM_FLIP_SIGN", "").strip().lower() in {"1", "true", "yes", "on", "y"}
    account_ids_env = os.getenv("MONZO_ACCOUNT_IDS", "")
    account_ids: List[str] = [a.strip() for a in account_ids_env.split(",") if a.strip()]
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty.")
        return 1

    # Prefer a provided access token; otherwise refresh via OAuth2
    access_token = os.getenv("MONZO_ACCESS_TOKEN", "").strip()
    if not access_token:
        try:
            access_token = refresh_access_token()
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to refresh Monzo access token: {exc}")
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
    for account_id in account_ids:
        since = get_since_for_account(account_id)
        try:
            txns = fetch_transactions(access_token, account_id, since)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to fetch transactions for {account_id}: {exc}")
            return 1
        lm_txns = batch_transform(
            txns,
            bank_transfer_category_id,
            monzo_ids_set,
            savings_pot_id=savings_pot_id,
            lm_savings_asset_id=lm_savings_asset_id,
            flip_sign=flip_sign_env,
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
            base["notes"] = (base.get("notes") or "") + " | Mirror to counterparty account"
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
        # Attach asset_id if configured for this account, but do not override
        # an explicit asset_id (e.g., mirrored savings pot transaction)
        asset_id = asset_map.get(account_id)
        if asset_id is not None:
            for t in lm_txns:
                if t.get("asset_id") is None:
                    t["asset_id"] = asset_id

        # Apply optional test suffix to external_id to avoid idempotent conflicts during replays
        if test_suffix:
            for t in lm_txns:
                if t.get("external_id"):
                    t["external_id"] = f"{t['external_id']}{test_suffix}"
        totals_by_account[account_id] = len(lm_txns)

        if dry_run:
            posted_by_account[account_id] = 0
            print(f"{account_id}: DRY-RUN would post {len(lm_txns)} transactions since {since}")
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

    overall = sum(totals_by_account.values())
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


