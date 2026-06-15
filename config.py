# config.py
import os

# ============================================================
# CHEMINS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "market_data.db")

# ============================================================
# PARAMÈTRES DE TÉLÉCHARGEMENT
# ============================================================
START_DATE = "2022-01-01"   # Historique depuis cette date
INTERVAL   = "1d"           # Bougie journalière

# ============================================================
# PARAMÈTRES DE TRADING
# ============================================================
CAPITAL_INITIAL  = 10000.0  # Capital de départ ($)
RISK_PER_TRADE   = 0.005    # Risque par trade (0.5% = 0.005)

# ============================================================
# UNIVERS DE TRADING (~50 tickers)
# ============================================================
UNIVERSE = [
    # Market ETFs
    "SPY", "QQQ", "IWM",

    # Sector ETFs
    "XLK", "XLF", "XLE", "XLV", "XLI",

    # Mega-cap / Core
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "JPM", "V", "UNH",

    # Semis / Hardware
    "AMD", "AVGO", "QCOM", "TXN", "MU", "AMAT", "INTC", "CSCO",

    # Software / Cloud / Cyber
    "ADBE", "CRM", "ORCL", "NOW", "SNOW", "PANW", "CRWD",

    # Consumer / Media / Retail
    "NFLX", "DIS", "WMT", "COST", "TGT", "HD", "NKE", "SBUX", "MCD",

    # Healthcare
    "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO",

    # Financials
    "BAC", "WFC", "GS", "MS", "BLK", "AXP",

    # Energy / Industrials
    "XOM", "CVX", "CAT", "DE", "BA", "GE", "HON", "UPS",
]

# ============================================================
# UTILISATEURS (ajoute/retire des users ici)
# ============================================================
import streamlit_authenticator as stauth

USERS = {
    "credentials": {
        "usernames": {
            "FrankB": {
                "name": "François Baron",
                "password": stauth.Hasher.hash("FrankB123321"),
            },
            "Invite": {
                "name": "Invite",
                "password": stauth.Hasher.hash("Invite321321"),
            },
        }
    },
    "cookie": {
        "name": "swing_trader_cookie",
        "key": "xK9#mP2$qL7vRtNwZpYsAeBcDfGhJkLm",
        "expiry_days": 30,
    },
}