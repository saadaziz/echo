# todo - refactor code to use this instead
# config.py

import os
import secrets

def get_env(key, default=None):
    return os.environ.get(key, default)

def get_required_env(key, fallback=None):
    v = os.environ.get(key, fallback)
    if v is None:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return v

# --- Strong secrets (generate if not provided) ---
JWT_SECRET_KEY = get_env("JWT_SECRET_KEY") or secrets.token_urlsafe(64)
FLASK_SECRET_KEY = get_env("FLASK_SECRET_KEY") or secrets.token_urlsafe(32)

# --- Standard OIDC/OpenID settings ---
JWT_ISSUER = get_env("JWT_ISSUER", "https://aurorahours.com/identity-backend")
JWT_EXPIRATION_MINUTES = int(get_env("JWT_EXPIRATION_MINUTES", "15"))

# --- OpenAI (or other) API Keys ---
OPENAI_API_KEY = get_env("OPENAI_API_KEY", "sk-proj-xxxx-xxxxxx")

# --- Client Auth (for OIDC clients) ---
OIDC_CLIENT_ID = get_env("OIDC_CLIENT_ID", "browser-ui")
OIDC_CLIENT_SECRET = get_env("OIDC_CLIENT_SECRET", "dev-client-secret")

ALLOWED_CLIENTS = [
    OIDC_CLIENT_ID,
]

CLIENT_SECRETS = {
    OIDC_CLIENT_ID: OIDC_CLIENT_SECRET,
}

ALLOWED_REDIRECT_URIS = [
    *(get_env("ALLOWED_REDIRECT_URIS", "http://localhost:5000/callback").split(",")),
]

OIDC_AUTH_URL = get_env("OIDC_AUTH_URL", "https://aurorahours.com/identity-backend/authorize")
OIDC_TOKEN_URL = get_env("OIDC_TOKEN_URL", "https://aurorahours.com/identity-backend/token")
OIDC_REDIRECT_URI = get_env("OIDC_REDIRECT_URI", "http://localhost:5000/callback")
