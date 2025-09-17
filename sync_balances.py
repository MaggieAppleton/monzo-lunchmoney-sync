import os
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv

from auth import ensure_valid_auth
from monzo import fetch_account_balance, list_pots
from lunchmoney import update_asset


def parse_bool_env(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def parse_account_ids_env(raw: str) -> List[str]:
    return [a.strip() for a in (raw or "").split(",") if a.strip()]


def parse_asset_map_env(raw: str) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    if not raw:
        return mapping
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        acc, aid = pair.split(":", 1)
        acc = acc.strip()
        try:
            mapping[acc] = int(aid.strip())
        except Exception:
            continue
    return mapping


def sync_account_balances(
    access_token: str,
    account_ids: List[str],
    asset_map: Dict[str, int],
    dry_run: bool,
) -> None:
    for account_id in account_ids:
        try:
            balance_info = fetch_account_balance(access_token, account_id)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to fetch balance for {account_id}: {exc}")
            continue

        lm_asset_id = asset_map.get(account_id)
        if lm_asset_id is None:
            print(
                f"Skipping {account_id}: no LM asset mapping found (set LM_ASSET_IDS_MAP)."
            )
            continue

        balance_major = float(balance_info.get("balance", 0.0) or 0.0)
        currency = str(balance_info.get("currency") or "")

        if dry_run:
            print(
                f"{account_id}: DRY-RUN would set LM asset {lm_asset_id} balance to {balance_major:.2f} {currency}"
            )
        else:
            try:
                update_asset(int(lm_asset_id), {"balance": balance_major})
                print(
                    f"{account_id}: updated LM asset {lm_asset_id} balance to {balance_major:.2f} {currency}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: failed to update LM asset {lm_asset_id} for {account_id}: {exc}")


def sync_pot_balance(
    access_token: str,
    pot_id: str,
    lm_asset_id: int,
    dry_run: bool,
    account_ids: List[str],
) -> None:
    # Try scoping pots by each configured Monzo current account id to avoid API 400s
    target: Optional[Dict] = None
    last_error: Optional[Exception] = None
    for acc_id in account_ids:
        try:
            pots = list_pots(access_token, current_account_id=acc_id)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        for pot in pots:
            if str(pot.get("id")) == str(pot_id):
                target = pot
                break
        if target is not None:
            break

    # Fallback: unscoped pots call if not found
    if target is None:
        try:
            pots = list_pots(access_token)
            for pot in pots:
                if str(pot.get("id")) == str(pot_id):
                    target = pot
                    break
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if target is None:
        if last_error is not None:
            print(f"Warning: unable to fetch pots ({last_error}); skipping pot balance sync")
        else:
            print(f"Warning: savings pot id {pot_id} not found; skipping pot balance sync")
        return

    pot_balance_minor = int(target.get("balance", 0) or 0)
    pot_currency = str(target.get("currency") or "GBP")
    pot_balance_major = pot_balance_minor / 100.0

    if dry_run:
        print(
            f"pot {pot_id}: DRY-RUN would set LM asset {lm_asset_id} balance to {pot_balance_major:.2f} {pot_currency}"
        )
    else:
        try:
            update_asset(int(lm_asset_id), {"balance": float(pot_balance_major)})
            print(
                f"pot {pot_id}: updated LM asset {lm_asset_id} balance to {pot_balance_major:.2f} {pot_currency}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to update LM savings asset {lm_asset_id}: {exc}")


def main() -> int:
    load_dotenv()

    dry_run = parse_bool_env(os.getenv("DRY_RUN", ""))

    account_ids = parse_account_ids_env(os.getenv("MONZO_ACCOUNT_IDS", ""))
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty.")
        return 1

    asset_map = parse_asset_map_env(os.getenv("LM_ASSET_IDS_MAP", ""))
    # Require mappings for all configured accounts to avoid posting to cash
    missing = [acc for acc in account_ids if acc not in asset_map]
    if missing:
        print(
            "LM_ASSET_IDS_MAP is missing mappings for these Monzo account_ids: "
            + ", ".join(missing)
        )
        return 1

    try:
        access_token = ensure_valid_auth()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to get Monzo access token: {exc}")
        return 1

    sync_account_balances(access_token, account_ids, asset_map, dry_run)

    pot_id = os.getenv("MONZO_SAVINGS_POT_ID") or ""
    lm_savings_asset_id_env = os.getenv("LM_SAVINGS_ASSET_ID") or ""
    if pot_id:
        try:
            lm_savings_asset_id = int(lm_savings_asset_id_env)
        except Exception:
            lm_savings_asset_id = None
        if lm_savings_asset_id is None:
            print(
                "MONZO_SAVINGS_POT_ID is set but LM_SAVINGS_ASSET_ID is missing/invalid; skipping pot balance sync"
            )
        else:
            sync_pot_balance(access_token, pot_id, lm_savings_asset_id, dry_run, account_ids)

    return 0


if __name__ == "__main__":
    sys.exit(main())


