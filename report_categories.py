import argparse
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from dotenv import load_dotenv

from monzo import fetch_transactions, get_access_token, list_accounts
from lunchmoney import list_categories


def iso_since_days(days: int) -> str:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(0, int(days)))
    # Monzo expects ISO8601; include time and Z for UTC
    return start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def aggregate_monzo_categories(
    access_token: str, account_ids: List[str], since_iso: str
) -> Tuple[Counter, int]:
    counts: Counter = Counter()
    total = 0
    for account_id in account_ids:
        try:
            txns = fetch_transactions(access_token, account_id, since_iso)
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to fetch transactions for {account_id}: {exc}")
            continue
        for t in txns:
            total += 1
            cat = t.get("category") or "unknown"
            counts[str(cat)] += 1
    return counts, total


def print_lm_categories() -> None:
    try:
        payload = list_categories()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch Lunch Money categories: {exc}")
        return
    cats = payload.get("categories") or []
    groups_by_id = {g.get("id"): g for g in payload.get("category_groups") or []}
    print("\nLunch Money categories (id — name):")
    # sort by group, then name
    cats_sorted = sorted(cats, key=lambda c: ((c.get("group_id") or 0), str(c.get("name") or "")))
    for c in cats_sorted:
        cid = c.get("id")
        name = c.get("name")
        group_id = c.get("group_id")
        group_name = (groups_by_id.get(group_id) or {}).get("name") if group_id else None
        prefix = f"[{group_name}] " if group_name else ""
        print(f"  {cid} — {prefix}{name}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Report unique Monzo categories to help build category_map.json",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Window of days to scan from today (default: 90)",
    )
    parser.add_argument(
        "--accounts",
        type=str,
        default="",
        help="Comma-separated Monzo account_ids to scan (overrides MONZO_ACCOUNT_IDS)",
    )
    parser.add_argument(
        "--list-lm",
        action="store_true",
        help="List Lunch Money categories (name and id) to assist mapping",
    )
    args = parser.parse_args()

    if args.accounts.strip():
        account_ids: List[str] = [a.strip() for a in args.accounts.split(",") if a.strip()]
    else:
        account_ids_env = os.getenv("MONZO_ACCOUNT_IDS", "")
        account_ids = [a.strip() for a in account_ids_env.split(",") if a.strip()]
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty. Use --accounts to provide ids.")
        # Attempt to list accessible accounts to help the user
        try:
            token_preview = get_access_token()
        except Exception:
            token_preview = ""
        if token_preview:
            try:
                accts = list_accounts(token_preview)
                if accts:
                    print("Accessible Monzo accounts:")
                    for a in accts:
                        print(f"  {a.get('id')} — {a.get('type')} — {a.get('description')}")
            except Exception as exc:  # noqa: BLE001
                print(f"(Could not list accounts: {exc})")
        return 1

    try:
        access_token = get_access_token()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to get Monzo access token: {exc}")
        return 1

    since_iso = iso_since_days(args.days)
    # Show accessible accounts to verify ids quickly
    try:
        accts = list_accounts(access_token)
        if accts:
            print("Accessible Monzo accounts:")
            for a in accts:
                print(f"  {a.get('id')} — {a.get('type')} — {a.get('description')}")
    except Exception:
        pass

    counts, total = aggregate_monzo_categories(access_token, account_ids, since_iso)

    print(f"Scanned {total} transactions across {len(account_ids)} account(s) since {since_iso}.")
    print("\nMonzo categories (count — key):")
    for key, cnt in counts.most_common():
        print(f"  {cnt:5d} — {key}")

    if args.list_lm:
        print_lm_categories()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


