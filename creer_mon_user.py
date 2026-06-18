# creer_mon_user.py (version simple)
import json
import streamlit_authenticator as stauth

# --- MODIFIE ICI AVANT D'EXÉCUTER ---
username = "ton_pseudo"        # <-- remplace par le login désiré
display_name = "Ton Nom"       # <-- optionnel
mot_de_passe = "ton_mot_de_passe"  # <-- remplace (max ~72 bytes)
# -----------------------------------

# tronquer à 72 bytes pour éviter l'erreur bcrypt
mot_de_passe = mot_de_passe.encode("utf-8")[:72].decode("utf-8", errors="ignore")

# hachage (compatible versions)
hasher = stauth.Hasher()
try:
    pwd_hash = hasher.hash_list([mot_de_passe])[0]
except Exception:
    pwd_hash = hasher.generate([mot_de_passe])[0]

data = {
    "usernames": {
        username: {
            "name": display_name,
            "password": pwd_hash
        }
    }
}

with open(".users.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

print("✅ .users.json créé. Ne pousse pas ce fichier dans Git.")