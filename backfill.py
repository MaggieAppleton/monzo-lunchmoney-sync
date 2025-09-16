#!/usr/bin/env python3
"""
Backfill script to sync Monzo transactions in 30-day chunks.
This helps work around Monzo's API limit of 365 days per request.
"""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Start from today and work backwards to this date
START_DATE = "2024-01-01"

def main():
    # Load environment variables
    load_dotenv()
    
    # Parse start date
    start = datetime.strptime(START_DATE, "%Y-%m-%d").replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    
    # Get today at midnight UTC
    now = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    # Work backwards in 30-day chunks
    current = now
    while current > start:
        chunk_start = max(current - timedelta(days=30), start)
        date_str = chunk_start.strftime("%Y-%m-%d")
        
        print(f"\n{'='*80}")
        print(f"Syncing chunk from {date_str} to {current.strftime('%Y-%m-%d')}")
        print(f"{'='*80}\n")
        
        # Run the sync script with this date range
        try:
            subprocess.run(
                ["python", "sync.py", f"--since={date_str}"],
                check=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error syncing chunk: {e}")
            return 1
        
        # Move to next chunk
        current = chunk_start
    
    print("\nBackfill complete!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())