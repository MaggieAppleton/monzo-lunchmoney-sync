#!/usr/bin/env python3
"""
Clear stored authentication tokens from the system keyring.

This script removes the Monzo OAuth tokens stored in the system keyring,
effectively logging out the user from the Monzo API. This is useful for
testing authentication flows or when tokens need to be refreshed manually.

Usage:
    python clear_tokens.py

The script will attempt to delete the stored password and report success
or indicate if no tokens were found (which is also fine).
"""
import keyring

# Constants from auth.py
KEYRING_SERVICE = "monzo-lunchmoney-sync"
KEYRING_USERNAME = "default"

if __name__ == "__main__":
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        print("Successfully cleared stored tokens")
    except keyring.errors.PasswordDeleteError:
        print("No tokens found in keyring (this is fine)")