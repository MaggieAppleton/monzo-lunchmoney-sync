#!/usr/bin/env python3
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