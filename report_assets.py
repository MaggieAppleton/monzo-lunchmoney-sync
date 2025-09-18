"""
Report Lunch Money assets (accounts) in CSV format.

This script fetches all active assets from Lunch Money and outputs them
in a CSV format showing key information like ID, type, name, balance,
and institution details. This is useful for identifying asset IDs needed
for configuration in the sync process.

Usage:
    python report_assets.py

The script requires LUNCHMONEY_ACCESS_TOKEN to be set in the environment
or .env file. It outputs a CSV header followed by asset data that can be
redirected to a file or piped to other tools.

Output format:
    id,type_name,name,balance,balance_as_of,institution_name,subtype
"""
import os
import sys
from typing import Any, Dict, List
from dotenv import load_dotenv
from lunchmoney import list_assets


def main() -> int:
    """Main function to fetch and display Lunch Money assets in CSV format.
    
    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    load_dotenv()

    if not os.getenv("LUNCHMONEY_ACCESS_TOKEN"):
        print("Missing LUNCHMONEY_ACCESS_TOKEN in environment (.env)")
        return 1

    try:
        data: Dict[str, Any] = list_assets(include_archived=False)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch assets: {exc}")
        return 1

    assets: List[Dict[str, Any]] = data.get("assets") or []
    if not assets:
        print("No assets returned.")
        return 0

    # Print compact table: id | type_name | name | balance | balance_as_of | institution_name | subtype
    print("id,type_name,name,balance,balance_as_of,institution_name,subtype")
    for a in assets:
        aid = a.get("id")
        name = a.get("name") or a.get("display_name") or ""
        type_name = a.get("type_name") or a.get("type") or ""
        balance = a.get("balance")
        balance_as_of = a.get("balance_as_of") or a.get("balance_update") or ""
        institution_name = a.get("institution_name") or a.get("display_institution") or ""
        subtype = a.get("subtype") or ""
        try:
            print(f"{int(aid)},{type_name},{name},{balance},{balance_as_of},{institution_name},{subtype}")
        except Exception:
            print(f"{aid},{type_name},{name},{balance},{balance_as_of},{institution_name},{subtype}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


