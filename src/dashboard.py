# src/dashboard.py
import streamlit as st
import pandas as pd
import sys
import os
import subprocess
import pytz
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import get_processed_data, get_live_price
from src.signals import detect_pullback_setup, get_last_signal
from src.sizer import calculate_position_size
from src.database import init_db
from src.journal import show_journal
from config import UNIVERSE, CAPITAL_INITIAL, RISK_PER_TRADE, USERS

init_db()

st.set_page_config(page_title="Swing Trader Quebec", layout="wide")

# ==================== AUTHENTIFICATION ====================
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    USERS["credentials"],
    USERS["cookie"]["name"],
    USERS["cookie"]["key"],
    USERS["cookie"]["expiry_days"]
)

# On appelle login, mais on ne récupère pas les variables ici
authenticator.login(location="main")

# On récupère le statut et les infos depuis l'objet lui-même
auth_status = st.session_state.get("authentication_status")
username    = st.session_state.get("username")
name        = st.session_state.get("name")

if auth_status is False:
    st.error("❌ Nom d'utilisateur ou mot de passe incorrect.")
    st.stop()

elif auth_status is None:
    st.warning("👆 Entrez vos identifiants pour accéder à l'application.")
    st.stop()

# ==================== APP PRINCIPALE (si connecté) ====================
st.title("📈 Swing Trader Dashboard")

# --- BARRE LATÉRALE ---
st.sidebar.header("Paramètres")
st.sidebar.markdown(f"👤 **{name}**")
authenticator.logout("🚪 Déconnexion", "sidebar")
st.sidebar.divider()

capital = st.sidebar.number_input(
    "Capital ($)",
    value=float(CAPITAL_INITIAL),
    help="Capital total utilisé pour calculer la taille des positions."
)

risk = st.sidebar.slider(
    "Risque par trade (%)",
    0.1, 2.0,
    float(RISK_PER_TRADE * 100),
    help="Perte max acceptée sur UN trade, en % du capital."
) / 100

max_gap = st.sidebar.slider(
    "Gap Max autorisé (%)",
    0.5, 3.0, 1.5,
    help="Si le prix du matin dépasse ce %, le signal devient invalide."
)

st.sidebar.divider()
st.sidebar.subheader("🔄 Mise à jour des données")

if st.sidebar.button(
    "📥 Télécharger clôtures du jour",
    use_container_width=True,
    help="À lancer après 16h05 (heure de New York)."
):
    with st.spinner("Téléchargement en cours..."):
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result = subprocess.run(
                [sys.executable, "scripts/daily_run.py"],
                capture_output=True,
                text=True,
                cwd=project_root
            )
            if result.returncode == 0:
                st.sidebar.success("✅ Données mises à jour !")
                st.rerun()
            else:
                st.sidebar.error("❌ Erreur lors de la mise à jour.")
                if result.stderr:
                    st.sidebar.code(result.stderr)
        except Exception as e:
            st.sidebar.error(f"Erreur: {e}")

# --- Heure NY ---
ny_tz = pytz.timezone("America/New_York")
now_ny = datetime.now(ny_tz)
hour_ny = now_ny.hour + now_ny.minute / 60.0
minutes_since_open = max(0, (hour_ny - 9.5) * 60)
today_ny = now_ny.strftime("%Y-%m-%d")

if 4.0 <= hour_ny < 9.5:
    market_status = "🟡 Pré-market"
elif 9.5 <= hour_ny < 16.0:
    market_status = "🟢 Marché ouvert"
else:
    market_status = "🔴 Marché fermé"

st.sidebar.divider()
st.sidebar.info(f"🕐 NY : {now_ny.strftime('%H:%M')} — {market_status}")

try:
    df_check = get_processed_data(UNIVERSE[0])
    if not df_check.empty:
        last_idx = df_check.index[-1]
        last_date = last_idx.strftime("%Y-%m-%d") if hasattr(last_idx, "strftime") else str(last_idx)
        st.sidebar.info(f"📅 Dernière date en DB : {last_date}")
except Exception:
    pass


# ==================== FONCTIONS UTILITAIRES ====================

def get_smart_verdict(live_p, stop, target, gap, max_gap):
    if gap > max_gap:
        return "🚫 Trop étendu", 0.0
    if gap < -2.0:
        return "⚠️ Gap baissier", 0.0
    risque = live_p - stop
    rendement = target - live_p
    if risque <= 0:
        return "🔴 Stop invalide", 0.0
    rr = rendement / risque
    if rr >= 2.0:
        return "✅ Entrée Idéale", rr
    elif 1.3 <= rr < 2.0:
        return "🟡 Entrée Acceptable", rr
    elif 1.0 <= rr < 1.3:
        return "🟠 R:R Limite", rr
    else:
        return "🔴 R:R Insuffisant", rr


def pick_last_completed_row(df: pd.DataFrame) -> pd.Series | None:
    if df is None or df.empty:
        return None
    last_idx = df.index[-1]
    last_date_str = last_idx.strftime("%Y-%m-%d") if hasattr(last_idx, "strftime") else str(last_idx)
    if (last_date_str == today_ny) and (hour_ny < 16.05) and (len(df) >= 2):
        return df.iloc[-2]
    return df.iloc[-1]


def get_timing_advice(ticker, live_p, entry_close, stop, target, rr, hour_ny):
    risque_par_action   = live_p - stop
    limite_abandon      = round(live_p + (risque_par_action * 0.5), 2)
    limite_invalidation = round(entry_close * 0.995, 2)

    if 15.5 <= hour_ny < 16.0:
        if rr >= 2.0:
            return {
                "emoji": "✅", "titre": "Fenêtre d'entrée optimale",
                "conseil": (
                    f"R:R de {rr:.2f} — Entrée idéale. "
                    f"Place ton ordre LIMIT à {live_p:.2f}$, "
                    f"Stop {stop:.2f}$, Target {target:.2f}$."
                ),
                "couleur": "success",
                "pourquoi": (
                    f"**Pourquoi maintenant ?** C'est la fenêtre idéale (15h30-16h00 NY). "
                    f"Les institutions placent leurs ordres finaux en fin de journée, ce qui confirme "
                    f"la direction du titre. Un R:R de {rr:.2f} signifie que pour chaque dollar risqué, "
                    f"tu en gagnes potentiellement {rr:.2f}. Au-dessus de 2.0, c'est mathématiquement "
                    f"avantageux même si tu as tort 40% du temps."
                )
            }
        elif rr >= 1.3:
            return {
                "emoji": "🟡", "titre": "Fenêtre d'entrée — R:R Acceptable",
                "conseil": (
                    f"R:R de {rr:.2f} (sous 2.0 mais acceptable). "
                    f"Entre seulement si prix stable entre {limite_invalidation:.2f}$ et {limite_abandon:.2f}$."
                ),
                "couleur": "warning",
                "pourquoi": (
                    f"**Pourquoi acceptable mais pas idéal ?** Le R:R de {rr:.2f} est positif mais "
                    f"sous notre seuil préféré de 2.0. Ça veut dire que tu dois avoir raison plus souvent "
                    f"pour être profitable à long terme. On entre quand même si le prix n'a pas trop bougé "
                    f"(entre {limite_invalidation:.2f}$ et {limite_abandon:.2f}$) car la tendance reste valide."
                )
            }
        else:
            return {
                "emoji": "🚫", "titre": "Fenêtre d'entrée — R:R insuffisant",
                "conseil": f"R:R de {rr:.2f} trop faible. Passe ton tour aujourd'hui.",
                "couleur": "error",
                "pourquoi": (
                    f"**Pourquoi on passe ?** Avec un R:R de {rr:.2f}, tu risques plus que ce que tu peux "
                    f"gagner. Sur 100 trades avec ce ratio, même en ayant raison 60% du temps, tu perdrais "
                    f"de l'argent. La discipline de passer son tour est ce qui sépare les traders "
                    f"profitables des autres."
                )
            }

    elif 11.5 <= hour_ny < 15.5:
        return {
            "emoji": "⏰", "titre": "Trop tôt — Attends la fin de journée",
            "conseil": (
                f"R:R actuel : {rr:.2f}. Attends 15h30 NY. "
                f"Si prix entre {limite_invalidation:.2f}$ et {limite_abandon:.2f}$ → entre. "
                f"Si prix > {limite_abandon:.2f}$ → abandonne. "
                f"Si prix < {limite_invalidation:.2f}$ → signal invalidé."
            ),
            "couleur": "info",
            "pourquoi": (
                f"**Pourquoi attendre ?** Entre 11h30 et 15h30 NY, le volume est faible "
                f"(les traders institutionnels sont au lunch ou en réunion). Les mouvements sont "
                f"souvent aléatoires et peu fiables. En attendant 15h30, tu laisses le marché "
                f"confirmer sa direction pour la clôture. Si {ticker} est encore fort à 15h30, "
                f"c'est un signe que les 'gros joueurs' veulent clôturer haut — c'est ton signal."
            )
        }

    elif 9.5 <= hour_ny < 11.5:
        return {
            "emoji": "⏳", "titre": "Ouverture — Trop volatile",
            "conseil": (
                f"Les 2 premières heures sont souvent erratiques. "
                f"R:R actuel : {rr:.2f}. Reviens à 15h30 pour décider."
            ),
            "couleur": "info",
            "pourquoi": (
                f"**Pourquoi éviter l'ouverture ?** Les 90 premières minutes sont dominées par "
                f"les réactions émotionnelles aux nouvelles de la nuit, les ordres accumulés overnight "
                f"et les algorithmes haute fréquence. Les prix peuvent faire des faux mouvements violents "
                f"dans les deux sens avant de trouver leur vraie direction. Attendre évite de se faire "
                f"'secouer' hors d'un bon trade par la volatilité initiale."
            )
        }

    elif 4.0 <= hour_ny < 9.5:
        return {
            "emoji": "🌅", "titre": "Pré-market — Prépare ton plan",
            "conseil": (
                f"R:R estimé : {rr:.2f}. Prépare ton ordre à l'avance. "
                f"Décision finale à 15h30-15h45 NY."
            ),
            "couleur": "info",
            "pourquoi": (
                f"**Pourquoi préparer maintenant ?** Le pré-market te donne le temps de calculer "
                f"tes niveaux sans pression. Note ton prix d'entrée ({live_p:.2f}$), ton stop "
                f"({stop:.2f}$) et ton objectif ({target:.2f}$). Quand le marché ouvre, tu exécutes "
                f"ton plan — tu ne décides plus sous l'émotion. Les traders professionnels arrivent "
                f"toujours avec un plan écrit avant l'ouverture."
            )
        }

    else:
        return {
            "emoji": "🔴", "titre": "Marché fermé",
            "conseil": "Ce signal sera réévalué demain matin à l'ouverture.",
            "couleur": "warning",
            "pourquoi": (
                "**Que faire maintenant ?** C'est le bon moment pour réviser tes trades ouverts, "
                "mettre à jour ton journal et télécharger les clôtures du jour (bouton dans la sidebar). "
                "Les meilleurs traders utilisent le soir pour analyser — pas pour trader."
            )
        }


def show_advice_box(advice, ticker):
    msg = f"{advice['emoji']} **{ticker} — {advice['titre']}**\n\n{advice['conseil']}"
    if advice["couleur"] == "success":
        st.success(msg)
    elif advice["couleur"] == "warning":
        st.warning(msg)
    elif advice["couleur"] == "error":
        st.error(msg)
    else:
        st.info(msg)

    with st.expander(f"🔍 Pourquoi ce conseil pour {ticker} ?"):
        st.markdown(advice["pourquoi"])


# ==================== CALCUL DES SIGNAUX ====================
results = []
for ticker in UNIVERSE:
    df = get_processed_data(ticker)
    df = detect_pullback_setup(df)

    if not df.empty and get_last_signal(df):
        last_row = pick_last_completed_row(df)
        if last_row is None:
            continue

        atr   = float(last_row["atr14"])
        entry = float(last_row["close"])
        stop  = entry - (2 * atr)

        sizing = calculate_position_size(capital, risk, entry, stop)

        if sizing["shares"] > 0:
            results.append({
                "Ticker":             ticker,
                "Entrée ($)":         round(entry, 2),
                "Stop ($)":           round(stop, 2),
                "Objectif ($)":       sizing["take_profit"],
                "Qté":                sizing["shares"],
                "Investissement ($)": sizing["total_cost"],
                "Risque ($)":         -abs(sizing["risk_amount"]),
                "Gain pot. ($)":      sizing["potential_profit"],
            })


# ==================== ONGLETS ====================
tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Scanner & Signaux",
    "☀️ Préparation Matinale",
    "📓 Journal des Trades",
    "📚 Guide & Logique"
])


# ==================== ONGLET 1 : SCANNER ====================
with tab1:

    with st.expander("ℹ️ Définitions (Paramètres & stratégie)"):
        st.markdown(
            "- **Capital ($)** : sert à calculer la taille de position.\n"
            "- **Risque par trade (%)** : perte max par trade.\n\n"
            "**Stratégie Pullback :**\n"
            "1) **Tendance** : `close > sma200`\n"
            "2) **Pullback** : `close < ema20`\n"
            "3) **Rebond** : bougie verte (`close > open`)\n\n"
            "**Stop** : `stop = entry - 2×ATR`  |  **Objectif** : `TP = entry + 2×(entry-stop)`\n"
        )

    st.subheader("🔍 Signaux et Plan d'Exécution")

    if results:
        df_res = pd.DataFrame(results)
        st.dataframe(df_res, use_container_width=True)

        with st.expander("📖 Définition des colonnes"):
            st.markdown(
                "- **Entrée ($)** : prix de clôture (dernier jour complété).\n"
                "- **Stop ($)** : niveau de sortie automatique.\n"
                "- **Objectif ($)** : niveau de prise de profit (2R).\n"
                "- **Qté** : nombre d'actions pour respecter ton risque.\n"
                "- **Risque ($)** : perte max si stop touché.\n"
                "- **Gain pot. ($)** : gain si objectif touché.\n"
            )

        risk_sum = float(df_res["Risque ($)"].abs().sum())
        gain_sum = float(df_res["Gain pot. ($)"].sum())
        st.warning(f"⚠️ Risque total : {risk_sum:.2f}$ | Gain potentiel total : {gain_sum:.2f}$")
    else:
        st.info("Aucun signal d'achat détecté. La patience est la clé du profit.")

    st.divider()
    st.subheader("📊 Graphique & indicateurs")

    selected_ticker = st.selectbox("Choisir un ticker", UNIVERSE)
    df_plot = get_processed_data(selected_ticker).tail(60)

    if df_plot.empty:
        st.warning("Pas de données à afficher.")
    else:
        st.caption("Lignes : close | SMA200 | EMA20")
        st.line_chart(df_plot[["close", "sma200", "ema20"]])

        last = df_plot.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("Close",  f"{float(last['close']):.2f}$")
        c2.metric("SMA200", f"{float(last['sma200']):.2f}$")
        c3.metric("ATR14",  f"{float(last['atr14']):.2f}$")

        with st.expander("ℹ️ Définitions (indicateurs)"):
            st.markdown(
                "- **SMA200** : moyenne 200 jours — tendance long terme.\n"
                "- **EMA20** : moyenne 20 jours — zone de pullback.\n"
                "- **ATR14** : volatilité moyenne 14 jours — sert au stop.\n"
            )


# ==================== ONGLET 2 : PRÉPARATION MATINALE ====================
with tab2:

    st.subheader("☀️ Préparation Matinale — Validation des Signaux")
    st.caption("À utiliser entre 8h00 et 9h30 (heure de New York) pour valider les signaux de la veille.")

    if 4.0 <= hour_ny < 9.5:
        st.info(f"🟡 Pré-market actif ({now_ny.strftime('%H:%M')} NY)")
    elif 9.5 <= hour_ny < 16.0:
        if minutes_since_open > 30:
            st.info(
                f"🟢 Marché ouvert ({now_ny.strftime('%H:%M')} NY) — "
                f"{int(minutes_since_open)} min depuis l'ouverture. "
                f"Le verdict dépend du R:R, pas de l'heure."
            )
        else:
            st.success(f"🟢 Marché ouvert ({now_ny.strftime('%H:%M')} NY) — Prix en temps réel.")
    else:
        st.warning(f"🔴 Marché fermé ({now_ny.strftime('%H:%M')} NY)")

    if not results:
        st.info("Aucun signal détecté. Rien à valider.")
    else:
        if st.button("🔄 Rafraîchir les prix live", use_container_width=False):
            st.rerun()

        st.markdown("### 📋 Tableau de décision")

        morning_data = []
        for r in results:
            ticker      = r["Ticker"]
            entry_close = r["Entrée ($)"]
            stop        = r["Stop ($)"]
            target      = r["Objectif ($)"]

            live_info = get_live_price(ticker)
            live_p    = live_info["price"]
            source    = live_info["source"]

            if live_p and source != "Fermé":
                gap = ((live_p - entry_close) / entry_close) * 100
                verdict, rr_val = get_smart_verdict(live_p, stop, target, gap, max_gap)
                sizing = calculate_position_size(capital, risk, live_p, stop)
                shares = sizing["shares"] if ("Idéale" in verdict or "Acceptable" in verdict) else 0

                morning_data.append({
                    "Ticker":        ticker,
                    "Clôture ($)":   entry_close,
                    "Prix Live ($)": round(live_p, 2),
                    "Source":        source,
                    "Gap (%)":       round(gap, 2),
                    "Stop ($)":      round(stop, 2),
                    "Objectif ($)":  round(target, 2),
                    "R:R Actuel":    round(rr_val, 2) if rr_val > 0 else "—",
                    "Qté":           shares,
                    "Verdict":       verdict,
                })
            else:
                morning_data.append({
                    "Ticker":        ticker,
                    "Clôture ($)":   entry_close,
                    "Prix Live ($)": "N/A",
                    "Source":        source,
                    "Gap (%)":       "N/A",
                    "Stop ($)":      round(stop, 2),
                    "Objectif ($)":  round(target, 2),
                    "R:R Actuel":    "—",
                    "Qté":           0,
                    "Verdict":       "⏸️ Marché fermé" if source == "Fermé" else "❓ Indisponible",
                })

        df_morning = pd.DataFrame(morning_data)
        st.dataframe(df_morning, use_container_width=True)

        verdicts  = [x["Verdict"] for x in morning_data]
        nb_ideal  = sum(1 for v in verdicts if "Idéale" in v)
        nb_ok     = sum(1 for v in verdicts if "Acceptable" in v)
        nb_limite = sum(1 for v in verdicts if "Limite" in v)
        nb_eviter = sum(1 for v in verdicts if ("🔴" in v or "🚫" in v or "⚠️" in v))

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("✅ Entrées Idéales", nb_ideal)
        col_s2.metric("🟡 Acceptables",     nb_ok)
        col_s3.metric("🟠 Limites",         nb_limite)
        col_s4.metric("🔴 À éviter",        nb_eviter)

        st.divider()
        st.markdown("### 💡 Conseils du Moment")

        valid_rows = [
            x for x in morning_data
            if "Idéale" in x["Verdict"] or "Acceptable" in x["Verdict"]
        ]

        if not valid_rows:
            st.info("🤷 Aucun signal actionnable en ce moment. Patience.")
        else:
            for row in valid_rows:
                try:
                    live_p  = float(row["Prix Live ($)"])
                    rr_val  = float(row["R:R Actuel"])
                except Exception:
                    continue

                advice = get_timing_advice(
                    ticker      = row["Ticker"],
                    live_p      = live_p,
                    entry_close = float(row["Clôture ($)"]),
                    stop        = float(row["Stop ($)"]),
                    target      = float(row["Objectif ($)"]),
                    rr          = rr_val,
                    hour_ny     = hour_ny
                )
                show_advice_box(advice, row["Ticker"])

        st.divider()
        st.markdown("### 🎯 Plan d'exécution détaillé")

        valid_tickers = [
            x["Ticker"] for x in morning_data
            if ("Idéale" in x["Verdict"] or "Acceptable" in x["Verdict"])
        ]

        if not valid_tickers:
            st.warning("Aucun signal avec un R:R suffisant ce matin.")
        else:
            chosen      = st.selectbox("Ticker à exécuter :", valid_tickers)
            chosen_data = next((x for x in morning_data if x["Ticker"] == chosen), None)

            try:
                live_p  = float(chosen_data["Prix Live ($)"])
                live_ok = True
            except Exception:
                live_ok = False

            if chosen_data and live_ok:
                stop       = float(chosen_data["Stop ($)"])
                rr_val     = chosen_data["R:R Actuel"]
                verdict    = chosen_data["Verdict"]
                source     = chosen_data["Source"]
                gap        = chosen_data["Gap (%)"]
                sizing     = calculate_position_size(capital, risk, live_p, stop)
                shares     = sizing["shares"]
                r_cash     = sizing["risk_amount"]
                total_cost = sizing["total_cost"]
                tp_2r      = round(live_p + (live_p - stop) * 2, 2)

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.success(f"{verdict} — Source : {source}")
                    st.metric("Prix Live",          f"{live_p:.2f}$")
                    st.metric("Gap vs Clôture",     f"{gap:.2f}%")
                    st.metric("R:R Actuel",          f"{rr_val}")
                    st.metric("Quantité à acheter",  f"{shares} actions")
                    st.metric("Coût total",          f"{total_cost:.2f}$")
                    st.metric("Risque réel",         f"-{r_cash:.2f}$")

                with col2:
                    st.info("📋 Copie ces valeurs dans IBKR Mobile")
                    st.code(
                        f"TICKER    : {chosen}\n"
                        f"TYPE      : BUY (Long)\n"
                        f"QUANTITÉ  : {shares} actions\n"
                        f"ORDRE     : LIMIT @ {live_p:.2f}$\n"
                        f"STOP LOSS : {stop:.2f}$\n"
                        f"TARGET 2R : {tp_2r}$\n"
                        f"--------------------------\n"
                        f"R:R       : {rr_val}\n"
                        f"RISQUE    : {r_cash:.2f}$\n"
                        f"COÛT      : {total_cost:.2f}$",
                        language="text"
                    )

        st.divider()
        with st.expander("ℹ️ Comment lire ce tableau ?"):
            st.markdown(
                "- **Clôture ($)** : dernière clôture complétée.\n"
                "- **Gap (%)** : (Prix Live - Clôture) / Clôture.\n"
                "- **R:R Actuel** : ratio calculé avec le prix live.\n"
                "- **Conseil du Moment** : adapté à l'heure NY.\n"
            )


# ==================== ONGLET 3 : JOURNAL ====================
with tab3:
    show_journal(username)


# ==================== ONGLET 4 : GUIDE & LOGIQUE ====================
with tab4:

    st.markdown("## 📚 Guide du Swing Trader — Comprendre la logique du dashboard")
    st.caption("Lis ce guide une fois. Il explique pourquoi chaque décision est prise de cette façon.")

    with st.expander("📖 C'est quoi le Swing Trading ? (Point de départ)"):
        st.markdown(
            "Le **swing trading** consiste à capturer des mouvements de prix sur **2 à 10 jours**.\n\n"
            "Contrairement au day trading (acheter et vendre le même jour), tu :\n"
            "- Achètes en fin de journée après avoir identifié un signal\n"
            "- Laisses le trade évoluer pendant quelques jours\n"
            "- Vends quand ton objectif est atteint **ou** quand ton stop est touché\n\n"
            "**L'avantage principal :** Tu n'as pas besoin de surveiller l'écran toute la journée. "
            "Une vérification le matin (pré-market) et une en fin de journée (15h30-16h00 NY) suffisent."
        )

    with st.expander("📐 C'est quoi le R:R (Ratio Risque/Rendement) ?"):
        st.markdown(
            "Le **R:R** est le concept le plus important du trading.\n\n"
            "**Exemple concret avec COST :**\n"
            "- Prix d'entrée : **982$**\n"
            "- Stop Loss : **937$** → tu risques **45$**\n"
            "- Objectif : **1071$** → tu peux gagner **89$**\n"
            "- R:R = 89 / 45 = **~2.0**\n\n"
            "| R:R | Taux de réussite nécessaire |\n"
            "|-----|----------------------------|\n"
            "| 1:1 | 50%+ |\n"
            "| 2:1 | 34%+ ✅ |\n"
            "| 3:1 | 25%+ ✅✅ |"
        )

    with st.expander("🛑 C'est quoi le Stop Loss et pourquoi c'est non-négociable ?"):
        st.markdown(
            "`Stop = Prix d'entrée - (2 × ATR14)`\n\n"
            "**Règle d'or :** Une fois le trade placé, **ne jamais déplacer le stop vers le bas**."
        )

    with st.expander("⏰ Pourquoi on attend 15h30 pour entrer ?"):
        st.markdown(
            "- **9h30-11h30** 🔴 Ouverture chaotique — éviter\n"
            "- **11h30-15h30** 🟡 Volume faible — observer\n"
            "- **15h30-16h00** ✅ Clôture institutionnelle — agir"
        )

    with st.expander("📊 Comment fonctionne la stratégie Pullback ?"):
        st.markdown(
            "1. `Close > SMA200` → tendance haussière\n"
            "2. `Close < EMA20` → pullback temporaire\n"
            "3. `Close > Open`  → bougie verte (rebond confirmé)"
        )

    with st.expander("💰 Comment est calculée la taille de position (Qté) ?"):
        st.markdown(
            "**Formule :**\n\n"
            "- Risque en $ = Capital × Risque %\n"
            "- Quantité = Risque en $ / (Prix entrée - Stop)\n\n"
            "**Exemple :** Capital 10 000$, risque 1%, entrée 100$, stop 95$\n"
            "→ Risque = 100$ | Quantité = 100 / 5 = **20 actions**"
        )

    with st.expander("📋 Exemple complet d'un trade — De A à Z"):
        st.markdown(
            "**COST — Lundi matin**\n\n"
            "- Clôture : 982$, ATR14 : 22$, Stop : 938$, Objectif : 1070$, R:R : 2.0\n"
            "- Lundi 15h45 → ordre LIMIT à 983$\n"
            "- **Scénario A :** COST → 1070$ → +87$ 🎉\n"
            "- **Scénario B :** COST → 938$ → -45$ (planifié) ✅"
        )

    with st.expander("🚫 Les 5 erreurs classiques du débutant"):
        st.markdown(
            "1. Déplacer le stop vers le bas\n"
            "2. Prendre le profit trop tôt\n"
            "3. Entrer à l'ouverture (9h30-11h30)\n"
            "4. Ignorer le Gap\n"
            "5. Ne pas tenir de journal"
        )

    with st.expander("🗓️ Routine quotidienne recommandée"):
        st.markdown(
            "- **☀️ 8h00-9h15 NY** : Vérifier signaux, préparer ordres\n"
            "- **🎯 15h30-15h50 NY** : Exécuter si signal valide\n"
            "- **🌙 Après 16h05 NY** : Télécharger clôtures, mettre à jour journal\n\n"
            "**Temps total : ~20-30 min/jour.**"
        )

    st.divider()
    st.info(
        "💡 **Rappel important :** Ce dashboard est un outil d'aide à la décision, "
        "pas un oracle. L'objectif est d'avoir un **avantage mathématique** sur le long terme."
    )