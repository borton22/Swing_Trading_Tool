# src/utils.py
import streamlit as st

def safe_rerun():
    """
    Compatibilité multi-versions pour relancer Streamlit.
    On essaye, dans l'ordre : st.rerun(), st.experimental_rerun(), puis levée de RerunException interne.
    Si tout échoue, on affiche un avertissement demandant un refresh manuel.
    """
    # 1) nouvelle API
    try:
        if hasattr(st, "rerun"):
            st.rerun()
            return
    except Exception:
        # on continue vers le fallback
        pass

    # 2) ancienne API
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
            return
    except Exception:
        pass

    # 3) tenter la RerunException interne (différents chemins selon versions)
    for path in (
        "streamlit.runtime.scriptrunner.script_runner",
        "streamlit.scriptrunner.script_runner",
        "streamlit.scriptrunner",
    ):
        try:
            mod = __import__(path, fromlist=["RerunException"])
            RerunException = getattr(mod, "RerunException")
            raise RerunException()
        except Exception:
            continue

    # 4) fallback : message à l'utilisateur
    try:
        st.session_state["_needs_manual_rerun"] = True
    except Exception:
        pass
    st.warning("Impossible de relancer automatiquement l'application — merci d'actualiser la page manuellement (F5).")