"""
Centralized configuration management.
All sensitive values are read from environment variables with no hardcoded defaults.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Mail API (YYDS / 215.im)
# ---------------------------------------------------------------------------
MAIL_API_KEY = os.environ.get("MAIL_API_KEY", "")
MAIL_API_BASE_URL = os.environ.get("MAIL_API_BASE_URL", "https://maliapi.215.im/v1")

# ---------------------------------------------------------------------------
# Network proxy (SOCKS5, optional)
# Leave empty to connect directly.
# Format: socks5://user:pass@host:port
# ---------------------------------------------------------------------------
SOCKS5_PROXY = os.environ.get("SOCKS5_PROXY", "")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privy_manager.db")
DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB)

# ---------------------------------------------------------------------------
# Server ports
# ---------------------------------------------------------------------------
MANAGER_PORT = int(os.environ.get("MANAGER_PORT", "7894"))
API_PORT = int(os.environ.get("API_PORT", "7895"))
API_HOST = os.environ.get("API_HOST", "0.0.0.0")

# ---------------------------------------------------------------------------
# Registration defaults (can be overridden via Web UI)
# ---------------------------------------------------------------------------
DEFAULT_TOTAL = int(os.environ.get("DEFAULT_TOTAL", "10"))
DEFAULT_CONCURRENCY = int(os.environ.get("DEFAULT_CONCURRENCY", "3"))
DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", "180"))
DEFAULT_INTERVAL = int(os.environ.get("DEFAULT_INTERVAL", "5"))
DEFAULT_DOMAIN = os.environ.get("DEFAULT_DOMAIN", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_proxies():
    """Return proxy dict if SOCKS5_PROXY is configured, otherwise None."""
    if SOCKS5_PROXY:
        return {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate():
    """Raise SystemExit if required configuration is missing."""
    missing = []
    if not MAIL_API_KEY:
        missing.append("MAIL_API_KEY")
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Copy .env.example to .env and fill in the values.", file=sys.stderr)
        sys.exit(1)