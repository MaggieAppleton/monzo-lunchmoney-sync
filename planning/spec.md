# Monzo → Lunch Money Sync

## Overview

A local Python script that keeps Lunch Money up-to-date with your Monzo transactions. The script runs on your personal computer (macOS) and syncs transactions daily, eliminating the need for third-party services or cloud infrastructure.

## Key Features

- Syncs transactions from multiple Monzo accounts (personal, joint, savings)
- Handles internal transfers between Monzo accounts
- Supports Monzo Pot transfers
- Maps Monzo categories to Lunch Money categories
- Secure OAuth 2.0 authentication with Monzo
- Local credential storage using system keychain
- Detailed activity logging (without sensitive data)

## User Experience

1. **Initial Setup**

   - User obtains API credentials from both Monzo and Lunch Money
   - Sets up environment variables in `.env`
   - Configures optional category mapping in `category_map.json`
   - Runs initial sync to backfill recent transactions

2. **Daily Operation**

   - Script runs automatically at 6am via cron
   - Fetches new transactions since last sync
   - Posts to Lunch Money with proper categorization
   - Logs summary of activity

3. **Error Handling**
   - Safe failure modes (no partial syncs)
   - Clear error messages
   - Automatic token refresh when needed

## Security Considerations

- Credentials stored securely in system keychain
- No cloud infrastructure required
- Runs entirely on user's machine
- Sensitive data never logged

## Future Vision

- Support for additional UK banks (Barclays, Vanguard UK, Monument)
- Enhanced duplicate detection

---

Updated: September 16, 2025 9:26P
