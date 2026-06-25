# Select top X tickers by average volume from NASDAQ and TSX
# Requires: pandas, yfinance, requests
# pip install pandas yfinance requests

import time
import pickle
from pathlib import Path
import io
import requests
import pandas as pd
import yfinance as yf

NASDAQ_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
CACHE_PATH = Path("data/top_universe_cache.pkl")


def load_nasdaq_symbols():
    r = requests.get(NASDAQ_LISTED_URL, timeout=15)
    r.raise_for_status()
    # nasdaqlisted.txt uses '|' separators and a final summary line; skipfooter=1
    df = pd.read_csv(io.StringIO(r.text), sep="|", engine="python", skipfooter=1)
    if "Symbol" not in df.columns:
        raise RuntimeError("Unexpected NASDAQ list format: no 'Symbol' column")
    return df["Symbol"].astype(str).str.strip().tolist()


def load_otherlisted_symbols():
    r = requests.get(OTHER_LISTED_URL, timeout=15)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="|", engine="python", skipfooter=1)
    # Normalize column names
    if "ACT Symbol" in df.columns and "Symbol" not in df.columns:
        df = df.rename(columns={"ACT Symbol": "Symbol"})
    # Try to find an exchange-like column
    exch_col = None
    for c in df.columns:
        if c.lower().startswith("exchange") or "exchange" in c.lower():
            exch_col = c
            break
    return df, exch_col


def map_tsx_symbol(symbol):
    # yfinance expects '.TO' suffix for TSX
    if symbol.endswith(".TO"):
        return symbol
    return symbol + ".TO"


def get_top_by_avg_volume(tickers, top_n=50, period="10d", batch_size=100):
    volumes = {}
    # unique while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
    tickers = unique_tickers

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            hist = yf.download(batch, period=period, progress=False, threads=True)
        except Exception:
            hist = None
        if hist is None or ("Volume" not in hist):
            # fallback: per-ticker fetch
            for t in batch:
                try:
                    v = yf.Ticker(t).history(period=period)["Volume"]
                    volumes[t] = float(v.mean()) if not v.empty else 0.0
                except Exception:
                    volumes[t] = 0.0
                time.sleep(0.3)
        else:
            vol_df = hist["Volume"]
            if isinstance(vol_df, pd.Series):
                volumes[batch[0]] = float(vol_df.mean())
            else:
                for t in vol_df.columns:
                    v = vol_df[t].dropna()
                    volumes[t] = float(v.mean()) if not v.empty else 0.0
        time.sleep(0.5)

    sorted_by_vol = sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, v in sorted_by_vol[:top_n]]


def select_top_from_exchanges(top_n_per_exchange=50, period="10d", cache_minutes=30):
    # try cache
    try:
        if CACHE_PATH.exists():
            mtime = CACHE_PATH.stat().st_mtime
            age_min = (time.time() - mtime) / 60.0
            if age_min < cache_minutes:
                return pickle.loads(CACHE_PATH.read_bytes())
    except Exception:
        pass

    # NASDAQ
    nasdaq_syms = load_nasdaq_symbols()
    nasdaq_top = get_top_by_avg_volume(nasdaq_syms, top_n=top_n_per_exchange, period=period)

    # OTHER (to find TSX)
    other_df, exch_col = load_otherlisted_symbols()
    tsx_candidates = []
    if exch_col is not None:
        # match common TSX labels
        mask = other_df[exch_col].astype(str).str.contains(r"TSX|TORONTO|T", case=False, na=False)
        tsx_df = other_df[mask]
        if "Symbol" in tsx_df.columns:
            tsx_candidates = tsx_df["Symbol"].astype(str).str.strip().tolist()
    else:
        # fallback: try to find typical TSX suffixes in the 'Issue' or 'Company' columns (best-effort)
        if "Symbol" in other_df.columns:
            tsx_candidates = other_df["Symbol"].astype(str).str.strip().tolist()

    # Map to yfinance format
    tsx_yf = [map_tsx_symbol(s) for s in tsx_candidates]
    tsx_top = get_top_by_avg_volume(tsx_yf, top_n=top_n_per_exchange, period=period)

    result = {"NASDAQ": nasdaq_top, "TSX": tsx_top}
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_bytes(pickle.dumps(result))
    except Exception:
        pass
    return result


if __name__ == "__main__":
    top = select_top_from_exchanges(top_n_per_exchange=25, period="10d")
    print("NASDAQ top:", top["NASDAQ"][:10])
    print("TSX top:", top["TSX"][:10])
