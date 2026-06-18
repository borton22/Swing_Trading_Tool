# generate_hashes_passlib.py
import json
from pathlib import Path
from passlib.hash import pbkdf2_sha256

BASE_DIR = Path(__file__).resolve().parent
OUT_FILE = BASE_DIR / ".users.json"

# ----- Définis les utilisateurs ET leurs mots de passe bruts ICI (exécution locale uniquement) -----
users_input = {
    "FrankB": {"name": "François Baron", "password": "FrankB123321"},
    "Invite": {"name": "Invite", "password": "Invite321321"},
}

# ----- Génération des hashes PBKDF2-SHA256 (29000 rounds, format compatible) -----
hashed_users = {}
for username, meta in users_input.items():
    pwd = meta["password"]
    # rounds 29000 -> format similaire à ce que streamlit_authenticator produit
    hashed = pbkdf2_sha256.using(rounds=29000).hash(pwd)
    hashed_users[username] = {"name": meta["name"], "password": hashed}

users_json = {"usernames": hashed_users}

# Écrire .users.json (local, NE PAS COMMIT)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(users_json, f, indent=2, ensure_ascii=False)

print(f".users.json créé en local : {OUT_FILE}")
print("Vérifie le contenu puis ajoute .users.json à .gitignore pour ne pas le committer.")