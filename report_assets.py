import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv

from lunchmoney import list_assets


def main() -> int:
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

    # Print compact table: id | type_name | name
    print("id,type_name,name")
    for a in assets:
        aid = a.get("id")
        name = a.get("name") or a.get("display_name") or ""
        type_name = a.get("type_name") or a.get("type") or ""
        try:
            print(f"{int(aid)},{type_name},{name}")
        except Exception:
            print(f"{aid},{type_name},{name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


