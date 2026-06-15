# src/collector.py
import sqlite3
import os
import time
import logging
import pandas as pd
import yfinance as yf
import pytz
from datetime import datetime, timedelta, date
from config import DB_PATH, DATA_DIR, START_DATE, INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prices_daily (
                ticker      TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                adj_close   REAL,
                volume      INTEGER,
                PRIMARY KEY (ticker, date)
            );

            CREATE TABLE IF NOT EXISTS signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT    NOT NULL,
                ticker          TEXT    NOT NULL,
                strategy_id     TEXT    NOT NULL,
                score           REAL,
                entry_price     REAL,
                stop_price      REAL,
                take_profit     REAL,
                notes           TEXT,
                created_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trades (
                trade_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT    NOT NULL,
                strategy_id     TEXT,
                entry_date      TEXT,
                entry_price     REAL,
                shares          INTEGER,
                stop_price      REAL,
                take_profit     REAL,
                exit_date       TEXT,
                exit_price      REAL,
                exit_reason     TEXT,
                pnl             REAL,
                r_multiple      REAL,
                created_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS equity_curve (
                date        TEXT    PRIMARY KEY,
                equity      REAL,
                cash        REAL,
                drawdown    REAL
            );

            CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices_daily(ticker);
            CREATE INDEX IF NOT EXISTS idx_prices_date   ON prices_daily(date);
            CREATE INDEX IF NOT EXISTS idx_signals_date  ON signals(date);
        """)
    conn.close()
    logger.info("Base de donnees initialisee.")


def _now_ny() -> datetime:
    ny_tz = pytz.timezone("America/New_York")
    return datetime.now(ny_tz)


def get_last_date(ticker: str) -> str | None:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT MAX(date) FROM prices_daily WHERE ticker = ?", (ticker,)
    )
    result = cursor.fetchone()[0]
    conn.close()
    return result


def download_ticker(ticker: str, start: str, end: str, retries: int = 3) -> pd.DataFrame | None:
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,                 # end est EXCLUSIF chez yfinance
                interval=INTERVAL,
                auto_adjust=False,
                progress=False
            )
            if df.empty:
                logger.warning(f"{ticker}: aucune donnee recue.")
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Adj Close": "adj_close", "Volume": "volume"
            })
            df.index.name = "date"
            df.index = df.index.strftime("%Y-%m-%d")
            df["ticker"] = ticker
            return df[["ticker", "open", "high", "low", "close", "adj_close", "volume"]]

        except Exception as e:
            logger.error(f"{ticker} tentative {attempt + 1}/{retries}: {e}")
            time.sleep(2 ** attempt)
    return None


def upsert_prices(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    conn = get_connection()
    records = [
        (row["ticker"], date_str, row["open"], row["high"], row["low"],
         row["close"], row["adj_close"], int(row["volume"]))
        for date_str, row in df.iterrows()
    ]
    with conn:
        conn.executemany("""
            INSERT OR REPLACE INTO prices_daily
                (ticker, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
    conn.close()
    return len(records)


def update_ticker(ticker: str, full_refresh: bool = False) -> int:
    """
    Fix critique:
    - Avant 16h05 NY, on EXCLUT "aujourd'hui" du download daily pour éviter
      que yfinance renvoie une bougie daily partielle (close = prix intraday).
    - Après 16h05 NY, on inclut aujourd'hui (clôture officielle) via end=demain.
    """
    if full_refresh:
        start_str = START_DATE
    else:
        last = get_last_date(ticker)
        if last:
            start_str = (datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start_str = START_DATE

    now_ny = _now_ny()
    hour_ny = now_ny.hour + now_ny.minute / 60.0

    today_ny = now_ny.strftime("%Y-%m-%d")
    tomorrow_ny = (now_ny + timedelta(days=1)).strftime("%Y-%m-%d")

    # end est EXCLUSIF:
    # - avant close: end=today => inclut jusqu'à hier
    # - après close: end=tomorrow => inclut aujourd'hui (close officielle)
    if hour_ny < 16.05:
        end_str = today_ny
    else:
        end_str = tomorrow_ny

    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
    except Exception:
        logger.error(f"{ticker}: dates invalides start={start_str} end={end_str}")
        return 0

    if start_dt >= end_dt:
        logger.info(f"{ticker}: deja a jour (start >= end).")
        return 0

    df = download_ticker(ticker, start_str, end_str)
    count = upsert_prices(df)

    if count > 0:
        logger.info(f"{ticker}: {count} lignes inserees/mises a jour.")
    else:
        logger.info(f"{ticker}: deja a jour.")
    return count


def update_universe(tickers: list[str], full_refresh: bool = False, delay: float = 0.5) -> dict:
    results = {}
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] Mise a jour: {ticker}")
        results[ticker] = update_ticker(ticker, full_refresh)
        time.sleep(delay)
    return results


def get_prices(ticker: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM prices_daily WHERE ticker = ?"
    params = [ticker]
    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date ASC"
    df = pd.read_sql_query(query, conn, params=params, index_col="date")
    conn.close()
    return df


def get_processed_data(ticker: str) -> pd.DataFrame:
    """Récupère les prix et calcule les indicateurs d'un coup."""
    from src.indicators import add_indicators
    df = get_prices(ticker)
    if df.empty:
        return df
    return add_indicators(df)


def get_live_price(ticker: str) -> dict:
    """
    Prix live fiable:
    - Marché ouvert: fast_info['last_price'] si dispo, sinon history 1m
    - Pré-market: preMarketPrice via info, fallback history 1m
    - Marché fermé: None
    """
    try:
        now_ny = _now_ny()
        hour = now_ny.hour + now_ny.minute / 60.0

        t = yf.Ticker(ticker)

        # Marché ouvert
        if 9.5 <= hour < 16.0:
            try:
                fi = getattr(t, "fast_info", None)
                if fi and fi.get("last_price"):
                    return {"price": float(fi["last_price"]), "source": "Live"}
            except Exception:
                pass

            df_live = t.history(period="1d", interval="1m")
            if not df_live.empty:
                return {"price": float(df_live["Close"].iloc[-1]), "source": "Live"}
            return {"price": None, "source": "Live (N/A)"}

        # Pré-market
        if 4.0 <= hour < 9.5:
            try:
                info = t.info
                pre = info.get("preMarketPrice")
                if pre:
                    return {"price": float(pre), "source": "Pré-market"}
            except Exception:
                pass

            df_live = t.history(period="1d", interval="1m")
            if not df_live.empty:
                return {"price": float(df_live["Close"].iloc[-1]), "source": "Pré-market (Hist)"}
            return {"price": None, "source": "Pré-market (N/A)"}

        # Marché fermé
        return {"price": None, "source": "Fermé"}

    except Exception as e:
        logger.error(f"Erreur get_live_price {ticker}: {e}")
        return {"price": None, "source": "Erreur"}