# create_user.py
import json
import os
import getpass
import streamlit_authenticator as stauth

OUT_PATH = ".users.json"
MAX_PWD_BYTES = 72

def truncate_pwd(pwd: str, max_bytes: int = MAX_PWD_BYTES) -> str:
    b = pwd.encode("utf-8")[:max_bytes]
    return b.decode("utf-8", errors="ignore")

def hash_passwords(pwds):
    # Compatibilité avec différentes versions de streamlit_authenticator
    try:
        hasher = stauth.Hasher()
        # préférer hash_list si disponible
        if hasattr(hasher, "hash_list"):
            return hasher.hash_list(pwds)
        elif hasattr(hasher, "generate"):
            return hasher.generate(pwds)
    except Exception as e:
        # dernier recours : essayer l'ancienne signature
        try:
            return stauth.Hasher(pwds).generate()
        except Exception:
            raise RuntimeError(f"Impossible de hacher les mots de passe: {e}")

def main():
    username = input("Nom d'utilisateur (login) : ").strip()
    display_name = input("Nom affiché (display name) [optionnel] : ").strip() or username
    pwd = getpass.getpass("Mot de passe (invisible) : ")
    pwd = truncate_pwd(pwd)

    hashed = hash_passwords([pwd])[0]

    users_structure = {
        "usernames": {
            username: {
                "name": display_name,
                "password": hashed
            }
        }
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(users_structure, f, indent=2, ensure_ascii=False)

    print(f"\nFichier '{OUT_PATH}' créé avec succès. Ne l'ajoute pas au dépôt git (il doit être git-ignored).")

if __name__ == "__main__":
    main()