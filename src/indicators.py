# src/indicators.py
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les indicateurs techniques sur le DataFrame.
    Requiert les colonnes: 'close', 'high', 'low'.
    """
    df = df.copy()

    # 1. Tendance de fond (SMA 200)
    df['sma200'] = df['close'].rolling(window=200).mean()

    # 2. Zone de valeur (EMA 20)
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

    # 3. Volatilité (ATR 14)
    # ATR = moyenne mobile de (High - Low, High - Close_prec, Low - Close_prec)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr14'] = true_range.rolling(window=14).mean()

    # 4. Indicateur de confirmation (Body de la bougie)
    # Utile pour vérifier si on termine dans le vert ou rouge
    df['is_green'] = df['close'] > df['open']

    # Distance à l'EMA20 en % (utile pour le scoring plus tard)
    df['dist_ema20'] = (df['close'] - df['ema20']) / df['ema20']

    return df