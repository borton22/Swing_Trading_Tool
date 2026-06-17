# Swing_Bot.py
"""
Swing_Bot.py
Système Swing Trading minimal avec :
 - indicateurs techniques (EMA8/EMA21, RSI)
 - sentiment basique (titres via yfinance)
 - plots (EMA + RSI)
 - ATR-based position sizing
 - stockage SQLite (scans, open_trades, closed_trades)
 - fonctions pour rafraîchir le sentiment des trades ouverts
Usage:
    python Swing_Bot.py    # exécute generate_report() sur la liste de tickers par défaut
Importation:
    from Swing_Bot import SwingBot
    bot = SwingBot(tickers=[...])
    bot.generate_report()
    bot.sync_open_trades_sentiment()
    df = bot.get_open_trades_df()
"""

import os
import sqlite3
from datetime import datetime
import json
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# -----------------------
# Configuration par défaut
# -----------------------
DEFAULT_DB = "trading.db"
DEFAULT_PLOTS_DIR = "plots"
DEFAULT_ACCOUNT_VALUE = 10000.0
DEFAULT_RISK_PCT = 0.01
DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_MULTIPLIER = 3

# -----------------------
# Classe principale
# -----------------------
class SwingBot:
    def __init__(
        self,
        tickers,
        db_path: str = DEFAULT_DB,
        account_value: float = DEFAULT_ACCOUNT_VALUE,
        risk_pct: float = DEFAULT_RISK_PCT,
        atr_period: int = DEFAULT_ATR_PERIOD,
        atr_mul: float = DEFAULT_ATR_MULTIPLIER,
        plots_dir: str = DEFAULT_PLOTS_DIR,
    ):
        self.tickers = tickers
        self.db_path = db_path
        self.account_value = float(account_value)
        self.risk_pct = float(risk_pct)
        self.atr_period = int(atr_period)
        self.atr_mul = float(atr_mul)
        self.plots_dir = plots_dir

        # Mots-clés très basiques pour sentiment
        self.positive_words = ['upgrad', 'buy', 'growth', 'beat', 'bullish', 'dividend', 'profit', 'surge', 'outperform']
        self.negative_words = ['downgrad', 'sell', 'debt', 'miss', 'bearish', 'risk', 'inflation', 'drop', 'recall']

        os.makedirs(self.plots_dir, exist_ok=True)
        self._init_db()

    # -----------------------
    # Base SQLite
    # -----------------------
    def _init_db(self):
        """Crée les tables si nécessaire."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    ticker TEXT,
                    price REAL,
                    ema8 REAL,
                    ema21 REAL,
                    rsi REAL,
                    tech_score REAL,
                    sent_raw INTEGER,
                    sent_score REAL,
                    final_score REAL,
                    decision TEXT,
                    position_size INTEGER,
                    stop_price REAL,
                    atr REAL,
                    plot_path TEXT,
                    headlines TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS open_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    entry_date TEXT,
                    entry_price REAL,
                    qty INTEGER,
                    initial_stop REAL,
                    initial_reason TEXT,
                    last_sent_raw INTEGER,
                    last_sent_score REAL,
                    last_sent_headlines TEXT,
                    last_sent_checked TEXT,
                    last_sent_trend TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS closed_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    entry_date TEXT,
                    exit_date TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    qty INTEGER,
                    pnl REAL,
                    reason TEXT
                )
            ''')
            conn.commit()

    # -----------------------
    # Indicateurs Techniques
    # -----------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()

        # RSI 14
        delta = df['Close'].diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.rolling(14, min_periods=1).mean()
        ma_down = down.rolling(14, min_periods=1).mean()
        rs = ma_up / ma_down.replace(0, 1e-10)
        df['RSI'] = 100 - (100 / (1 + rs))

        return df

    # -----------------------
    # Plot EMA & RSI
    # -----------------------
    def plot_ticker(self, df: pd.DataFrame, ticker: str) -> str:
        try:
            plt.style.use('seaborn-darkgrid')
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                           gridspec_kw={'height_ratios': [3, 1]})
            ax1.plot(df.index, df['Close'], label='Close', color='black', linewidth=1)
            if 'EMA8' in df.columns:
                ax1.plot(df.index, df['EMA8'], label='EMA8', color='tab:orange', linewidth=1)
            if 'EMA21' in df.columns:
                ax1.plot(df.index, df['EMA21'], label='EMA21', color='tab:blue', linewidth=1)
            ax1.set_title(f"{ticker} — Close + EMA8/EMA21")
            ax1.legend(loc='upper left', fontsize='small')

            ax2.plot(df.index, df['RSI'], label='RSI(14)', color='tab:green', linewidth=1)
            ax2.axhline(70, color='red', linestyle='--', linewidth=0.7)
            ax2.axhline(30, color='blue', linestyle='--', linewidth=0.7)
            ax2.set_ylabel('RSI')
            ax2.set_ylim(0, 100)
            ax2.legend(loc='upper left', fontsize='small')

            plt.tight_layout()
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.plots_dir, f"{ticker}_{ts}.png")
            fig.savefig(filename, dpi=150)
            plt.close(fig)
            return filename
        except Exception as e:
            print(f"[plot error] {ticker} : {e}")
            return None

    # -----------------------
    # ATR & position sizing
    # -----------------------
    def compute_atr(self, df: pd.DataFrame, period: int = None) -> pd.Series:
        period = self.atr_period if period is None else period
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(period, min_periods=1).mean()
        return atr

    def position_sizing(self, df: pd.DataFrame, price: float) -> dict:
        atr_series = self.compute_atr(df, period=self.atr_period)
        atr = atr_series.iloc[-1] if len(atr_series) > 0 else None
        if atr is None or pd.isna(atr) or atr == 0:
            return {"position_size": 0, "stop_price": None, "risk_amount": 0.0, "atr": None}
        stop_distance = atr * self.atr_mul
        risk_amount = self.account_value * self.risk_pct
        qty = int(risk_amount / stop_distance) if stop_distance > 0 else 0
        stop_price = round(price - stop_distance, 4)
        return {"position_size": qty, "stop_price": stop_price, "risk_amount": round(risk_amount, 2), "atr": round(float(atr), 6)}

    # -----------------------
    # Sentiment (basique via yfinance.news)
    # -----------------------
    def get_sentiment_score(self, ticker: str) -> dict:
        """
        Récupère jusqu'à 5 titres et calcule un score simple (raw count) puis normalise entre -1..+1.
        Retourne : {'raw': int, 'normalized': float, 'headlines': [str]}
        """
        headlines = []
        sent_raw = 0
        try:
            stock = yf.Ticker(ticker)
            news_items = getattr(stock, "news", []) or []
            news_items = news_items[:5]
            for n in news_items:
                title = ""
                if isinstance(n, dict):
                    title = (n.get('title') or "").strip()
                else:
                    title = str(n)
                if not title:
                    continue
                headlines.append(title)
                lt = title.lower()
                for pw in self.positive_words:
                    if pw in lt:
                        sent_raw += 1
                for nw in self.negative_words:
                    if nw in lt:
                        sent_raw -= 1
        except Exception as e:
            # erreur réseau ou autre - on renvoie neutral
            print(f"[news error] {ticker} : {e}")

        normalized = max(-1.0, min(1.0, sent_raw / 2.0))  # clamp sur -1..1 (échelle heuristique)
        return {"raw": int(sent_raw), "normalized": float(normalized), "headlines": headlines}

    # -----------------------
    # Analyse complète d'un ticker
    # -----------------------
    def analyze_ticker(self, ticker: str) -> dict:
        """
        Télécharge les prix, calcule indicateurs, sentiment, sizing, génère plot et insère dans scans table.
        Retourne le dictionnaire de résultat.
        """
        try:
            df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        except Exception as e:
            print(f"[download error] {ticker}: {e}")
            return None

        if df is None or df.empty or len(df) < 21:
            print(f"[skip] {ticker} : données insuffisantes")
            return None

        df = self.compute_indicators(df)

        last_close = float(df['Close'].iloc[-1])
        last_ema8 = float(df['EMA8'].iloc[-1])
        last_ema21 = float(df['EMA21'].iloc[-1])
        last_rsi = float(df['RSI'].iloc[-1])

        # Score technique simple (heuristique)
        tech_score = 0.0
        if last_ema8 > last_ema21:
            tech_score += 0.6
        else:
            tech_score -= 0.2
        if last_rsi < 35:
            tech_score += 0.4
        elif last_rsi > 70:
            tech_score -= 0.4
        if last_close < last_ema21:
            tech_score -= 0.3
        tech_score = max(-1.0, min(1.0, tech_score))

        # Sentiment
        sent = self.get_sentiment_score(ticker)
        sent_score = sent['normalized']
        sent_raw = sent['raw']
        headlines = sent['headlines']

        # Final score pondéré
        final_score = round((0.7 * tech_score) + (0.3 * sent_score), 4)

        # Decision
        if final_score > 0.4:
            decision = "BUY"
        elif final_score < -0.2:
            decision = "SELL"
        else:
            decision = "HOLD"

        # Position sizing
        sizing = self.position_sizing(df, last_close)

        # Plot
        plot_path = self.plot_ticker(df, ticker)

        result = {
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "ticker": ticker,
            "price": round(last_close, 4),
            "ema8": round(last_ema8, 6),
            "ema21": round(last_ema21, 6),
            "rsi": round(last_rsi, 3),
            "tech_score": round(tech_score, 4),
            "sent_raw": int(sent_raw),
            "sent_score": round(sent_score, 4),
            "final_score": final_score,
            "decision": decision,
            "position_size": int(sizing.get("position_size", 0)),
            "stop_price": sizing.get("stop_price"),
            "risk_amount": sizing.get("risk_amount"),
            "atr": sizing.get("atr"),
            "plot_path": plot_path,
            "headlines": headlines
        }

        # Persist in scans table
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO scans (
                        date, ticker, price, ema8, ema21, rsi, tech_score, sent_raw, sent_score, final_score, 
                        decision, position_size, stop_price, atr, plot_path, headlines
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    result['date'],
                    result['ticker'],
                    result['price'],
                    result['ema8'],
                    result['ema21'],
                    result['rsi'],
                    result['tech_score'],
                    result['sent_raw'],
                    result['sent_score'],
                    result['final_score'],
                    result['decision'],
                    result['position_size'],
                    result['stop_price'],
                    result['atr'],
                    result['plot_path'],
                    json.dumps(result['headlines'], ensure_ascii=False)
                ))
                conn.commit()
        except Exception as e:
            print(f"[db insert scan error] {e}")

        return result

    # -----------------------
    # Generate report (scan all tickers)
    # -----------------------
    def generate_report(self) -> list:
        results = []
        print(f"Running generate_report at {datetime.now().isoformat()}")
        for t in self.tickers:
            out = self.analyze_ticker(t)
            if out:
                results.append(out)
                print(f"  - {t}: {out['decision']} (score {out['final_score']})")
        print("generate_report done.")
        return results

    # -----------------------
    # SQLite helpers: get DataFrames
    # -----------------------
    def get_scans_df(self, limit: int = 500) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql(f"SELECT * FROM scans ORDER BY id DESC LIMIT {limit}", conn)
        if 'headlines' in df.columns:
            df['headlines'] = df['headlines'].apply(lambda x: json.loads(x) if x else [])
        return df

    def get_open_trades_df(self) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql("SELECT * FROM open_trades ORDER BY id DESC", conn)
        return df

    def get_closed_trades_df(self) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql("SELECT * FROM closed_trades ORDER BY id DESC", conn)
        return df

    # -----------------------
    # Open trades management
    # -----------------------
    def add_open_trade(self, ticker: str, entry_price: float, qty: int, initial_stop: float, initial_reason: str = ""):
        """Ajoute un trade ouvert ; capture aussi sentiment au moment de l'entrée."""
        sent = self.get_sentiment_score(ticker)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO open_trades (
                    ticker, entry_date, entry_price, qty, initial_stop, initial_reason,
                    last_sent_raw, last_sent_score, last_sent_headlines, last_sent_checked, last_sent_trend
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticker,
                now,
                float(entry_price),
                int(qty),
                initial_stop,
                initial_reason,
                int(sent['raw']),
                float(sent['normalized']),
                json.dumps(sent['headlines'], ensure_ascii=False),
                now,
                "stable"
            ))
            conn.commit()
        print(f"[open_trade added] {ticker} qty={qty} entry={entry_price}")

    def close_trade(self, trade_id: int, exit_price: float, reason: str = ""):
        """Ferme un trade en le déplaçant vers closed_trades."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT * FROM open_trades WHERE id = ?", (trade_id,)).fetchone()
            if not row:
                print(f"[close_trade] trade id {trade_id} not found")
                return False
            # row fields: (id, ticker, entry_date, entry_price, qty, initial_stop, initial_reason, ...)
            # index mapping based on table schema
            id_, ticker, entry_date, entry_price, qty = row[0], row[1], row[2], row[3], row[4]
            pnl = (float(exit_price) - float(entry_price)) * int(qty)
            exit_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute('''
                INSERT INTO closed_trades (ticker, entry_date, exit_date, entry_price, exit_price, qty, pnl, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, entry_date, exit_date, entry_price, float(exit_price), qty, float(pnl), reason))
            cur.execute('DELETE FROM open_trades WHERE id = ?', (trade_id,))
            conn.commit()
        print(f"[trade closed] id={trade_id} {ticker} pnl={pnl}")
        return True

    # -----------------------
    # Sentiment sync for open trades
    # -----------------------
    def sync_open_trades_sentiment(self, alert_delta: float = 0.25):
        """
        Met à jour last_sent_* pour tous les trades ouverts.
        Detecte la tendance (improved / worsened / stable / caution).
        alert_delta : seuil minimal de changement pour considérer 'improved'/'worsened'
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute("SELECT id, ticker, last_sent_score FROM open_trades").fetchall()
            for row in rows:
                trade_id = row[0]
                ticker = row[1]
                old_score = row[2]
                sent = self.get_sentiment_score(ticker)
                new_score = float(sent['normalized'])
                raw = int(sent['raw'])
                headlines = json.dumps(sent['headlines'], ensure_ascii=False)
                checked = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                trend = 'stable'
                try:
                    old_score_f = float(old_score) if old_score is not None else None
                except Exception:
                    old_score_f = None

                if old_score_f is None:
                    trend = 'stable'
                else:
                    delta = new_score - old_score_f
                    if delta <= -alert_delta:
                        trend = 'worsened'
                    elif delta >= alert_delta:
                        trend = 'improved'
                    elif new_score < -0.2:
                        trend = 'caution'
                    else:
                        trend = 'stable'

                cur.execute('''
                    UPDATE open_trades
                    SET last_sent_raw = ?, last_sent_score = ?, last_sent_headlines = ?, last_sent_checked = ?, last_sent_trend = ?
                    WHERE id = ?
                ''', (raw, new_score, headlines, checked, trend, trade_id))
            conn.commit()
        print("[sync_open_trades_sentiment] done.")

# -----------------------
# Main (exécution simple)
# -----------------------
if __name__ == "__main__":
    # Exemple d'utilisation simple
    tickers = ["NVDA", "COST", "TSLA", "BMO.TO", "SHOP.TO"]
    bot = SwingBot(
        tickers=tickers,
        db_path=DEFAULT_DB,
        account_value=DEFAULT_ACCOUNT_VALUE,
        risk_pct=DEFAULT_RISK_PCT,
        atr_period=DEFAULT_ATR_PERIOD,
        atr_mul=DEFAULT_ATR_MULTIPLIER,
        plots_dir=DEFAULT_PLOTS_DIR
    )

    # Lancer le scan / rapport (insère dans la table scans)
    bot.generate_report()

    # Synchroniser sentiment des trades ouverts (s'il y en a)
    bot.sync_open_trades_sentiment()

    # Afficher un résumé rapide
    print("\n---- Latest scans (top 5) ----")
    df_scans = bot.get_scans_df(limit=5)
    if not df_scans.empty:
        print(df_scans[['date','ticker','price','final_score','decision']].to_string(index=False))
    else:
        print("No scans found yet.")

    print("\n---- Open trades ----")
    df_open = bot.get_open_trades_df()
    if not df_open.empty:
        print(df_open.to_string(index=False))
    else:
        print("No open trades.")