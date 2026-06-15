# src/journal.py
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import date
from src.database import (
    init_db,
    add_trade,
    get_all_trades,
    close_trade,
    delete_trade,
    get_scanned_tickers,
)

COLUMNS = [
    "ID", "Ticker", "Date Entrée", "Prix Entrée ($)",
    "Stop Loss ($)", "Take Profit ($)", "Qté",
    "Statut", "Prix Sortie ($)", "Date Sortie", "Notes", "Créé le", "Devise", "Username"
]

@st.cache_data(ttl=900, show_spinner="Récupération du taux USD/CAD...")
def get_usdcad_rate():
    try:
        rate = yf.Ticker("USDCAD=X").fast_info["last_price"]
        if rate and rate > 0:
            return round(float(rate), 4)
    except Exception:
        pass
    return 1.3650

@st.cache_data(ttl=3600, show_spinner="Chargement de la liste des tickers...")
def load_universe_tickers():
    try:
        from config import UNIVERSE
        return sorted(set([str(t).strip() for t in UNIVERSE if str(t).strip()]))
    except Exception:
        return []

@st.cache_data(ttl=86400, show_spinner="Téléchargement de la liste US complète...")
def load_all_us_tickers_from_github():
    url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    tickers = []
    for line in r.text.splitlines():
        t = line.strip()
        if t and "$" not in t:
            tickers.append(t)
    return sorted(set(tickers))

def calculate_stats(df, usdcad_rate):
    closed = df[df["Statut"].isin(["Gagné", "Perdu"])].copy()
    if closed.empty:
        return None

    closed["P&L ($)"] = (
        (closed["Prix Sortie ($)"] - closed["Prix Entrée ($)"]) * closed["Qté"]
    )

    closed["P&L (CAD)"] = closed.apply(
        lambda row: row["P&L ($)"] * usdcad_rate if row["Devise"] == "USD" else row["P&L ($)"],
        axis=1
    )

    total_trades = len(closed)
    wins = closed[closed["Statut"] == "Gagné"]
    losses = closed[closed["Statut"] == "Perdu"]

    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
    total_pnl_cad = closed["P&L (CAD)"].sum()
    avg_win_cad = wins["P&L (CAD)"].mean() if not wins.empty else 0
    avg_loss_cad = losses["P&L (CAD)"].mean() if not losses.empty else 0
    profit_factor = abs(avg_win_cad / avg_loss_cad) if avg_loss_cad != 0 else 0

    usd_trades = closed[closed["Devise"] == "USD"]
    cad_trades = closed[closed["Devise"] == "CAD"]

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl_cad": total_pnl_cad,
        "avg_win_cad": avg_win_cad,
        "avg_loss_cad": avg_loss_cad,
        "profit_factor": profit_factor,
        "pnl_usd": usd_trades["P&L ($)"].sum() if not usd_trades.empty else 0,
        "pnl_cad_native": cad_trades["P&L ($)"].sum() if not cad_trades.empty else 0,
        "count_usd": len(usd_trades),
        "count_cad": len(cad_trades),
        "df_closed": closed,
    }


def show_journal(username):
    st.subheader("📓 Journal des Trades")

    init_db()

    # --- Taux de change ---
    usdcad_rate = get_usdcad_rate()
    st.caption(f"💱 Taux USD/CAD en cours : **{usdcad_rate}** (mis à jour toutes les 15 min)")

    # --- Source tickers ---
    scanned = get_scanned_tickers()
    universe = load_universe_tickers()

    colA, colB = st.columns([1, 1])
    with colA:
        use_scanned_only = st.toggle(
            "🎯 Tickers scannés seulement",
            value=bool(scanned),
            disabled=not bool(scanned),
            help="Si activé: le dropdown contient uniquement les tickers du dernier scan."
        )
    with colB:
        include_all_us = st.toggle(
            "🇺🇸 Inclure liste US complète (plus lourd)",
            value=False,
            help="Ajoute une grande liste de tickers US depuis GitHub."
        )

    if use_scanned_only and scanned:
        ticker_list = scanned
        st.caption(f"📋 {len(ticker_list)} tickers issus du dernier scan")
    else:
        ticker_list = universe[:] if universe else []
        source_msg = f"📋 {len(ticker_list)} tickers depuis UNIVERSE"

        if include_all_us:
            try:
                all_us = load_all_us_tickers_from_github()
                ticker_list = sorted(set(ticker_list) | set(all_us))
                source_msg += f" + {len(all_us):,} tickers US"
            except Exception as e:
                st.warning(f"Impossible de charger la liste US complète: {e}")

        if scanned:
            ticker_list = sorted(set(ticker_list) | set(scanned))
            source_msg += f" (+ {len(scanned)} scannés)"

        if not ticker_list:
            ticker_list = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "COST"]
            source_msg = "📋 Fallback (liste courte)"

        st.caption(source_msg)

    # --- FORMULAIRE NOUVEAU TRADE ---
    with st.expander("➕ Entrer un nouveau trade", expanded=True):
        with st.form("new_trade_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)

            ticker = col1.selectbox(
                "Ticker",
                options=ticker_list,
                index=None,
                placeholder="Tape ou cherche...",
                help="Commence à taper pour filtrer."
            )
            ticker = ticker.strip() if ticker else ""

            devise = col2.selectbox(
                "Devise",
                options=["USD", "CAD"],
                index=0,
                help="Devise dans laquelle tu achètes l'action."
            )

            date_entree = col3.date_input("Date d'entrée", value=date.today())
            quantite = col4.number_input("Quantité", min_value=1, step=1, value=1)

            col5, col6, col7 = st.columns(3)
            prix_entree = col5.number_input(
                "Prix d'entrée ($)", min_value=0.01, step=0.01,
                help="Prix auquel tu as acheté l'action."
            )
            stop_loss = col6.number_input(
                "Stop Loss ($)", min_value=0.01, step=0.01,
                help="Prix de sortie automatique si le trade va contre toi."
            )
            take_profit = col7.number_input(
                "Take Profit ($)", min_value=0.01, step=0.01,
                help="Prix cible pour encaisser le profit."
            )

            notes = st.text_area(
                "Notes (optionnel)",
                placeholder="Ex: Signal pullback EMA20, marché haussier..."
            )

            submitted = st.form_submit_button("💾 Sauvegarder le trade", use_container_width=True)
            if submitted:
                if not ticker:
                    st.error("Le ticker est obligatoire.")
                elif stop_loss >= prix_entree:
                    st.error("Le Stop Loss doit être inférieur au prix d'entrée.")
                elif take_profit <= prix_entree:
                    st.error("Le Take Profit doit être supérieur au prix d'entrée.")
                else:
                    add_trade(
                        username, ticker, str(date_entree), prix_entree,
                        stop_loss, take_profit, quantite, notes, devise
                    )
                    st.success(f"✅ Trade {ticker} ({devise}) sauvegardé !")
                    st.rerun()

    # --- CHARGER LES TRADES ---
    st.warning(f"DEBUG - username reçu: '{username}'")
    rows = get_all_trades(username)
    rows = get_all_trades(username)
    if not rows:
        st.info("Aucun trade enregistré pour l'instant.")
        return

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.drop(columns=["Créé le"])

    # --- STATISTIQUES ---
    stats = calculate_stats(df, usdcad_rate)
    if stats:
        st.subheader("📊 Statistiques globales (en CAD)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Win Rate",
            f"{stats['win_rate']:.1f}%",
            help="Pourcentage de trades gagnants."
        )
        c2.metric(
            "P&L Total (CAD)",
            f"{stats['total_pnl_cad']:+.2f} $CAD",
            help=f"Tout converti en CAD au taux {usdcad_rate}"
        )
        c3.metric(
            "Gain moyen (CAD)",
            f"{stats['avg_win_cad']:+.2f} $CAD"
        )
        c4.metric(
            "Profit Factor",
            f"{stats['profit_factor']:.2f}",
            help="Au-dessus de 1.5 = solide. Au-dessus de 2.0 = excellent."
        )

        st.subheader("📊 Détail par devise")
        d1, d2 = st.columns(2)
        d1.metric(
            f"P&L USD ({stats['count_usd']} trades)",
            f"{stats['pnl_usd']:+.2f} $USD",
            f"≈ {stats['pnl_usd'] * usdcad_rate:+.2f} $CAD"
        )
        d2.metric(
            f"P&L CAD ({stats['count_cad']} trades)",
            f"{stats['pnl_cad_native']:+.2f} $CAD"
        )

        df_closed = stats["df_closed"].sort_values("Date Entrée")
        df_closed["P&L Cumulatif (CAD)"] = df_closed["P&L (CAD)"].cumsum()
        st.line_chart(df_closed.set_index("Date Entrée")["P&L Cumulatif (CAD)"])

    st.divider()

    # --- TRADES OUVERTS ---
    open_trades = df[df["Statut"] == "Ouvert"]
    if not open_trades.empty:
        st.subheader(f"🟡 Trades Ouverts ({len(open_trades)})")
        for _, row in open_trades.iterrows():
            devise_row = row.get("Devise", "USD")
            with st.expander(
                f"{row['Ticker']} ({devise_row}) — Entré le {row['Date Entrée']} à {row['Prix Entrée ($)']} ${devise_row}"
            ):
                col1, col2, col3, col4 = st.columns(4)
                col1.write(f"**Stop Loss :** {row['Stop Loss ($)']} ${devise_row}")
                col2.write(f"**Take Profit :** {row['Take Profit ($)']} ${devise_row}")
                col3.write(f"**Quantité :** {row['Qté']}")
                col4.write(f"**Devise :** {devise_row}")
                if row["Notes"]:
                    st.caption(f"📝 {row['Notes']}")

                st.markdown("**Fermer ce trade :**")
                with st.form(f"close_{row['ID']}"):
                    c1, c2, c3 = st.columns(3)
                    prix_sortie = c1.number_input(
                        f"Prix de sortie (${devise_row})", min_value=0.01, step=0.01, key=f"ps_{row['ID']}"
                    )
                    date_sortie = c2.date_input(
                        "Date de sortie", value=date.today(), key=f"ds_{row['ID']}"
                    )
                    statut_sortie = c3.selectbox(
                        "Résultat", ["Gagné", "Perdu"], key=f"st_{row['ID']}"
                    )

                    c_close, c_delete = st.columns(2)
                    if c_close.form_submit_button("✅ Fermer le trade", use_container_width=True):
                        close_trade(row["ID"], prix_sortie, str(date_sortie), statut_sortie)
                        st.success("Trade fermé !")
                        st.rerun()
                    if c_delete.form_submit_button("🗑️ Supprimer", use_container_width=True):
                        delete_trade(row["ID"])
                        st.warning("Trade supprimé.")
                        st.rerun()

    # --- HISTORIQUE ---
    closed_trades = df[df["Statut"].isin(["Gagné", "Perdu"])]
    if not closed_trades.empty:
        st.divider()
        st.subheader(f"📋 Historique ({len(closed_trades)} trades fermés)")
        st.dataframe(closed_trades, use_container_width=True, hide_index=True)