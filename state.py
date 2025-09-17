import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LAST_SYNC_FILE = os.path.join(DATA_DIR, "last_sync.json")


def _default_since_days_ago(days: int = 7) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def read_last_sync() -> Dict[str, str]:
    # Backward-compatibility: allow legacy root file if data path missing
    if not os.path.exists(LAST_SYNC_FILE):
        legacy = os.path.join(BASE_DIR, "last_sync.json")
        if os.path.exists(legacy):
            try:
                with open(legacy, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {str(k): str(v) for k, v in data.items()}
            except Exception:
                return {}
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
    # Optional override to force a backfill window for this run only
    override_days = (os.getenv("LM_OVERRIDE_SINCE_DAYS", "").strip() or None)
    if override_days is not None:
        try:
            days = int(override_days)
            if days > 0:
                return _default_since_days_ago(days)
        except ValueError:
            pass
    state = read_last_sync()
    return state.get(account_id) or _default_since_days_ago(7)


def write_last_sync(updates: Dict[str, str]) -> None:
    state = read_last_sync()
    state.update(updates)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


