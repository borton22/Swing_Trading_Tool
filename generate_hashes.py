# generate_hashes.py
import json
from streamlit_authenticator import Hasher
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT_FILE = BASE_DIR / ".users.json"

# ----- Définis les utilisateurs ET leurs mots de passe bruts ICI (exécution locale uniquement) -----
# Remplace les mots de passe par ceux que tu veux, puis exécute ce script localement.
users_input = {
    "FrankB": {"name": "François Baron", "password": "FrankB123321"},
    "Invite": {"name": "Invite", "password": "Invite321321"},
}

# ----- Génération des hashes -----
passwords = [v["password"] for v in users_input.values()]
# Correct usage: create Hasher() then call generate(passwords)
hashed_list = Hasher().generate(passwords)

# ----- Construire la structure attendue par streamlit_authenticator -----
usernames = {}
for (username, meta), hashed in zip(users_input.items(), hashed_list):
    usernames[username] = {
        "name": meta["name"],
        "password": hashed
    }

users_json = {"usernames": usernames}

# Écrire .users.json (local, NE PAS COMMIT)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(users_json, f, indent=2, ensure_ascii=False)

print(f".users.json créé en local : {OUT_FILE}")
print("N'OUBLIE PAS d'ajouter .users.json à .gitignore et de ne pas le committer.")