# Implementation Plan

## Current Architecture

### Core Components

1. **Authentication (`auth.py`)**

   - Full OAuth 2.0 implementation with Monzo
   - Local callback server for initial auth
   - Secure token storage in system keychain
   - Automatic token refresh

2. **Monzo Integration (`monzo.py`)**

   - Transaction fetching with pagination
   - Account listing
   - Verification handling
   - Filters for settled-only transactions

3. **Lunch Money Integration (`lunchmoney.py`)**

   - Transaction creation with batching
   - Category listing and mapping
   - Asset ID support

4. **Transaction Processing (`transform.py`)**

   - Monzo → Lunch Money schema conversion
   - Internal transfer detection
   - Pot transfer handling
   - Category mapping
   - Asset mirroring for transfers

5. **State Management (`state.py`)**
   - Per-account sync state tracking
   - Last sync timestamp persistence

### Environment Variables

Required:

- `MONZO_CLIENT_ID`
- `MONZO_CLIENT_SECRET`
- `MONZO_ACCOUNT_IDS` (comma-separated)
- `LUNCHMONEY_ACCESS_TOKEN`

Optional:

- `LM_CATEGORY_BANK_TRANSFER_ID` (for transfer categorization)
- `MONZO_SAVINGS_POT_ID` (for savings tracking)
- `LM_SAVINGS_ASSET_ID` (for savings mirroring)
- `LM_ASSET_IDS_MAP` (account → asset mapping)
- `MONZO_ACCOUNT_LABELS` (friendly names)
- `DRY_RUN` (testing mode)

### Data Files

- `.env`: Environment variables
- `category_map.json`: Monzo → Lunch Money category mapping
- `last_sync.json`: Per-account sync state

## Remaining Tasks

1. **OAuth Implementation**

   - [x] Basic OAuth flow with local callback
   - [x] Token refresh handling
   - [x] Secure token storage
   - [ ] Handle verification challenges
   - [ ] Add token expiry tracking

2. **Error Handling**

   - [x] Safe transaction batching
   - [x] Duplicate prevention
   - [ ] Add retry logic for API failures
   - [ ] Implement proper backoff strategy

3. **Monitoring**

   - [ ] Add structured logging
   - [ ] Implement error notifications
   - [ ] Add basic metrics tracking

---

Updated: September 16, 2025 9:26P
