# config.py
import os
from pathlib import Path

# ============================================================
# CHEMINS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "market_data.db"

# ============================================================
# PARAMÈTRES DE TÉLÉCHARGEMENT
# ============================================================
START_DATE = "2022-01-01"   # Historique depuis cette date
INTERVAL = "1d"             # Bougie journalière

# ============================================================
# PARAMÈTRES DE TRADING
# ============================================================
CAPITAL_INITIAL = 10000.0  # Capital de départ ($)
RISK_PER_TRADE = 0.005     # Risque par trade (0.5% = 0.005)

# ============================================================
# UNIVERS DE TRADING (~50 tickers)
# ============================================================
UNIVERSE = [
    "SPY", "QQQ", "IWM",
    "XLK", "XLF", "XLE", "XLV", "XLI",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "JPM", "V", "UNH",
    "AMD", "AVGO", "QCOM", "TXN", "MU", "AMAT", "INTC", "CSCO",
    "ADBE", "CRM", "ORCL", "NOW", "SNOW", "PANW", "CRWD",
    "NFLX", "DIS", "WMT", "COST", "TGT", "HD", "NKE", "SBUX", "MCD",
    "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO",
    "BAC", "WFC", "GS", "MS", "BLK", "AXP",
    "XOM", "CVX", "CAT", "DE", "BA", "GE", "HON", "UPS",
]

# --- UTILISATEURS (authentification Streamlit) ---
# NE PAS STOCKER de secrets en clair dans le repo public.
# On charge les credentials depuis .users.json (git-ignored) ou depuis une variable d'environnement.

import json

# Emplacement du fichier .users.json (doit être git-ignoré)
USERS_FILE = BASE_DIR / ".users.json"

if USERS_FILE.exists():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            USERS_CREDENTIALS = json.load(f)  # structure attendue: {"usernames": { ... }}
    except Exception as e:
        print(f"[config] Erreur lecture {USERS_FILE}: {e}")
        USERS_CREDENTIALS = {"usernames": {}}
else:
    USERS_CREDENTIALS = {"usernames": {}}

# Charger la clé de cookie depuis la variable d'environnement (ne pas hardcoder)
COOKIE_KEY = os.environ.get("SWING_COOKIE_KEY")
if not COOKIE_KEY:
    print("Warning: SWING_COOKIE_KEY not set. Set it in your environment or in a non-committed .env file.")

# Construire la variable USERS utilisée par le code existant (format compatible)
USERS = {
    "credentials": {
        "usernames": USERS_CREDENTIALS.get("usernames", {})
    },
    "cookie": {
        "name": "swing_trader_cookie",
        "key": COOKIE_KEY,
        "expiry_days": 30,
    },
}

# ============================================================
# DYNAMIC UNIVERSE (optional)
# - To enable dynamic selection at import time set USE_DYNAMIC_UNIVERSE=1 in the environment.
# - Otherwise the static UNIVERSE above is used as the fallback.
# - The dynamic loader lives in src/get_top_universe.py and uses yfinance + NASDAQ symbol lists.
# ============================================================

USE_DYNAMIC_UNIVERSE = os.environ.get("USE_DYNAMIC_UNIVERSE", "0") in ("1", "true", "True", "yes", "Yes")

# Default active universe (fallback to static list)
ACTIVE_UNIVERSE = UNIVERSE

if USE_DYNAMIC_UNIVERSE:
    try:
        # import local module that computes top tickers by volume per exchange
        from src.get_top_universe import select_top_from_exchanges

        try:
            dyn = select_top_from_exchanges(top_n_per_exchange=50, period="10d", cache_minutes=60)
            # dyn is a dict: {"NASDAQ": [...], "TSX": [...]} where TSX tickers include the .TO suffix
            # Combine lists: NASDAQ first, then TSX. Keep TSX tickers in yfinance format (.TO)
            ACTIVE_UNIVERSE = dyn.get("NASDAQ", []) + dyn.get("TSX", [])
            if not ACTIVE_UNIVERSE:
                print("[config] Dynamic universe returned empty list, falling back to static UNIVERSE.")
                ACTIVE_UNIVERSE = UNIVERSE
        except Exception as e:
            print(f"[config] Failed to compute dynamic universe: {e}. Using static UNIVERSE.")
            ACTIVE_UNIVERSE = UNIVERSE
    except Exception as e:
        print(f"[config] Dynamic universe module not available: {e}. Using static UNIVERSE.")
        ACTIVE_UNIVERSE = UNIVERSE


def get_active_universe():
    """Return the currently active universe (dynamic if enabled and available, otherwise static UNIVERSE)."""
    return ACTIVE_UNIVERSE
