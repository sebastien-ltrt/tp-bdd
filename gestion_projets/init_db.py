#!/usr/bin/env python3
"""
init_db.py - Initialisation de la base de données MongoDB
Crée les collections avec validation JSON Schema et les index pertinents.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid, ConnectionFailure


# --- Configuration ---
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "gestion_projets"


def get_database():
    """Connexion à MongoDB et retourne la base de données."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Vérification de la connexion
        client.admin.command("ping")
        print("✓ Connexion à MongoDB réussie.")
        return client, client[DB_NAME]
    except ConnectionFailure as e:
        print(f"✗ Impossible de se connecter à MongoDB : {e}")
        raise SystemExit(1)


def creer_collection_members(db):
    """Crée la collection 'members' avec validation JSON Schema."""
    schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["nom", "prenom", "email", "role", "competences", "date_embauche"],
            "properties": {
                "nom": {
                    "bsonType": "string",
                    "description": "Nom de famille du membre"
                },
                "prenom": {
                    "bsonType": "string",
                    "description": "Prénom du membre"
                },
                "email": {
                    "bsonType": "string",
                    "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                    "description": "Adresse email valide"
                },
                "role": {
                    "bsonType": "string",
                    "enum": ["developpeur", "designer", "chef_projet", "testeur", "devops", "analyste"],
                    "description": "Rôle dans l'équipe"
                },
                "competences": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"},
                    "description": "Liste des compétences"
                },
                "date_embauche": {
                    "bsonType": "date",
                    "description": "Date d'embauche"
                }
            }
        }
    }

    try:
        db.create_collection("members", validator=schema)
        print("  ✓ Collection 'members' créée avec validation.")
    except CollectionInvalid:
        # La collection existe déjà, on met à jour le validateur
        db.command("collMod", "members", validator=schema)
        print("  ✓ Collection 'members' mise à jour (existait déjà).")


def creer_collection_projects(db):
    """Crée la collection 'projects' avec validation JSON Schema."""
    schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["nom", "description", "date_debut", "date_fin_prevue", "statut", "budget", "chef_projet_id"],
            "properties": {
                "nom": {
                    "bsonType": "string",
                    "description": "Nom du projet"
                },
                "description": {
                    "bsonType": "string",
                    "description": "Description du projet"
                },
                "date_debut": {
                    "bsonType": "date",
                    "description": "Date de début du projet"
                },
                "date_fin_prevue": {
                    "bsonType": "date",
                    "description": "Date de fin prévue"
                },
                "date_fin_reelle": {
                    "bsonType": ["date", "null"],
                    "description": "Date de fin réelle (null si en cours)"
                },
                "statut": {
                    "bsonType": "string",
                    "enum": ["planifie", "en_cours", "termine", "annule", "en_pause"],
                    "description": "Statut du projet"
                },
                "budget": {
                    "bsonType": "double",
                    "minimum": 0,
                    "description": "Budget alloué en euros"
                },
                "chef_projet_id": {
                    "bsonType": "objectId",
                    "description": "Référence vers le chef de projet (members._id)"
                }
            }
        }
    }

    try:
        db.create_collection("projects", validator=schema)
        print("  ✓ Collection 'projects' créée avec validation.")
    except CollectionInvalid:
        db.command("collMod", "projects", validator=schema)
        print("  ✓ Collection 'projects' mise à jour (existait déjà).")


def creer_collection_tasks(db):
    """
    Crée la collection 'tasks' avec validation JSON Schema.

    Choix d'architecture : RÉFÉRENCEMENT (et non imbrication)
    ---------------------------------------------------------
    Les tâches sont stockées dans une collection séparée avec des références
    (projet_id, assignee_id) plutôt qu'imbriquées dans les projets car :
    1. Un projet peut avoir des dizaines de tâches → le document projet deviendrait
       trop volumineux (limite 16 Mo par document).
    2. On a besoin de requêter les tâches indépendamment des projets
       (ex: tâches en retard tous projets confondus, charge par membre).
    3. Les tâches sont fréquemment mises à jour (statut, temps réel) →
       modifier un sous-document imbriqué est plus coûteux.
    4. Les agrégations et vues MongoDB fonctionnent mieux avec des collections
       séparées via $lookup.
    """
    schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["titre", "projet_id", "assignee_id", "statut", "priorite",
                         "date_debut", "date_echeance", "temps_estime_heures"],
            "properties": {
                "titre": {
                    "bsonType": "string",
                    "description": "Titre de la tâche"
                },
                "description": {
                    "bsonType": "string",
                    "description": "Description détaillée"
                },
                "projet_id": {
                    "bsonType": "objectId",
                    "description": "Référence vers le projet (projects._id)"
                },
                "assignee_id": {
                    "bsonType": "objectId",
                    "description": "Référence vers le membre assigné (members._id)"
                },
                "statut": {
                    "bsonType": "string",
                    "enum": ["todo", "in_progress", "done", "blocked"],
                    "description": "Statut de la tâche"
                },
                "priorite": {
                    "bsonType": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Niveau de priorité"
                },
                "date_debut": {
                    "bsonType": "date",
                    "description": "Date de début"
                },
                "date_echeance": {
                    "bsonType": "date",
                    "description": "Date d'échéance"
                },
                "date_fin_reelle": {
                    "bsonType": ["date", "null"],
                    "description": "Date de fin réelle"
                },
                "temps_estime_heures": {
                    "bsonType": "double",
                    "minimum": 0,
                    "description": "Temps estimé en heures"
                },
                "temps_reel_heures": {
                    "bsonType": ["double", "null"],
                    "minimum": 0,
                    "description": "Temps réellement passé en heures"
                }
            }
        }
    }

    try:
        db.create_collection("tasks", validator=schema)
        print("  ✓ Collection 'tasks' créée avec validation.")
    except CollectionInvalid:
        db.command("collMod", "tasks", validator=schema)
        print("  ✓ Collection 'tasks' mise à jour (existait déjà).")


def creer_index(db):
    """Crée les index pour optimiser les requêtes fréquentes."""
    # Members
    db.members.create_index("email", unique=True, name="idx_email_unique")
    db.members.create_index("role", name="idx_role")
    print("  ✓ Index sur 'members' créés (email unique, role).")

    # Projects
    db.projects.create_index("statut", name="idx_statut")
    db.projects.create_index("chef_projet_id", name="idx_chef_projet")
    db.projects.create_index("date_fin_prevue", name="idx_date_fin_prevue")
    print("  ✓ Index sur 'projects' créés (statut, chef_projet_id, date_fin_prevue).")

    # Tasks — les requêtes les plus fréquentes
    db.tasks.create_index("projet_id", name="idx_projet")
    db.tasks.create_index("assignee_id", name="idx_assignee")
    db.tasks.create_index("statut", name="idx_task_statut")
    db.tasks.create_index("date_echeance", name="idx_echeance")
    # Index composé pour la requête "tâches en retard"
    db.tasks.create_index(
        [("statut", ASCENDING), ("date_echeance", ASCENDING)],
        name="idx_statut_echeance"
    )
    # Index composé pour la charge par membre
    db.tasks.create_index(
        [("assignee_id", ASCENDING), ("statut", ASCENDING)],
        name="idx_assignee_statut"
    )
    print("  ✓ Index sur 'tasks' créés (projet, assignee, statut, échéance, composés).")


def initialiser():
    """Point d'entrée : initialise toute la base de données."""
    print("=" * 60)
    print("  INITIALISATION DE LA BASE DE DONNÉES")
    print("=" * 60)

    client, db = get_database()

    print("\n--- Création des collections ---")
    creer_collection_members(db)
    creer_collection_projects(db)
    creer_collection_tasks(db)

    print("\n--- Création des index ---")
    creer_index(db)

    print("\n" + "=" * 60)
    print("  BASE DE DONNÉES INITIALISÉE AVEC SUCCÈS")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    initialiser()
