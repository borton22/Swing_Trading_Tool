# src/signals.py
import pandas as pd
import numpy as np

def detect_pullback_setup(df: pd.DataFrame) -> pd.DataFrame:
    """
    Détecte les setups d'achat selon la stratégie de pullback.
    Règles:
    1. Tendance: Close > SMA200
    2. Pullback: Close < EMA20 (le prix est sous sa moyenne courte)
    3. Rebond: Close > Open (bougie verte)
    """
    if df.empty or 'sma200' not in df.columns:
        return pd.DataFrame()

    # On ne garde que les lignes où toutes les conditions sont vraies
    cond_trend = df['close'] > df['sma200']
    cond_pullback = df['close'] < df['ema20']
    cond_confirmation = df['close'] > df['open']
    
    # Un signal est valide si les 3 conditions sont réunies
    df['is_setup'] = cond_trend & cond_pullback & cond_confirmation
    
    return df

def get_last_signal(df: pd.DataFrame):
    """Vérifie si la dernière ligne disponible est un signal."""
    if df.empty or 'is_setup' not in df.columns:
        return False
    return df['is_setup'].iloc[-1]