# src/live_utils.py
import time
import pandas as pd
import yfinance as yf
import streamlit as st

@st.cache_data(ttl=10)
def get_live_price(ticker: str):
    try:
        t = yf.Ticker(ticker)
        last = None
        try:
            last = t.fast_info.get("last_price", None)
        except Exception:
            last = None
        if last is not None:
            return float(last), time.time()
        hist = t.history(period="2d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1]), time.time()
    except Exception:
        pass
    return None, None

@st.cache_data(ttl=300)
def get_price_series(ticker: str, period="6mo", interval="1d"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        return hist["Close"].astype(float)
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def get_volume_series(ticker: str, period="3mo", interval="1d"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        return hist["Volume"].astype(float)
    except Exception:
        return pd.Series(dtype=float)

def compute_ema(series: pd.Series, span: int):
    if series is None or series.empty:
        return None
    return series.ewm(span=span, adjust=False).mean().iloc[-1]

def compute_atr(series_high: pd.Series, series_low: pd.Series, series_close: pd.Series, n=14):
    try:
        if series_high is not None and not series_high.empty and series_low is not None and not series_low.empty and series_close is not None and not series_close.empty:
            high = series_high
            low = series_low
            close = series_close
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(n).mean().iloc[-1]
            return float(atr) if not pd.isna(atr) else None
    except Exception:
        pass
    try:
        if series_close is not None and not series_close.empty:
            returns = series_close.pct_change().abs()
            approx = returns.rolling(n).mean().iloc[-1] * series_close.iloc[-1]
            return float(approx) if not pd.isna(approx) else None
    except Exception:
        pass
    return None

def compute_rsi(series: pd.Series, n=14):
    if series is None or len(series) < n+1:
        return None
    delta = series.diff().dropna()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(n).mean()
    ma_down = down.rolling(n).mean()
    rs = ma_up / (ma_down.replace(0, 1e-9))
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None

def compute_live_metrics(row: dict, live_price: float):
    try:
        entry = float(row.get("Prix Entrée ($)", 0) or 0)
        qty = int(row.get("Qté", 1) or 1)
        stop = float(row.get("Stop Loss ($)", 0) or 0)
        tp = float(row.get("Take Profit ($)", 0) or 0)
    except Exception:
        return None

    if live_price is None or entry == 0:
        return None

    pl = (live_price - entry) * qty
    pl_pct = (live_price / entry - 1) * 100
    dist_to_stop = (live_price - stop)
    dist_to_stop_pct = (dist_to_stop / live_price) * 100 if live_price != 0 else 0
    dist_to_tp = (tp - live_price)
    dist_to_tp_pct = (dist_to_tp / live_price) * 100 if live_price != 0 else 0

    return {
        "live_price": live_price,
        "unrealized_pl": pl,
        "unrealized_pct": pl_pct,
        "dist_to_stop_abs": dist_to_stop,
        "dist_to_stop_pct": dist_to_stop_pct,
        "dist_to_tp_abs": dist_to_tp,
        "dist_to_tp_pct": dist_to_tp_pct,
    }

def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def _linear_map(x, x_min, x_max):
    if x_max == x_min:
        return 0.0
    return (x - x_min) / (x_max - x_min)

def compute_decision_score(row: dict, price_series: pd.Series = None, live_price: float = None, volume_series: pd.Series = None, params: dict = None):
    default_params = {
        "max_good_dist_pct": 10.0,
        "min_atr_mul": 1.0,
        "weights": {
            "pl": 0.12,
            "dist_to_stop": 0.24,
            "trend": 0.26,
            "rsi": 0.08,
            "atr_penalty": 0.10,
            "volume_penalty": 0.10,
        },
        "thresholds": {
            "ok": 0.65,
            "warning": 0.40,
        }
    }
    if params:
        for k, v in (params or {}).items():
            if k == "weights":
                default_params["weights"].update(v)
            else:
                default_params[k] = v
    p = default_params

    try:
        entry = float(row.get("Prix Entrée ($)", 0) or 0)
        stop = float(row.get("Stop Loss ($)", 0) or 0)
    except Exception:
        return 0.0, {"error": "invalid numeric fields"}, "UNKNOWN"

    if live_price is None:
        if price_series is not None and not price_series.empty:
            live_price = float(price_series.iloc[-1])
        else:
            return 0.0, {"error": "no price available"}, "UNKNOWN"

    diagnostics = {"entry": entry, "live": live_price, "stop": stop}

    if stop and live_price <= stop:
        diagnostics["reason"] = "Prix ≤ stop"
        return 0.0, diagnostics, "CLOSE"

    pl_pct = (live_price / entry - 1) * 100 if entry != 0 else 0
    diagnostics["pl_pct"] = pl_pct
    score_pl = _clamp(_linear_map(pl_pct, -10, 20), 0, 1)

    dist_stop_pct = ((live_price - stop) / live_price * 100) if live_price != 0 else 0
    diagnostics["dist_to_stop_pct"] = dist_stop_pct
    score_dist = _clamp(dist_stop_pct / p["max_good_dist_pct"], 0, 1)

    ema50 = None
    score_trend = 0.0
    if price_series is not None and len(price_series) >= 20:
        ema50 = compute_ema(price_series, 50)
        diagnostics["ema50"] = ema50
        if ema50 is not None:
            if live_price > ema50:
                score_trend = 1.0
            else:
                gap = abs(live_price - ema50) / ema50
                score_trend = _clamp(1 - gap*10, 0, 1)
    else:
        diagnostics["ema50"] = None
        score_trend = 0.5 if live_price >= entry else 0.25

    rsi = compute_rsi(price_series, 14) if price_series is not None else None
    diagnostics["rsi"] = rsi
    if rsi is None:
        score_rsi = 0.5
    else:
        if 40 <= rsi <= 65:
            score_rsi = 1.0
        else:
            score_rsi = max(0.0, 1.0 - abs(rsi - 52) / 50.0)

    atr = None
    atr_penalty = 0.0
    if price_series is not None and len(price_series) >= 15:
        atr = compute_atr(price_series, price_series, price_series, n=14)
        diagnostics["atr"] = atr
        if atr is not None and (live_price - stop) < (p["min_atr_mul"] * atr):
            atr_penalty = 1.0
    else:
        diagnostics["atr"] = None

    vol_penalty = 0.0
    if volume_series is not None and not volume_series.empty:
        avg_vol = volume_series.rolling(20).mean().iloc[-1]
        last_vol = volume_series.iloc[-1]
        diagnostics["avg_vol"] = float(avg_vol) if not pd.isna(avg_vol) else None
        diagnostics["last_vol"] = float(last_vol) if not pd.isna(last_vol) else None
        if avg_vol and last_vol and last_vol > 2 * avg_vol:
            if live_price < entry:
                vol_penalty = 1.0
    else:
        diagnostics["avg_vol"] = None
        diagnostics["last_vol"] = None

    w = p["weights"]
    raw_score = (
        w.get("pl", 0.0) * score_pl +
        w.get("dist_to_stop", 0.0) * score_dist +
        w.get("trend", 0.0) * score_trend +
        w.get("rsi", 0.0) * score_rsi
    )
    penalty = w.get("atr_penalty", 0.0) * atr_penalty + w.get("volume_penalty", 0.0) * vol_penalty
    score = _clamp(raw_score - penalty, 0.0, 1.0)
    diagnostics.update({
        "score_pl": score_pl,
        "score_dist": score_dist,
        "score_trend": score_trend,
        "score_rsi": score_rsi,
        "atr_penalty": atr_penalty,
        "volume_penalty": vol_penalty,
        "raw_score": raw_score,
        "penalty": penalty,
    })

    if score >= p["thresholds"]["ok"]:
        action = "HOLD"
    elif score >= p["thresholds"]["warning"]:
        action = "CAUTION"
    else:
        action = "CLOSE"

    if live_price <= stop:
        action = "CLOSE"

    return score, diagnostics, action