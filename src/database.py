# src/database.py
import sqlite3
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "market_data.db"
)

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Table prix
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            ticker TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, date)
        )
    """)

    # Table trades (avec colonne username)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date_entree TEXT NOT NULL,
            prix_entree REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            quantite INTEGER NOT NULL,
            devise TEXT DEFAULT 'USD',
            statut TEXT DEFAULT 'Ouvert',
            prix_sortie REAL,
            date_sortie TEXT,
            notes TEXT,
            username TEXT DEFAULT 'toi',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migration : ajoute les colonnes manquantes si nécessaire
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN devise TEXT DEFAULT 'USD'")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN username TEXT DEFAULT 'toi'")
        conn.commit()
    except Exception:
        pass

    # Table signaux (scan)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            price REAL,
            stop REAL,
            shares INTEGER,
            cost REAL,
            risk REAL,
            scanned_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()

def add_trade(ticker, date_entree, prix_entree, stop_loss, take_profit, quantite, username, notes="", devise="USD"):
    """Ajoute un trade lié à un username spécifique."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trades (ticker, date_entree, prix_entree, stop_loss, take_profit, quantite, username, notes, devise)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticker, date_entree, prix_entree, stop_loss, take_profit, quantite, username, notes, devise))
    conn.commit()
    conn.close()

def get_all_trades(username):
    """Récupère uniquement les trades de l'utilisateur connecté."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE LOWER(username) = LOWER(?) ORDER BY date_entree DESC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def close_trade(trade_id, prix_sortie, date_sortie, statut):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE trades
        SET prix_sortie = ?, date_sortie = ?, statut = ?
        WHERE id = ?
    """, (prix_sortie, date_sortie, statut, trade_id))
    conn.commit()
    conn.close()

def delete_trade(trade_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()
    conn.close()

def save_scan_signals(signals):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scan_signals")
    for s in signals:
        cursor.execute("""
            INSERT INTO scan_signals (ticker, price, stop, shares, cost, risk, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            s.get("ticker"),
            s.get("price"),
            s.get("stop"),
            s.get("shares"),
            s.get("cost"),
            s.get("risk"),
        ))
    conn.commit()
    conn.close()

def get_scanned_tickers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ticker FROM scan_signals ORDER BY ticker")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows if r and r[0]]