# Monzo → Lunch Money Sync

Local Python script that syncs recent Monzo transactions into Lunch Money.

## Prereqs

- Python 3.9+ recommended
- A Monzo OAuth2 client (client id/secret + refresh token)
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
MONZO_REFRESH_TOKEN=...
MONZO_ACCOUNT_IDS=acc_...,acc_...,acc_...
LUNCHMONEY_ACCESS_TOKEN=...
# Optional: category id in Lunch Money for bank transfers
LM_CATEGORY_BANK_TRANSFER_ID=123456
# Optional: map Monzo account_id to Lunch Money asset_id (comma-separated pairs)
# Find asset_id in Lunch Money by filtering by account in the UI (see URL param `asset=`)
LM_ASSET_IDS_MAP=acc_000...:1234,acc_000...:5678,acc_000...:9012
# Optional: dry-run to avoid posting
DRY_RUN=1
# Optional: mirror a specific Monzo savings pot into a separate LM asset
MONZO_SAVINGS_POT_ID=pot_0000000000000000000000
LM_SAVINGS_ASSET_ID=9012
```

Notes:

- `MONZO_ACCOUNT_IDS` should include your three account ids (personal, joint, savings), comma-separated.
- Internal movements and Pot transfers are included and categorized as Bank Transfers when `LM_CATEGORY_BANK_TRANSFER_ID` is set.
- If you want to treat a Monzo pot as a separate Lunch Money account, set `MONZO_SAVINGS_POT_ID` and `LM_SAVINGS_ASSET_ID` to mirror those transfers.

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

Notes:

- `| cat` forces full stdout passthrough in some terminals/loggers.
- When the venv is active, `python` resolves to the virtualenv interpreter.

### Alternatives

If you prefer not to use a one-liner, you can run:

```bash
source .venv/bin/activate
python sync.py
```

Output includes per-account counts and overall totals. On success, the newest Monzo `created` timestamp per account is saved to `last_sync.json`.

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

Example entry to run daily at 6am, logging to `sync.log` in the repo:

```bash
0 6 * * * cd /Users/helios/Github/monzo-lunchmoney-sync && /usr/bin/python3 sync.py >> sync.log 2>&1
```

Tip: keep your `.env` in the repo root; `python-dotenv` loads it automatically.

## How it works (high level)

1. Refresh Monzo access token using the refresh token at `https://api.monzo.com/oauth2/token`.
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
