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