Updated: September 15, 2025 10:22P

## Monzo → Lunch Money Sync — Implementation Plan

### Goals

- Keep Lunch Money up to date with recent Monzo transactions via a local Python script run daily on macOS.
- Store credentials in `.env` and a `last_sync.json` locally.

### Scope

- Sync transactions from three Monzo accounts (personal checking, joint checking, savings) to Lunch Money.
- Include internal movements (between these three accounts) and Pot transfers; categorize them as Bank Transfers.
- Exclude sensitive data from logs; include only counts and high-level info.
- Run locally via cron; no cloud infra.

### Out of Scope (initial version)

- Category mapping between Monzo and Lunch Money.
- Multi-bank support (Barclays, Vanguard UK, Monument).
- Notifications (email/Slack).

### Architecture

- Python 3 script using `requests` and `python-dotenv`.
- Local state file `last_sync.json` for incremental fetches.
- Two HTTP integrations: Monzo OAuth2 + Transactions API; Lunch Money Transactions create API.

### Secrets

`.env` keys:

- `MONZO_CLIENT_ID`
- `MONZO_CLIENT_SECRET`
- `MONZO_REFRESH_TOKEN`
- `MONZO_ACCOUNT_IDS` (comma-separated list for personal, joint, savings)
- `LUNCHMONEY_ACCESS_TOKEN`
- `LM_CATEGORY_BANK_TRANSFER_ID` (Lunch Money category ID to use for transfers)

### High-Level Flow

1. Load `.env` secrets.
2. Refresh Monzo access token using refresh token.
3. Read `last_sync.json` map per account (or default each to 7 days ago).
4. For each `account_id` in `MONZO_ACCOUNT_IDS`, fetch transactions since its `last_sync`.
5. Transform Monzo transactions to Lunch Money schema, classifying internal/pot movements as Bank Transfers.
6. POST to Lunch Money (batch) per account.
7. Save newest synced `created` timestamp per account back to `last_sync.json`.
8. Log per-account summaries and overall totals; exit.

### Edge Cases & Decisions

- Monzo amounts are in minor units (pence). Convert to GBP with positive numbers for expenses in Lunch Money.
- Ignore pending/declined transactions; only settled transactions. If Monzo returns `declined` or missing `settled`, filter out.
- Internal transfers and Pot transfers: include and set `category_id = LM_CATEGORY_BANK_TRANSFER_ID`.
- Multi-account state: maintain `last_sync` per Monzo `account_id` in a single `last_sync.json` object.
- Idempotency: use per-account `last_sync` and optionally set `external_id` to the Monzo transaction `id` to avoid duplicates.
- Timezones: use UTC timestamps as provided by Monzo; store and compare in ISO8601.

### Tasks (commit-sized)

- [ ] Create Python project skeleton with `.env.example`, `requirements.txt`, and `sync.py` entry.
- [ ] Implement Monzo OAuth2 refresh and token retrieval helper.
- [ ] Implement `last_sync.json` read/write helpers with per-account timestamps.
- [ ] Support multiple Monzo accounts via `MONZO_ACCOUNT_IDS` loop.
- [ ] Fetch transactions since per-account `last_sync` with filtering for settled transactions.
- [ ] Transform Monzo JSON into Lunch Money transaction objects.
- [ ] Detect internal transfers and Pot transfers; set `category_id = LM_CATEGORY_BANK_TRANSFER_ID`.
- [ ] POST batch to Lunch Money with error handling.
- [ ] Add basic logging and summaries (per-account and overall).
- [ ] Add simple idempotency/duplicate guard (use `external_id` = Monzo `id`).
- [ ] Document macOS cron setup and local run instructions in `README.md`.

### Testing Plan

- Dry-run mode: print the number of transactions and first 1-2 transformed items without POSTing.
- Use small `since` window to limit data during manual tests.
- Handle and log non-200 responses from both APIs; abort safely without writing `last_sync`.

### Decisions

- Include Monzo Pot transfers and internal transfers between the three accounts; categorize as Bank Transfers.
