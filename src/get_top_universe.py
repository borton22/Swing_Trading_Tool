# Select top X tickers by average volume from Yahoo (preferred) or NASDAQ/other lists (fallback)
# Requires: pandas, yfinance, requests
# pip install pandas yfinance requests

import time
import pickle
import io
import os
from pathlib import Path
from typing import List, Dict

import requests
import pandas as pd
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Constants
YAHOO_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener"
NASDAQ_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
CACHE_PATH = Path("data/top_universe_cache.pkl")

# HTTP helpers

def requests_session_with_retries(total_retries=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504)) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    # honor HTTP(S)_PROXY env vars automatically used by requests
    return s


def fetch_text_with_retries(url: str, timeout: int = 15) -> str:
    s = requests_session_with_retries()
    resp = s.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# Yahoo Finance screener fallback (preferred when FTP is unreachable)

def fetch_yahoo_most_active(region: str = "US", count: int = 250, timeout: int = 10) -> List[str]:
    """
    Query Yahoo Finance screener for most active symbols in a given region.
    region: 'US' or 'CA' (Canada/TSX)
    Returns a list of ticker symbols (strings). Uses the 'most_actives' screener.
    """
    session = requests_session_with_retries()
    params = {
        "formatted": "true",
        "lang": "en-US",
        "region": region,
        "scrIds": "most_actives",
        "count": str(count),
    }
    headers = {"User-Agent": "python-requests/2.x"}

    try:
        resp = session.get(YAHOO_SCREENER_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[get_top_universe] Yahoo screener request failed (region={region}): {e}")
        return []

    quotes = []
    try:
        # Depending on Yahoo's response structure
        quotes = data.get("finance", {}).get("result", [])[0].get("quotes", [])
    except Exception:
        quotes = []

    symbols = []
    for q in quotes:
        sym = q.get("symbol")
        exch = (q.get("exchange") or q.get("exchangeName") or "").upper()
        if not sym:
            continue
        # Normalize TSX tickers for yfinance: add .TO if exchange indicates Toronto/TSX
        if region.upper() == "CA":
            if not sym.endswith(".TO") and ("TORONTO" in exch or "TSX" in exch or exch == "TSE"):
                sym = sym + ".TO"
        symbols.append(sym)

    time.sleep(0.1)
    return symbols


# NASDAQ/Otherlisted fetchers (fallback)

def load_nasdaq_symbols() -> List[str]:
    txt = fetch_text_with_retries(NASDAQ_LISTED_URL, timeout=20)
    df = pd.read_csv(io.StringIO(txt), sep="|", engine="python", skipfooter=1)
    if "Symbol" not in df.columns:
        raise RuntimeError("Unexpected NASDAQ list format: no 'Symbol' column")
    return df["Symbol"].astype(str).str.strip().tolist()


def load_otherlisted_symbols() -> (pd.DataFrame, str):
    txt = fetch_text_with_retries(OTHER_LISTED_URL, timeout=20)
    df = pd.read_csv(io.StringIO(txt), sep="|", engine="python", skipfooter=1)
    if "ACT Symbol" in df.columns and "Symbol" not in df.columns:
        df = df.rename(columns={"ACT Symbol": "Symbol"})
    exch_col = None
    for c in df.columns:
        if "exchange" in c.lower():
            exch_col = c
            break
    return df, exch_col


def map_tsx_symbol(symbol: str) -> str:
    # yfinance expects '.TO' suffix for TSX
    if symbol.endswith(".TO"):
        return symbol
    return symbol + ".TO"


# Volume-based selection

def get_top_by_avg_volume(tickers: List[str], top_n: int = 50, period: str = "10d", batch_size: int = 100) -> List[str]:
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
                time.sleep(0.15)
        else:
            vol_df = hist["Volume"]
            if isinstance(vol_df, pd.Series):
                volumes[batch[0]] = float(vol_df.mean())
            else:
                for t in vol_df.columns:
                    v = vol_df[t].dropna()
                    volumes[t] = float(v.mean()) if not v.empty else 0.0
        time.sleep(0.3)

    sorted_by_vol = sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, v in sorted_by_vol[:top_n]]


# Main selection function: try Yahoo first, then NASDAQ/otherlisted as fallback

def select_top_from_exchanges(top_n_per_exchange: int = 50, period: str = "10d", cache_minutes: int = 30) -> Dict[str, List[str]]:
    # try cache
    try:
        if CACHE_PATH.exists():
            mtime = CACHE_PATH.stat().st_mtime
            age_min = (time.time() - mtime) / 60.0
            if age_min < cache_minutes:
                print(f"[get_top_universe] Using cached universe (age {age_min:.1f} minutes)")
                return pickle.loads(CACHE_PATH.read_bytes())
    except Exception:
        pass

    # 1) Try Yahoo screener first (US and CA)
    try:
        print("[get_top_universe] Attempting to fetch candidates from Yahoo screener...")
        nasdaq_candidates = fetch_yahoo_most_active(region="US", count=500, timeout=10)
        tsx_candidates = fetch_yahoo_most_active(region="CA", count=500, timeout=10)

        nasdaq_top = get_top_by_avg_volume(nasdaq_candidates, top_n=top_n_per_exchange, period=period)
        # Normalize TSX tickers for yfinance format
        tsx_yf = []
        for s in tsx_candidates:
            # if Yahoo already provided suffix, keep it; otherwise add .TO
            if s.endswith(".TO"):
                tsx_yf.append(s)
            else:
                tsx_yf.append(map_tsx_symbol(s))
        tsx_top = get_top_by_avg_volume(tsx_yf, top_n=top_n_per_exchange, period=period)

        result = {"NASDAQ": nasdaq_top, "TSX": tsx_top}
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_bytes(pickle.dumps(result))
        except Exception:
            pass
        print("[get_top_universe] Successfully selected top tickers using Yahoo screener")
        return result
    except Exception as e:
        print(f"[get_top_universe] Yahoo-based selection failed: {e}. Falling back to NASDAQ files...")

    # 2) Fallback to NASDAQ/otherlisted approach
    try:
        nasdaq_syms = load_nasdaq_symbols()
        nasdaq_top = get_top_by_avg_volume(nasdaq_syms, top_n=top_n_per_exchange, period=period)

        other_df, exch_col = load_otherlisted_symbols()
        tsx_candidates = []
        if exch_col is not None:
            mask = other_df[exch_col].astype(str).str.contains(r"TSX|TORONTO|T", case=False, na=False)
            tsx_df = other_df[mask]
            if "Symbol" in tsx_df.columns:
                tsx_candidates = tsx_df["Symbol"].astype(str).str.strip().tolist()
        else:
            if "Symbol" in other_df.columns:
                tsx_candidates = other_df["Symbol"].astype(str).str.strip().tolist()

        tsx_yf = [map_tsx_symbol(s) for s in tsx_candidates]
        tsx_top = get_top_by_avg_volume(tsx_yf, top_n=top_n_per_exchange, period=period)

        result = {"NASDAQ": nasdaq_top, "TSX": tsx_top}
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_bytes(pickle.dumps(result))
        except Exception:
            pass
        print("[get_top_universe] Successfully selected top tickers using NASDAQ/otherlisted lists")
        return result
    except Exception as e:
        print(f"[get_top_universe] Fallback NASDAQ/otherlisted approach failed: {e}")
        # Final fallback: return empty lists
        return {"NASDAQ": [], "TSX": []}


if __name__ == "__main__":
    top = select_top_from_exchanges(top_n_per_exchange=25, period="10d")
    print("NASDAQ top:", top["NASDAQ"][:20])
    print("TSX top:", top["TSX"][:20])
