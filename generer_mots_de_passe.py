import streamlit_authenticator as stauth

mots_de_passe = ["?ZQ1FM5*d0Z&evDj"]

# Compatibilité avec plusieurs versions
try:
    hasher = stauth.Hasher()
    hashs = hasher.hash_list(mots_de_passe)
except Exception:
    hasher = stauth.Hasher()
    hashs = hasher.generate(mots_de_passe)

print("Hashes générés :")
for h in hashs:
    print(h)