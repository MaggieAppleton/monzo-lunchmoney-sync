#!/usr/bin/env python3
"""
Script to fetch and save a complete snapshot of Monzo transactions.
This takes advantage of the OAuth permissions window to fetch all historical data
and save it locally for later processing.
"""
import os
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
from monzo import fetch_transactions, VerificationRequiredError
from auth import ensure_valid_auth

def fetch_account_transactions(
    access_token: str,
    account_id: str,
    start_date: datetime,
    end_date: datetime,
    chunk_size: timedelta = timedelta(days=30)
) -> List[Dict]:
    """
    Fetch all transactions for an account in chunks to handle API limits.
    """
    all_transactions: List[Dict] = []
    current = start_date
    
    while current < end_date:
        chunk_end = min(current + chunk_size, end_date)
        print(f"  Fetching {current.date()} to {chunk_end.date()}...")
        
        # Retry loop per chunk (handles SCA and transient errors)
        max_retries = 6
        attempt = 0
        while True:
            attempt += 1
            try:
                txns = fetch_transactions(
                    access_token,
                    account_id,
                    current.isoformat().replace("+00:00", "Z"),
                    chunk_end.isoformat().replace("+00:00", "Z"),
                )
                all_transactions.extend(txns)
                print(f"    Found {len(txns)} transactions")
                break
            except VerificationRequiredError as ve:
                wait_s = 30
                print(
                    "    Monzo verification required. Please approve in the Monzo app "
                    f"(attempt {attempt}/{max_retries}). Waiting {wait_s}s before retry..."
                )
                time.sleep(wait_s)
                if attempt >= max_retries:
                    print("    Giving up on this chunk due to repeated verification requirements.")
                    break
            except Exception as e:
                # Transient error handling with backoff
                if attempt >= max_retries:
                    print(f"    Error after {attempt} attempts: {e}. Skipping this chunk.")
                    break
                backoff = min(60, 5 * attempt)
                print(f"    Error: {e}. Retrying in {backoff}s (attempt {attempt}/{max_retries})...")
                time.sleep(backoff)
        
        current = chunk_end
    
    return all_transactions

def main() -> int:
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Fetch Monzo snapshot for a date range")
    parser.add_argument("--start", type=str, default="2024-01-01", help="Start date YYYY-MM-DD (UTC)")
    parser.add_argument("--end", type=str, default="", help="End date YYYY-MM-DD (UTC, exclusive upper bound)")
    parser.add_argument("--chunk-days", type=int, default=7, help="Chunk size in days for fetching")
    args = parser.parse_args()
    
    # Get account IDs from env
    account_ids_env = os.getenv("MONZO_ACCOUNT_IDS", "")
    account_ids = [a.strip() for a in account_ids_env.split(",") if a.strip()]
    if not account_ids:
        print("MONZO_ACCOUNT_IDS is not set or empty.")
        return 1
    
    # Get fresh OAuth token
    print("\nGetting fresh OAuth token...")
    access_token = ensure_valid_auth()
    
    # Define date range
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"Invalid --start date: {e}")
        return 2
    if args.end:
        try:
            end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"Invalid --end date: {e}")
            return 2
    else:
        end_date = datetime.now(timezone.utc)
    
    if end_date <= start_date:
        print("End date must be after start date")
        return 2
    
    print(f"\nFetching transactions from {start_date.date()} to {end_date.date()} (chunk {args.chunk_days}d)")
    
    # Fetch transactions for each account
    snapshot = {
        "metadata": {
            "fetched_at": end_date.isoformat(),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        },
        "accounts": {}
    }
    
    for account_id in account_ids:
        print(f"\nAccount {account_id}:")
        transactions = fetch_account_transactions(
            access_token,
            account_id,
            start_date,
            end_date,
            chunk_size=timedelta(days=max(1, int(args.chunk_days)))
        )
        
        snapshot["accounts"][account_id] = {
            "transactions": transactions,
            "total_transactions": len(transactions)
        }
        
        print(f"Total transactions: {len(transactions)}")
    
    # Save to file with timestamp inside data/ (create if needed)
    base_dir = os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    filename = f"monzo_snapshot_{end_date.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(data_dir, filename)
    print(f"\nSaving to {filepath}...")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    
    # Print summary
    total = sum(
        len(acc["transactions"])
        for acc in snapshot["accounts"].values()
    )
    print(f"\nSnapshot complete! Saved {total} transactions across {len(account_ids)} accounts.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
