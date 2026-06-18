# reset_user.py (interactive)
import json
import getpass
import streamlit_authenticator as stauth

OUT_PATH = ".users.json"
MAX_PWD_BYTES = 72

def truncate_pwd(pwd: str, max_bytes: int = MAX_PWD_BYTES) -> str:
    b = pwd.encode("utf-8")[:max_bytes]
    return b.decode("utf-8", errors="ignore")

username = input("Nom d'utilisateur (login) : ").strip()
display_name = input("Nom affiché (optionnel) : ").strip() or username
pwd = getpass.getpass("Nouveau mot de passe : ")
pwd = truncate_pwd(pwd)

# hash (compatible différentes versions)
hasher = stauth.Hasher()
try:
    hashed = hasher.hash_list([pwd])[0]
except Exception:
    hashed = hasher.generate([pwd])[0]

data = {"usernames": {username: {"name": display_name, "password": hashed}}}
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Fichier '{OUT_PATH}' mis à jour. Ne pas partager ce fichier.")