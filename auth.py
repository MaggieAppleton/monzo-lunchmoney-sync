"""Monzo OAuth 2.0 authentication module.

This module handles the OAuth 2.0 flow for Monzo API authentication:
1. Initial authorization (redirect to Monzo login)
2. Token exchange (after callback)
3. Token refresh
4. Secure token storage

For personal use, this runs a local Flask server to handle the OAuth callback.
"""
import os
import secrets
import webbrowser
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import keyring
import requests
from dotenv import load_dotenv
from flask import Flask, request

# Load environment variables
load_dotenv()

# Constants
MONZO_AUTH_URL = "https://auth.monzo.com"
MONZO_TOKEN_URL = "https://api.monzo.com/oauth2/token"
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# Keyring service name for storing tokens
KEYRING_SERVICE = "monzo-lunchmoney-sync"
KEYRING_USERNAME = "default"  # Since this is single-user

class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass

def get_stored_tokens() -> Tuple[Optional[str], Optional[str]]:
    """Get stored access and refresh tokens from keyring.
    
    Returns:
        Tuple of (access_token, refresh_token) or (None, None) if not found
    """
    try:
        tokens = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if tokens:
            access_token, refresh_token = tokens.split(":", 1)
            return access_token, refresh_token
        return None, None
    except Exception as e:
        print(f"Error reading from keyring: {e}")
        return None, None

def store_tokens(access_token: str, refresh_token: str) -> None:
    """Store access and refresh tokens securely in keyring."""
    try:
        # Store both tokens together with a separator
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, f"{access_token}:{refresh_token}")
    except Exception as e:
        print(f"Error storing in keyring: {e}")
        raise AuthenticationError(f"Failed to store tokens: {e}")

def refresh_access_token(refresh_token: str) -> Tuple[str, str]:
    """Refresh access token using a refresh token.
    
    Args:
        refresh_token: The refresh token to use
        
    Returns:
        Tuple of (new_access_token, new_refresh_token)
        
    Raises:
        AuthenticationError: If refresh fails
    """
    client_id = os.getenv("MONZO_CLIENT_ID")
    client_secret = os.getenv("MONZO_CLIENT_SECRET")
    
    if not all([client_id, client_secret]):
        raise AuthenticationError("Missing MONZO_CLIENT_ID/SECRET in environment")
    
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    
    try:
        response = requests.post(MONZO_TOKEN_URL, data=data, timeout=30)
        response.raise_for_status()
        tokens = response.json()
        return tokens["access_token"], tokens["refresh_token"]
    except Exception as e:
        raise AuthenticationError(f"Token refresh failed: {e}")

def get_auth_url() -> Tuple[str, str]:
    """Generate authorization URL and state token for OAuth flow.
    
    Returns:
        Tuple of (auth_url, state_token)
    """
    client_id = os.getenv("MONZO_CLIENT_ID")
    if not client_id:
        raise AuthenticationError("Missing MONZO_CLIENT_ID in environment")
    
    # Generate secure random state token
    state = secrets.token_urlsafe(32)
    
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": "accounts:read transactions:read balance:read"
    }
    auth_url = f"{MONZO_AUTH_URL}/?{urlencode(params)}"
    return auth_url, state

def exchange_code_for_tokens(code: str) -> Tuple[str, str]:
    """Exchange authorization code for access and refresh tokens.
    
    Args:
        code: The authorization code from callback
        
    Returns:
        Tuple of (access_token, refresh_token)
        
    Raises:
        AuthenticationError: If exchange fails
    """
    client_id = os.getenv("MONZO_CLIENT_ID")
    client_secret = os.getenv("MONZO_CLIENT_SECRET")
    
    if not all([client_id, client_secret]):
        raise AuthenticationError("Missing MONZO_CLIENT_ID/SECRET in environment")
    
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "code": code
    }
    
    try:
        response = requests.post(MONZO_TOKEN_URL, data=data, timeout=30)
        response.raise_for_status()
        tokens = response.json()
        return tokens["access_token"], tokens["refresh_token"]
    except Exception as e:
        raise AuthenticationError(f"Token exchange failed: {e}")

def start_auth_flow() -> Tuple[str, str]:
    """Start OAuth flow by running local server and opening browser.
    
    Returns:
        Tuple of (access_token, refresh_token)
        
    Raises:
        AuthenticationError: If authentication fails
    """
    app = Flask(__name__)
    auth_url, expected_state = get_auth_url()
    received_tokens: Dict = {}
    
    @app.route("/callback")
    def callback():
        if "error" in request.args:
            received_tokens["error"] = request.args["error"]
            return "Authentication failed! You can close this window."
            
        state = request.args.get("state")
        if not state or state != expected_state:
            received_tokens["error"] = "Invalid state"
            return "Authentication failed - invalid state! You can close this window."
            
        code = request.args.get("code")
        if not code:
            received_tokens["error"] = "No code received"
            return "Authentication failed - no code! You can close this window."
            
        try:
            access_token, refresh_token = exchange_code_for_tokens(code)
            received_tokens["access_token"] = access_token
            received_tokens["refresh_token"] = refresh_token
            return "Authentication successful! You can close this window."
        except Exception as e:
            received_tokens["error"] = str(e)
            return f"Authentication failed: {e}! You can close this window."
    
    # Start local server
    print("Starting local server for OAuth callback...")
    from threading import Thread
    server = Thread(target=lambda: app.run(port=REDIRECT_PORT, debug=False))
    server.daemon = True
    server.start()
    
    # Open browser for auth
    print(f"Opening browser for Monzo authentication...")
    webbrowser.open(auth_url)
    
    # Wait for callback
    while not received_tokens and server.is_alive():
        pass
    
    if "error" in received_tokens:
        raise AuthenticationError(f"Authentication failed: {received_tokens['error']}")
    
    return received_tokens["access_token"], received_tokens["refresh_token"]

def ensure_valid_auth() -> str:
    """Ensure we have valid authentication tokens.
    
    This will:
    1. Check for stored tokens
    2. If none found, start OAuth flow (only in interactive environments)
    3. If found but access token expired, refresh it
    4. Store new tokens if generated
    
    Returns:
        Valid access token
        
    Raises:
        AuthenticationError: If authentication fails
    """
    import os
    
    # Check if we're in a non-interactive environment early
    is_non_interactive = not os.isatty(0) or os.getenv('CRON') or os.getenv('CI')
    
    access_token, refresh_token = get_stored_tokens()
    
    if not access_token or not refresh_token:
        if is_non_interactive:
            raise AuthenticationError("No stored tokens found in non-interactive environment. Please run the script interactively first to authenticate.")
        print("No stored tokens found. Starting OAuth flow...")
        access_token, refresh_token = start_auth_flow()
        store_tokens(access_token, refresh_token)
        return access_token
    
    # Try the access token
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get("https://api.monzo.com/ping/whoami", headers=headers, timeout=30)
        if response.status_code == 200:
            return access_token
    except Exception as e:
        print(f"Access token test failed: {e}")
    
    # Access token expired, try refresh
    print("Access token expired. Refreshing...")
    try:
        access_token, refresh_token = refresh_access_token(refresh_token)
        store_tokens(access_token, refresh_token)
        return access_token
    except AuthenticationError as e:
        # Refresh failed, check if we're in a non-interactive environment
        if is_non_interactive:
            # In non-interactive environment (cron, CI), don't start OAuth flow
            raise AuthenticationError(f"Token refresh failed in non-interactive environment: {e}")
        
        # Refresh failed, start new OAuth flow (only in interactive environments)
        print("Token refresh failed. Starting new OAuth flow...")
        access_token, refresh_token = start_auth_flow()
        store_tokens(access_token, refresh_token)
        return access_token
