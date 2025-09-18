# Monzo → Lunch Money Sync

Local Python script that syncs your Monzo transactions into Lunch Money. Everything stays on your machine. No cloud servers to configure or worries about leaking API keys.
Designed to be run via a daily cron job (or hourly, weekly, whatever you prefer) 
When the script first runs it fetches historical transactions to sync. Then only fetches recent/new transactions on future runs.

## Requirements

- Python 3.9+
- A Monzo OAuth2 client (client id/secret)
- A Lunch Money Personal Access Token

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Create a `.env` file in the repo root with:

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

### Getting credentials

Get your Monzo client ID and secret by creating a new client app in the [Monzo Developers](https://developers.monzo.com/) portal
Get your Lunchmoney access token here

### Notes:

- `MONZO_ACCOUNT_IDS` should include your account ids (personal, joint), comma-separated.
- Internal movements and Pot transfers are included and categorized as Bank Transfers when `LM_CATEGORY_BANK_TRANSFER_ID` is set.
- If you want to treat a Monzo pot as a separate Lunch Money account, set `MONZO_SAVINGS_POT_ID` and `LM_SAVINGS_ASSET_ID` to mirror those transfers.
- `LM_ASSET_IDS_MAP` must include a mapping for every `account_id` in `MONZO_ACCOUNT_IDS`; the script exits if any are missing.
- Only finalized (settled) and not-declined transactions are synced.
- `category_map.json` is read from `data/category_map.json` if present (preferred). A legacy `category_map.json` in the repo root is also supported.

## Run

### Recommended (activate venv and run)

Live run with stdout passthrough:

```bash
source .venv/bin/activate && python sync.py | cat
```

Dry-run (fetch/transform only, no POSTs):

```bash
source .venv/bin/activate && DRY_RUN=1 python sync.py | cat
```

### Notes:

- On first run, the script opens the browser for Monzo OAuth; tokens are stored in the system keychain. No tokens are written to .env.
- `| cat` forces full stdout passthrough in some terminals/loggers.
- When the venv is active, `python` resolves to the virtualenv interpreter.

### Alternatives

If you prefer not to use a one-liner, you can run:

```bash
source .venv/bin/activate
python sync.py
```

Output includes per-account counts and overall totals. On success, the newest Monzo `created` timestamp per account is saved to `data/last_sync.json`.

### Temporary backfill window (testing)

To fetch a larger window for a one-off run (e.g., 14 or 30 days) without changing saved state:

```bash
source .venv/bin/activate && LM_OVERRIDE_SINCE_DAYS=14 python sync.py | cat
```

Omit `LM_OVERRIDE_SINCE_DAYS` afterwards to resume normal incremental syncing from `last_sync.json`.

## Cron (macOS)

Edit crontab:

```bash
crontab -e
```

Example entry to run daily at 8am, logging to `sync.log` in the repo:

```bash
0 8 * * * cd /Users/helios/Github/monzo-lunchmoney-sync && /usr/bin/python3 sync.py >> sync.log 2>&1
```

Tip: keep your `.env` in the repo root; `python-dotenv` loads it automatically.

## How it works (high level)

1. Obtain/refresh a Monzo access token via OAuth; tokens are stored in the system keychain.
2. For each `account_id` in `MONZO_ACCOUNT_IDS`, fetch transactions since that account’s `last_sync`.
3. Transform to Lunch Money format; detect internal/Pot transfers and assign the Bank Transfers category.
4. POST batch to Lunch Money at `https://api.lunchmoney.app/v1/transactions` with `external_id` for idempotency.
5. Update `last_sync.json` with the newest `created` timestamp per account.

## Savings pot mirroring

Monzo “savings” are usually Pots attached to your personal current account (not separate accounts). To mirror movement into/out of a specific savings pot into its own Lunch Money account:

1. Find your pot id (`pot_id`):
   - In some Monzo transaction payloads (scheme `uk_retail_pot`), `metadata.pot_id` is present.
   - Alternatively, use the Monzo API to list pots and copy the id.
2. Set these in `.env`:

```bash
MONZO_SAVINGS_POT_ID=pot_0000000000000000000000
LM_SAVINGS_ASSET_ID=9012
```

Behavior:

- For any transaction identified as a transfer to/from that pot, we add a mirrored transaction into the `LM_SAVINGS_ASSET_ID` with the same date/amount and mark it as a Bank Transfer (if `LM_CATEGORY_BANK_TRANSFER_ID` is set).
- Mirrors use a distinct `external_id` suffix (`:mirror_savings`) for idempotency.

## Safety

- No sensitive values are logged. Logs show counts and timestamps only.
- Idempotency via `external_id` avoids duplicates on retries.
- `DRY_RUN` helps validate setup before live posting.

## Category mapping (Monzo → Lunch Money)

Optionally create a `category_map.json` in the repo root to map Monzo transaction categories to Lunch Money categories. When present, non-transfer transactions will use this mapping to set `category_id`.

Example `category_map.json`:

```json
{
	"groceries": 111111,
	"eating_out": "🥬 Groceries",
	"transport": "🚗 Transportation",
	"bills": "🏠 Housing"
}
```

### Notes:

- Monzo category keys are lower-case like `groceries`, `eating_out`, `transport`, etc.
- Values can be either a numeric Lunch Money `category_id` or the exact Lunch Money category name (with or without emoji). Names are normalized (emoji stripped, case/whitespace-insensitive) and resolved via the Lunch Money API.
- Internal transfers and pot transfers still use `LM_CATEGORY_BANK_TRANSFER_ID` when set, regardless of the map.
- If a Monzo category isn’t present in the map, the transaction is left uncategorized in Lunch Money.
