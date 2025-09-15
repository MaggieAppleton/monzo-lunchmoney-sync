# Monzo → Lunch Money Sync Script

## Overview

This script fetches recent transactions from the Monzo API and pushes them into the Lunch Money API. It is intended to be run locally on macOS via a scheduled cron job every morning at 6am.

The goal is to keep shared finances up-to-date in Lunch Money without relying on third-party services or cloud infrastructure.

## Requirements

### Functional

- Authenticate with the Monzo API using OAuth 2.0 (client ID, client secret, refresh token).
- Refresh the Monzo access token as needed.
- Fetch all Monzo transactions since the last sync.
- Convert transactions into the format expected by the [Lunch Money `create transaction` API](https://lunchmoney.dev/#create-transaction).
- Send transactions to Lunch Money.
- Store the last sync timestamp locally (e.g., in a JSON file).

### Non-functional

- Store sensitive credentials in a `.env` file (never hardcoded).
- Log basic activity (number of transactions synced, errors).
- Never log sensitive data like tokens or full transaction details.
- Designed for macOS, run via cron at `0 6 * * *` (6am daily).

### Tech Stack

- **Language:** Python 3.x
- **Dependencies:**
  - `requests` (HTTP calls)
  - `python-dotenv` (load secrets from `.env`)
- **Local data:**
  - `last_sync.json` to persist the timestamp of the last synced transaction

---

## Environment Variables

Stored in `.env` (never committed to git):
MONZO_CLIENT_ID=your_client_id
MONZO_CLIENT_SECRET=your_client_secret
MONZO_REFRESH_TOKEN=your_refresh_token
LUNCHMONEY_ACCESS_TOKEN=your_lunchmoney_token
MONZO_ACCOUNT_ID=your_account_id

---

## Script Flow

1. **Load environment variables**  
   Read credentials from `.env`.

2. **Refresh Monzo access token**  
   POST request to Monzo OAuth endpoint with refresh token → get new `access_token`.

3. **Load last sync timestamp**  
   If `last_sync.json` exists, use its timestamp.  
   Otherwise, default to e.g. 7 days ago.

4. **Fetch Monzo transactions**  
   GET request from Monzo API:  
   `https://api.monzo.com/transactions?account_id={MONZO_ACCOUNT_ID}&since={timestamp}`

5. **Transform transactions**  
   For each Monzo transaction:

   - Extract date, amount, merchant name, category, notes.
   - Convert amount from pence → pounds.
   - Map to Lunch Money schema.

   Example Lunch Money format:

   ```json
   {
   	"date": "2025-09-14",
   	"amount": 12.5,
   	"payee": "Pret A Manger",
   	"currency": "GBP",
   	"category_id": null,
   	"notes": "Synced from Monzo"
   }
   ```

6. Send to Lunch Money
   POST batch of transactions to:
   https://dev.lunchmoney.app/v1/transactions

7. Update last sync file
   Save the timestamp of the newest synced transaction to last_sync.json.

8. Log result
   Print summary: Synced 8 transactions on 2025-09-14.

## Error Handling

- If Monzo token refresh fails → log and exit.
- If Lunch Money API call fails → log and exit.
- Script should fail safely (no partial duplicate entries).

## Draft Python Implementation

```python
import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONZO_CLIENT_ID = os.getenv("MONZO_CLIENT_ID")
MONZO_CLIENT_SECRET = os.getenv("MONZO_CLIENT_SECRET")
MONZO_REFRESH_TOKEN = os.getenv("MONZO_REFRESH_TOKEN")
MONZO_ACCOUNT_ID = os.getenv("MONZO_ACCOUNT_ID")
LUNCHMONEY_ACCESS_TOKEN = os.getenv("LUNCHMONEY_ACCESS_TOKEN")

LAST_SYNC_FILE = "last_sync.json"


def refresh_monzo_token():
    url = "https://api.monzo.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": MONZO_CLIENT_ID,
        "client_secret": MONZO_CLIENT_SECRET,
        "refresh_token": MONZO_REFRESH_TOKEN,
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def load_last_sync():
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE, "r") as f:
            return json.load(f)["last_sync"]
    else:
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        return week_ago


def save_last_sync(timestamp):
    with open(LAST_SYNC_FILE, "w") as f:
        json.dump({"last_sync": timestamp}, f)


def fetch_monzo_transactions(token, since):
    url = f"https://api.monzo.com/transactions"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"account_id": MONZO_ACCOUNT_ID, "since": since}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()["transactions"]


def transform_to_lunchmoney(txn):
    return {
        "date": txn["created"][:10],
        "amount": abs(txn["amount"]) / 100.0,  # pence → pounds
        "payee": txn.get("merchant", {}).get("name") or txn.get("description"),
        "currency": "GBP",
        "notes": "Synced from Monzo",
    }


def send_to_lunchmoney(transactions):
    url = "https://dev.lunchmoney.app/v1/transactions"
    headers = {"Authorization": f"Bearer {LUNCHMONEY_ACCESS_TOKEN}"}
    data = {"transactions": transactions}
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()


def main():
    token = refresh_monzo_token()
    since = load_last_sync()
    transactions = fetch_monzo_transactions(token, since)

    if not transactions:
        print("No new transactions to sync.")
        return

    lm_transactions = [transform_to_lunchmoney(t) for t in transactions]

    result = send_to_lunchmoney(lm_transactions)
    print(f"Synced {len(lm_transactions)} transactions.")

    newest_timestamp = max(t["created"] for t in transactions)
    save_last_sync(newest_timestamp)


if __name__ == "__main__":
    main()

```

## Cron Setup (macOS)

1. Open crontab editor: `crontab -e`

2. Add entry: `0 6 * * * /usr/bin/python3 /path/to/sync_monzo_to_lunchmoney.py >> /path/to/sync.log 2>&1`

This runs daily at 6am and logs output.

## Future Enhancements

- Add support for Barclays, Vanguard UK, and Monument.
- Map Monzo categories → Lunch Money categories.
- Deduplicate transactions if re-run.
- Add notification (e.g. email/Slack) on error.