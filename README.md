# Monzo → Lunch Money Sync

A local Python script that syncs your Monzo bank transactions into Lunch Money. Everything runs on your computer - no cloud services to set up.

The first time you run it, it fetches all your past Monzo transactions and saves them to a local 'snapshot'. You can sync this to Lunch Money to backfill historical transactions. After that, it only fetches new ones since the last time it ran.

## Requirements

- Python 3.9+
- A Monzo developer account + client app
- A Lunch Money API key

## Setup

Create a virtual environment (this keeps the script's dependencies separate from your system):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create a file called `.env` in the main folder with your account details:

```bash
MONZO_CLIENT_ID=...
MONZO_CLIENT_SECRET=...
MONZO_ACCOUNT_IDS=acc_...,acc_...

LUNCHMONEY_ACCESS_TOKEN=...
LM_ASSET_IDS_MAP=acc_...:1234,acc_...:5678

# Optional:
LM_CATEGORY_BANK_TRANSFER_ID=123456
MONZO_SAVINGS_POT_ID=pot_000...
LM_SAVINGS_ASSET_ID=9012
MONZO_ACCOUNT_LABELS=acc_...:personal,acc_...:joint
DRY_RUN=true
```

### Getting your Monzo API keys

1. Go to the [Monzo Developers](https://developers.monzo.com/) website
2. Create a new app to get your API keys

![Make a new client app](/images/monzo1.png)

3. Fill in the form:
   - Give your app a name and description
   - Leave the logo URL blank
   - Set the redirect URL to: `http://localhost:8080/callback`
   - Set confidentiality to "Confidential"

![How to fill in the client app form](/images/monzo2.png)

### Getting your Lunch Money API key

1. Log into Lunch Money
2. Go to Settings > Developers
3. Click "Request new access token"

![How to get an API key within Lunch Money](/images/lunchmoney.png)

4. Copy the token and add it to your `.env` file

### Important notes:

- **Account IDs**: List all your Monzo accounts (personal, joint, etc.) separated by commas
- **Asset mapping**: You must tell the script which Lunch Money account each Monzo account should sync to
- **Bank transfers**: Money moves between your own accounts are marked as "Bank Transfer" if you set that category
- **Savings pots**: You can treat Monzo savings pots as separate Lunch Money accounts
- **Only real transactions**: The script only syncs completed transactions (not pending ones)
- **Category mapping**: You can create a file to automatically assign categories to your transactions

## Running the script

### Activate your virtual environment

```bash
source .venv/bin/activate
```

### Test run (recommended first)

Before syncing for real, do a test run to see what would happen:

```bash
DRY_RUN=1 python sync.py
```

This shows you what transactions would be sent to Lunch Money without actually sending them.

### Real sync

Once you're happy with the test run:

```bash
python sync.py
```

### What happens when you run it:

- **First time**: Your browser opens for Monzo login. Login via email, then open the Monzo app to approve access
- **Security**: Your login tokens are stored in your computer's keychain (not in files)
- **Tracking**: The script remembers where it left off so it only gets new transactions next time
- **Output**: You'll see a summary of how many transactions were synced

### Syncing more history

To grab more past transactions (like the last 14 or 30 days) for one run:

```bash
LM_OVERRIDE_SINCE_DAYS=14 python sync.py
```

After this runs, it will remember the newest transaction and go back to normal syncing. Don't use this setting for regular runs.

### Syncing specific date ranges

To sync transactions from specific dates:

```bash
python sync.py --since 2024-01-01 --before 2024-02-01
```

- `--since`: Start date (inclusive)
- `--before`: End date (exclusive - so 2024-02-01 means up to but not including Feb 1st)
- If you don't specify `--before`, it syncs up to today

## Advanced: Using snapshots for large backfills

For syncing lots of old transactions, you can save them to a file first, then sync from that file. This is useful for big backfills or if you want to review the data first.

### Step 1: Create a snapshot

```bash
python snapshot_transactions.py --start 2023-01-01 --end 2024-12-31
```

This saves all transactions from that period to a file in the `data/` folder.

### Step 2: Sync from the snapshot

Test first:

```bash
DRY_RUN=1 python sync_from_snapshot.py --month 2024-08
```

Then for real:

```bash
python sync_from_snapshot.py --month 2024-08
```

- Use `--month` to sync just one month, or leave it out to sync everything in the snapshot
- You still need your `LM_ASSET_IDS_MAP` set up

## Setting up automatic syncing

You can make the script run automatically every day (or however often you want).

### On Mac:

1. Open Terminal and type:

```bash
crontab -e
```

2. Add this line to run daily at 8am (replace `/path/to/monzo-lunchmoney-sync` with your actual folder path):

```bash
0 8 * * * cd /path/to/monzo-lunchmoney-sync && /path/to/monzo-lunchmoney-sync/.venv/bin/python sync.py >> sync.log 2>&1
```

3. Save and exit (in nano: Ctrl+X, then Y, then Enter)

This will run the sync every day at 8am and save any output to `sync.log`. You can check the log with:

```bash
tail -f sync.log
```

## Where your data is stored

- **`data/` folder**: Created automatically, contains:
  - `last_sync.json` - remembers where the script left off
  - `monzo_snapshot_*.json` - any snapshots you create
  - `category_map.json` - your custom category mappings (optional)
  - `interest.json` - interest sync data (optional)
- **Privacy**: The `data/` folder and `.env` file are ignored by Git (not uploaded anywhere)
- **Security**: Your login tokens are stored in your computer's secure keychain, not in files

## Syncing Monzo savings pots

Monzo savings are usually "pots" attached to your main account. You can treat them as separate accounts in Lunch Money.

### Setup:

1. Find your pot ID (look in Monzo transaction details or use the Monzo API)
2. Add these to your `.env` file:

```bash
MONZO_SAVINGS_POT_ID=pot_0000000000000000000000
LM_SAVINGS_ASSET_ID=9012
```

### What happens:

- When money moves to/from your savings pot, it creates matching transactions in both your main account and the savings account in Lunch Money
- These are marked as "Bank Transfer" if you set that category
- The script prevents duplicates by using special IDs

## Bonus: Interest tracking

Included a script to sync monthly interest payments you earn from Monzo savings pots. These aren't exposed in the API so you have you manually add them to a local json file to sync them. You can then use `sync_interest.py` to sync the interest payments to Lunch Money.

## Safety features

- **No secrets in logs**: Only transaction counts and timestamps are logged
- **Duplicate protection**: Won't create duplicate transactions if you run it multiple times
- **Test mode**: Always test with `DRY_RUN=1` before running for real

## Automatic category assignment

You can create a `category_map.json` file to automatically assign categories to your transactions based on how Monzo categorizes them.

Example `category_map.json`:

```json
{
	"groceries": 111111,
	"eating_out": "🥬 Groceries",
	"transport": "🚗 Transportation",
	"bills": "🏠 Housing"
}
```

### How it works:

- **Monzo categories**: Use lowercase names like `groceries`, `eating_out`, `transport`
- **Lunch Money categories**: You can use either the category ID number or the exact category name (with or without emoji)
- **Transfers**: Money moves between your own accounts still use the "Bank Transfer" category if you set it
- **Missing categories**: If a Monzo category isn't in your map, the transaction stays uncategorized
