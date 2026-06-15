# test_indicators.py
from src.collector import get_processed_data
import pandas as pd

ticker = "SPY"
print(f"Vérification des indicateurs pour {ticker}...")

df = get_processed_data(ticker)

if not df.empty:
    print(df.tail(5)[['close', 'sma200', 'ema20', 'atr14']])
    
    # Vérification simple
    last_close = df['close'].iloc[-1]
    last_sma = df['sma200'].iloc[-1]
    
    if last_close > last_sma:
        print(f"\nSignale: {ticker} est en tendance HAUSSIÈRE (Close > SMA200)")
    else:
        print(f"\nSignale: {ticker} est en tendance BAISSIÈRE (Close < SMA200)")
else:
    print("Erreur: Aucune donnée trouvée.")