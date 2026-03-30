#!/usr/bin/env python3
"""
test_schema.py - Tests de validation JSON Schema MongoDB
Vérifie que les contraintes de schéma rejettent correctement les documents invalides.

Usage : python test_schema.py
"""

from datetime import datetime
from bson import ObjectId
from pymongo.errors import WriteError

from init_db import get_database

# ---------------------------------------------------------------------------
#  Utilitaire
# ---------------------------------------------------------------------------

PASS = "\033[92m  [PASS]\033[0m"
FAIL = "\033[91m  [FAIL]\033[0m"
INFO = "\033[94m  [INFO]\033[0m"

_fake_id = ObjectId()  # ObjectId générique pour les champs requis

_resultats = {"pass": 0, "fail": 0}


def test_rejet(label: str, collection, document: dict):
    """Vérifie qu'un document invalide est bien rejeté par MongoDB."""
    try:
        collection.insert_one(document)
        # Si on arrive ici, MongoDB n'a PAS rejeté → test échoue
        # On essaie de nettoyer le document inséré
        collection.delete_one({"_id": document.get("_id")})
        print(f"{FAIL} {label} → non rejeté (schéma trop permissif ?)")
        _resultats["fail"] += 1
    except WriteError:
        print(f"{PASS} {label} → correctement rejeté par MongoDB")
        _resultats["pass"] += 1


def test_accepte(label: str, collection, document: dict):
    """Vérifie qu'un document valide est bien accepté par MongoDB."""
    try:
        result = collection.insert_one(document)
        collection.delete_one({"_id": result.inserted_id})
        print(f"{PASS} {label} → accepté comme attendu")
        _resultats["pass"] += 1
    except WriteError as e:
        print(f"{FAIL} {label} → rejeté à tort : {e.details.get('errmsg', e)}")
        _resultats["fail"] += 1


# ---------------------------------------------------------------------------
#  Tests collection members
# ---------------------------------------------------------------------------

def tests_members(db):
    col = db.members
    print("\n── Collection members ──────────────────────────────────────────")

    base_valide = {
        "nom": "Test", "prenom": "Schema",
        "email": "test.schema@example.com",
        "role": "developpeur",
        "competences": ["Python"],
        "date_embauche": datetime(2023, 1, 15)
    }

    # Document valide — doit être accepté
    test_accepte("Document valide", col, {**base_valide})

    # Email sans arobase
    test_rejet("Email sans @", col, {**base_valide, "email": "emailinvalide.com"})

    # Rôle non autorisé (hors de l'enum)
    test_rejet("Rôle invalide 'stagiaire'", col, {**base_valide, "role": "stagiaire"})

    # Champ requis manquant : prenom
    doc_sans_prenom = {k: v for k, v in base_valide.items() if k != "prenom"}
    test_rejet("Champ requis 'prenom' absent", col, doc_sans_prenom)

    # Champ requis manquant : email
    doc_sans_email = {k: v for k, v in base_valide.items() if k != "email"}
    test_rejet("Champ requis 'email' absent", col, doc_sans_email)

    # competences pas un tableau
    test_rejet("competences n'est pas un tableau", col, {**base_valide, "competences": "Python"})


# ---------------------------------------------------------------------------
#  Tests collection projects
# ---------------------------------------------------------------------------

def tests_projects(db):
    col = db.projects
    print("\n── Collection projects ─────────────────────────────────────────")

    base_valide = {
        "nom": "Projet Test",
        "description": "Test de validation",
        "date_debut": datetime(2024, 1, 1),
        "date_fin_prevue": datetime(2024, 12, 31),
        "date_fin_reelle": None,
        "statut": "en_cours",
        "budget": 10000.0,
        "chef_projet_id": _fake_id
    }

    # Document valide
    test_accepte("Document valide", col, {**base_valide})

    # Statut invalide (hors enum)
    test_rejet("Statut invalide 'actif'", col, {**base_valide, "statut": "actif"})

    # Budget négatif
    test_rejet("Budget négatif", col, {**base_valide, "budget": -500.0})

    # Champ requis manquant : nom
    doc_sans_nom = {k: v for k, v in base_valide.items() if k != "nom"}
    test_rejet("Champ requis 'nom' absent", col, doc_sans_nom)

    # chef_projet_id n'est pas un ObjectId
    test_rejet("chef_projet_id n'est pas un ObjectId", col,
               {**base_valide, "chef_projet_id": "pas-un-objectid"})


# ---------------------------------------------------------------------------
#  Tests collection tasks
# ---------------------------------------------------------------------------

def tests_tasks(db):
    col = db.tasks
    print("\n── Collection tasks ────────────────────────────────────────────")

    base_valide = {
        "titre": "Tâche de test",
        "description": "Description",
        "projet_id": _fake_id,
        "assignee_id": _fake_id,
        "statut": "todo",
        "priorite": "medium",
        "date_debut": datetime(2024, 1, 1),
        "date_echeance": datetime(2024, 3, 31),
        "date_fin_reelle": None,
        "temps_estime_heures": 8.0,
        "temps_reel_heures": None
    }

    # Document valide
    test_accepte("Document valide", col, {**base_valide})

    # Statut invalide
    test_rejet("Statut invalide 'pending'", col, {**base_valide, "statut": "pending"})

    # Priorité invalide
    test_rejet("Priorité invalide 'urgent'", col, {**base_valide, "priorite": "urgent"})

    # Temps estimé négatif
    test_rejet("temps_estime_heures négatif", col,
               {**base_valide, "temps_estime_heures": -2.0})

    # Champ requis manquant : titre
    doc_sans_titre = {k: v for k, v in base_valide.items() if k != "titre"}
    test_rejet("Champ requis 'titre' absent", col, doc_sans_titre)

    # Champ requis manquant : statut
    doc_sans_statut = {k: v for k, v in base_valide.items() if k != "statut"}
    test_rejet("Champ requis 'statut' absent", col, doc_sans_statut)


# ---------------------------------------------------------------------------
#  Point d'entrée
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  TESTS DE VALIDATION JSON SCHEMA — MongoDB")
    print("=" * 65)
    print(f"{INFO} Connexion à MongoDB...")

    client, db = get_database()

    try:
        tests_members(db)
        tests_projects(db)
        tests_tasks(db)
    finally:
        client.close()

    total = _resultats["pass"] + _resultats["fail"]
    print("\n" + "=" * 65)
    print(f"  Résultats : {_resultats['pass']}/{total} tests passés", end="")
    if _resultats["fail"] == 0:
        print("  \033[92m✓ Tous les tests sont OK\033[0m")
    else:
        print(f"  \033[91m✗ {_resultats['fail']} test(s) échoué(s)\033[0m")
    print("=" * 65)


if __name__ == "__main__":
    main()
