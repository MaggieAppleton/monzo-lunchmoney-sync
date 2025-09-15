import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

LAST_SYNC_FILE = "last_sync.json"


def _default_since_days_ago(days: int = 7) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def read_last_sync() -> Dict[str, str]:
    if not os.path.exists(LAST_SYNC_FILE):
        return {}
    try:
        with open(LAST_SYNC_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
            return {}
    except Exception:
        return {}


def get_since_for_account(account_id: str) -> str:
    state = read_last_sync()
    return state.get(account_id) or _default_since_days_ago(7)


def write_last_sync(updates: Dict[str, str]) -> None:
    state = read_last_sync()
    state.update(updates)
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


