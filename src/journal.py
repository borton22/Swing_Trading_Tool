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
    get_connection,
)

# nouveau utils
from src.live_utils import (
    get_live_price,
    get_price_series,
    get_volume_series,
    compute_live_metrics,
    compute_decision_score,
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
                        ticker = ticker,
                        date_entree = str(date_entree),
                        prix_entree = prix_entree,
                        stop_loss = stop_loss,
                        take_profit = take_profit,
                        quantite = quantite,
                        username = username,
                        notes = notes,
                        devise = devise,
                    )
                    st.success(f"✅ Trade {ticker} ({devise}) sauvegardé !")
                    st.rerun()

    # --- CHARGER LES TRADES (robuste) ---
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE LOWER(username) = LOWER(?) ORDER BY date_entree DESC", (username,))
    rows = cursor.fetchall()
    db_cols_real = [description[0] for description in cursor.description]
    conn.close()

    if not rows:
        st.info("Aucun trade enregistré pour l'instant.")
        return

    df = pd.DataFrame(rows, columns=db_cols_real)

    rename_map = {
        "id": "ID",
        "ticker": "Ticker",
        "date_entree": "Date Entrée",
        "prix_entree": "Prix Entrée ($)",
        "stop_loss": "Stop Loss ($)",
        "take_profit": "Take Profit ($)",
        "quantite": "Qté",
        "statut": "Statut",
        "prix_sortie": "Prix Sortie ($)",
        "date_sortie": "Date Sortie",
        "notes": "Notes",
        "created_at": "Créé le",
        "devise": "Devise",
        "username": "Username"
    }

    df = df.rename(columns=rename_map)

    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None

    df = df[COLUMNS]

    # Conserver la valeur brute telle que lue de la DB (string) pour affichage exact si besoin
    if "Date Entrée" in df.columns:
        df["Date Entrée Raw"] = df["Date Entrée"].astype(str).str[:10]

    # -- Normaliser "Date Entrée" en date pure (YYYY-MM-DD) pour éviter les décalages timezone/heure --
    if "Date Entrée" in df.columns:
        try:
            df["Date Entrée"] = pd.to_datetime(
                df["Date Entrée"].astype(str).str[:10],
                errors="coerce",
                format="%Y-%m-%d"
            ).dt.date
        except Exception:
            st.warning("Impossible de normaliser 'Date Entrée' — affichage possible incorrect.")

    # Convert types
    if "Qté" in df.columns:
        df["Qté"] = pd.to_numeric(df["Qté"], errors="coerce").fillna(0).astype(int)
    for col in ["Prix Entrée ($)", "Stop Loss ($)", "Take Profit ($)", "Prix Sortie ($)"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep a display copy
    df_display = df.drop(columns=["Créé le"])

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

    # --- TRADES OUVERTS (avec decision engine) ---
    def fmt_date_safe(d):
        if d is None or (isinstance(d, float) and pd.isna(d)):
            return "N/A"
        if isinstance(d, pd.Timestamp):
            try:
                return pd.to_datetime(d).date().isoformat()
            except Exception:
                return str(d)
        if isinstance(d, date):
            return d.isoformat()
        return str(d)

    open_trades = df_display[df_display["Statut"] == "Ouvert"]
    if not open_trades.empty:
        st.subheader(f"🟡 Trades Ouverts ({len(open_trades)})")
        if st.button("🔄 Rafraîchir les prix live", key="refresh_live_prices_journal"):
            st.experimental_rerun()

        # Précharger séries / volumes pour tickers uniques
        tickers_needed = sorted(set(open_trades["Ticker"].dropna().astype(str).tolist()))
        series_cache = {}
        vol_cache = {}
        for t in tickers_needed:
            series_cache[t] = get_price_series(t, period="6mo", interval="1d")
            vol_cache[t] = get_volume_series(t, period="3mo", interval="1d")

        for idx, row in open_trades.iterrows():
            ticker = str(row["Ticker"])
            live_price, ts = get_live_price(ticker)
            metrics = compute_live_metrics(row, live_price) if live_price is not None else None
            price_series = series_cache.get(ticker, None)
            volume_series = vol_cache.get(ticker, None)

            # compute decision score + recommendation
            score, diag, recommended = compute_decision_score(
                row,
                price_series=price_series,
                live_price=live_price,
                volume_series=volume_series
            )

            # Header & color badge
            color_badge = "🟡"
            if metrics:
                if metrics["unrealized_pl"] > 0:
                    color_badge = "🟢"
                elif metrics["unrealized_pl"] < 0:
                    color_badge = "🔴"

            # Prefer the raw string date for header if available to avoid timezone shifts
            raw_date = row.get("Date Entrée Raw")
            if raw_date and isinstance(raw_date, str) and raw_date.strip():
                header_date = raw_date.strip()[:10]
            else:
                header_date = fmt_date_safe(row.get("Date Entrée"))

            header = f"{color_badge} {ticker} — Entré le {header_date} à {row['Prix Entrée ($)']} {row.get('Devise','')}"
            with st.expander(header, expanded=False):
                # Top line: price + score
                c1, c2, c3 = st.columns([1.2, 1, 1])
                if metrics:
                    c1.metric("Prix live", f"{metrics['live_price']:.2f}", delta=f"{metrics['unrealized_pct']:.2f}%")
                else:
                    c1.info("Prix live indisponible")

                # Score display
                score_pct = int(score * 100)
                if score >= 0.65:
                    c2.success(f"Score: {score_pct}% — KEEP")
                elif score >= 0.40:
                    c2.warning(f"Score: {score_pct}% — CAUTION")
                else:
                    c2.error(f"Score: {score_pct}% — CLOSE")

                # Recommended action
                c3.markdown(f"**Recommandation :** **{recommended}**")

                # Diagnostics summary
                st.markdown("**Diagnostics**")
                diag_cols = st.columns(3)
                diag_cols[0].write(f"Entrée : {diag.get('entry', 'N/A')}")
                diag_cols[0].write(f"Stop : {diag.get('stop', 'N/A')}")
                diag_cols[1].write(f"P&L% : {diag.get('pl_pct', 0):+.2f}%")
                diag_cols[1].write(f"Dist stop : {diag.get('dist_to_stop_pct', 0):+.2f}%")
                diag_cols[2].write(f"EMA50 : {diag.get('ema50', 'N/A')}")
                diag_cols[2].write(f"RSI : {diag.get('rsi', 'N/A')}")
                st.write("Raisons principales :")
                reasons = []
                # Compose human reasons from diag
                if diag.get("pl_pct", 0) < 0:
                    reasons.append(f"Prix < entrée ({diag.get('pl_pct'):.2f}%)")
                if diag.get("ema50") is not None and diag.get("live") < diag.get("ema50"):
                    reasons.append("Sous EMA50 (tendance affaiblie)")
                if diag.get("atr") is not None and diag.get("atr") > 0 and (diag.get("live") - diag.get("stop")) < diag.get("atr"):
                    reasons.append("Stop trop serré vs ATR")
                if diag.get("volume_penalty", 0) > 0:
                    reasons.append("Volume élevé sur mouvement adverse")
                if not reasons:
                    reasons.append("Aucun signal critique détecté")

                for r in reasons:
                    st.info(r)

                # Quick actions
                st.markdown("---")
                st.write("Actions rapides")
                # Copy for broker
                if st.button("Copier valeurs pour IBKR", key=f"copy_ibkr_{row['ID']}"):
                    st.code(f"TICKER : {ticker}\nQUANTITÉ : {row['Qté']}\nORDRE : LIMIT @ {row['Prix Entrée ($)']}\nSTOP LOSS : {row['Stop Loss ($)']}\nTARGET : {row['Take Profit ($)']}")

                # Action buttons: Tighten stop, Reduce position, Close
                a1, a2, a3 = st.columns(3)
                if a1.button("🔒 Tighten stop (breakeven+1%)", key=f"tighten_{row['ID']}"):
                    new_stop = float(row["Prix Entrée ($)"])  # exemple : move to entry
                    st.info(f"Nouvel stop proposé : {new_stop:.2f}. (A implémenter : update_trade_stop)")
                if a2.button("➗ Réduire position 25%", key=f"reduce_{row['ID']}"):
                    st.info("Action: réduire position de 25% manuellement dans le broker.")
                if a3.button("⛔ Fermer maintenant", key=f"close_now_{row['ID']}"):
                    st.warning("Utilise la section 'Fermer ce trade' ci‑dessous pour enregistrer la fermeture.")

                # Close form (identique à ton existing close form)
                st.markdown("---")
                with st.form(f"close_{row['ID']}", clear_on_submit=False):
                    f1, f2, f3 = st.columns(3)
                    prix_sortie = f1.number_input(
                        f"Prix de sortie ({row.get('Devise','')})", min_value=0.01, step=0.01, key=f"ps_{row['ID']}"
                    )
                    date_sortie = f2.date_input(
                        "Date de sortie", value=date.today(), key=f"ds_{row['ID']}"
                    )
                    statut_sortie = f3.selectbox(
                        "Résultat", ["Gagné", "Perdu"], key=f"st_{row['ID']}"
                    )
                    c_close, c_delete = st.columns(2)
                    if c_close.form_submit_button("✅ Fermer le trade", use_container_width=True):
                        close_trade(row["ID"], prix_sortie, str(date_sortie), statut_sortie)
                        st.success("Trade fermé !")
                        st.experimental_rerun()
                    if c_delete.form_submit_button("🗑️ Supprimer", use_container_width=True):
                        delete_trade(row["ID"])
                        st.warning("Trade supprimé.")
                        st.experimental_rerun()

    # --- HISTORIQUE ---
    closed_trades = df_display[df_display["Statut"].isin(["Gagné", "Perdu"])]
    if not closed_trades.empty:
        st.divider()
        st.subheader(f"📋 Historique ({len(closed_trades)} trades fermés)")
        st.dataframe(closed_trades, use_container_width=True, hide_index=True)