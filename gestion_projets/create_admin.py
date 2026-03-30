#!/usr/bin/env python3
"""
create_admin.py - Crée un compte administrateur
Usage : python create_admin.py [--username ADMIN] [--email ADMIN@EXAMPLE.COM]
        (interactif si les arguments sont omis)
"""

import argparse
import getpass
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

from init_db import get_database


def creer_admin(username: str, email: str, password: str) -> None:
    client, db = get_database()

    # Vérifier si l'username ou l'email existe déjà
    if db.users.find_one({"username": username}):
        print(f"✗ Un compte avec l'username '{username}' existe déjà.")
        client.close()
        sys.exit(1)

    if db.users.find_one({"email": email}):
        print(f"✗ Un compte avec l'email '{email}' existe déjà.")
        client.close()
        sys.exit(1)

    admin_doc = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "email": email,
        "app_role": "admin",
        "member_id": None,
        "is_active": True,
        "created_at": datetime.now(),
    }

    db.users.insert_one(admin_doc)
    print(f"\n✓ Compte administrateur créé avec succès.")
    print(f"  Username : {username}")
    print(f"  Email    : {email}")
    print(f"  Rôle     : admin")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Créer un compte administrateur")
    parser.add_argument("--username", help="Nom d'utilisateur")
    parser.add_argument("--email", help="Adresse email")
    args = parser.parse_args()

    print("=" * 50)
    print("  CRÉATION DU COMPTE ADMINISTRATEUR")
    print("=" * 50)

    username = args.username or input("Username [admin]: ").strip() or "admin"
    email = args.email or input("Email [admin@gestion-projets.fr]: ").strip() or "admin@gestion-projets.fr"

    password = getpass.getpass("Mot de passe : ")
    if not password:
        print("✗ Le mot de passe ne peut pas être vide.")
        sys.exit(1)

    confirm = getpass.getpass("Confirmer le mot de passe : ")
    if password != confirm:
        print("✗ Les mots de passe ne correspondent pas.")
        sys.exit(1)

    if len(password) < 6:
        print("✗ Le mot de passe doit contenir au moins 6 caractères.")
        sys.exit(1)

    creer_admin(username, email, password)


if __name__ == "__main__":
    main()
