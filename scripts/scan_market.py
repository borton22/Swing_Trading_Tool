# scripts/scan_market.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import get_processed_data
from src.signals import detect_pullback_setup, get_last_signal
from src.sizer import calculate_position_size
from src.database import init_db, save_scan_signals
from config import UNIVERSE, CAPITAL_INITIAL, RISK_PER_TRADE
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_scan():
    logger.info("=== SCANNER AVEC POSITION SIZING ===")

    # Assure que la DB et les tables existent
    init_db()

    signals_found = []

    for ticker in UNIVERSE:
        df = get_processed_data(ticker)
        df = detect_pullback_setup(df)

        if get_last_signal(df):
            last_price = df["close"].iloc[-1]
            atr = df["atr14"].iloc[-1]
            suggested_stop = last_price - (2 * atr)

            sizing = calculate_position_size(
                CAPITAL_INITIAL,
                RISK_PER_TRADE,
                last_price,
                suggested_stop
            )

            if sizing["shares"] > 0:
                signals_found.append({
                    "ticker": ticker,
                    "price": round(last_price, 2),
                    "stop": round(suggested_stop, 2),
                    "shares": sizing["shares"],
                    "cost": sizing["total_cost"],
                    "risk": sizing["risk_amount"],
                })

    if not signals_found:
        logger.info("Aucun signal détecté ce soir.")
    else:
        logger.info(f"SIGNALS DÉTECTÉS ({len(signals_found)}) :")
        print("-" * 60)
        for s in signals_found:
            print(f"SYMBOLE : {s['ticker']}")
            print(f"ACHAT   : {s['price']}$")
            print(f"STOP    : {s['stop']}$")
            print(f"QUANTITÉ: {s['shares']} actions")
            print(f"COÛT TOT: {s['cost']}$")
            print(f"RISQUE  : {s['risk']}$ ({RISK_PER_TRADE*100:.2f}% de {CAPITAL_INITIAL}$)")
            print("-" * 60)

    # Sauvegarde en DB pour alimenter le dropdown du journal
    save_scan_signals(signals_found)
    logger.info(f"✅ {len(signals_found)} signal(s) sauvegardé(s) en DB.")

if __name__ == "__main__":
    run_scan()