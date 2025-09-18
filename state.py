"""
State management for sync operations.

This module handles persistent state storage for the sync process, primarily
tracking the last sync timestamp for each Monzo account to enable incremental
syncing. It provides functions to read and write sync state, with support
for backward compatibility with legacy file locations.

Key features:
- Per-account sync timestamp tracking
- Backward compatibility with legacy file locations
- Environment variable override for backfill operations
- Safe fallback to default time windows
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LAST_SYNC_FILE = os.path.join(DATA_DIR, "last_sync.json")


def _default_since_days_ago(days: int = 7) -> str:
    """Generate a default ISO timestamp for a given number of days ago.
    
    Args:
        days: Number of days to look back (default 7)
        
    Returns:
        ISO8601 timestamp string
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def read_last_sync() -> Dict[str, str]:
    """Read the last sync state from persistent storage.
    
    Attempts to read from the data/last_sync.json file, with fallback to
    legacy root-level last_sync.json for backward compatibility.
    
    Returns:
        Dictionary mapping account IDs to their last sync timestamps
    """
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
    """Get the 'since' timestamp for a specific account.
    
    Checks for environment variable override first, then falls back to
    stored state or default time window.
    
    Args:
        account_id: Monzo account ID to get timestamp for
        
    Returns:
        ISO8601 timestamp string for the sync start point
    """
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
    """Write updated sync state to persistent storage.
    
    Merges the provided updates with existing state and writes to
    data/last_sync.json, creating the directory if needed.
    
    Args:
        updates: Dictionary of account_id -> timestamp mappings to update
    """
    state = read_last_sync()
    state.update(updates)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


