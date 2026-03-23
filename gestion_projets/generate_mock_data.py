#!/usr/bin/env python3
"""
generate_mock_data.py - Génération de données réalistes
Utilise Faker pour créer 10 membres, 5 projets et 40-50 tâches
avec des scénarios variés (en retard, terminées, en cours, bloquées).
"""

import random
from datetime import datetime, timedelta
from faker import Faker
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from init_db import get_database, initialiser

# Faker en français pour des noms réalistes
fake = Faker("fr_FR")
Faker.seed(42)
random.seed(42)


# --- Données de référence ---
COMPETENCES = [
    "Python", "JavaScript", "TypeScript", "React", "Angular", "Vue.js",
    "Node.js", "Django", "Flask", "FastAPI", "MongoDB", "PostgreSQL",
    "Docker", "Kubernetes", "AWS", "Azure", "Git", "CI/CD",
    "Scrum", "UX/UI", "Figma", "Java", "Go", "Rust",
    "Machine Learning", "Data Analysis", "Cybersécurité", "DevOps"
]

ROLES = ["developpeur", "designer", "chef_projet", "testeur", "devops", "analyste"]

NOMS_PROJETS = [
    "Refonte Site E-Commerce",
    "Application Mobile Santé",
    "Plateforme Data Analytics",
    "Migration Cloud Infrastructure",
    "Chatbot Service Client"
]

DESCRIPTIONS_PROJETS = [
    "Refonte complète du site e-commerce avec nouveau design et optimisation des performances.",
    "Développement d'une application mobile de suivi de santé pour les patients chroniques.",
    "Mise en place d'une plateforme d'analyse de données avec tableaux de bord interactifs.",
    "Migration de l'infrastructure on-premise vers le cloud AWS avec conteneurisation.",
    "Création d'un chatbot intelligent pour le service client avec traitement du langage naturel."
]

TITRES_TACHES = [
    "Maquettes UI/UX", "API REST utilisateurs", "Authentification JWT",
    "Base de données - modélisation", "Tests unitaires module paiement",
    "Intégration Stripe", "Page d'accueil responsive", "Système de notifications",
    "Pipeline CI/CD", "Documentation API", "Optimisation requêtes SQL",
    "Migration données legacy", "Conteneurisation Docker", "Tests d'intégration",
    "Revue de code sprint 3", "Déploiement staging", "Monitoring Grafana",
    "Gestion des erreurs API", "Cache Redis", "Recherche Elasticsearch",
    "Export CSV/PDF", "Gestion des rôles", "Tableau de bord admin",
    "Formulaire inscription", "Système de logs", "Backup automatique",
    "Tests de charge", "Sécurité - audit OWASP", "SSO entreprise",
    "Internationalisation i18n", "Mode hors-ligne", "Push notifications",
    "Synchronisation temps réel", "Analytics utilisateur", "Gestion des fichiers",
    "Workflow d'approbation", "Module de reporting", "API GraphQL",
    "Microservice facturation", "Migration vers TypeScript", "Refactoring module core",
    "Optimisation bundle front", "Tests E2E Cypress", "Configuration Terraform",
    "Mise à jour dépendances", "Correctif bug critique panier",
    "Amélioration performances requêtes", "Mise en place CDN",
    "Formation équipe React", "Documentation utilisateur"
]


def generer_membres(db):
    """Génère 10 membres d'équipe réalistes."""
    membres = []

    # S'assurer d'avoir au moins 2 chefs de projet
    roles_forces = ["chef_projet", "chef_projet"]
    roles_restants = [random.choice([r for r in ROLES if r != "chef_projet"]) for _ in range(8)]
    roles_tous = roles_forces + roles_restants
    random.shuffle(roles_tous)

    for i in range(10):
        prenom = fake.first_name()
        nom = fake.last_name()
        membre = {
            "nom": nom,
            "prenom": prenom,
            "email": f"{prenom.lower()}.{nom.lower()}@entreprise.fr",
            "role": roles_tous[i],
            "competences": random.sample(COMPETENCES, k=random.randint(3, 6)),
            "date_embauche": fake.date_time_between(
                start_date="-5y", end_date="-3m"
            )
        }
        membres.append(membre)

    result = db.members.insert_many(membres)
    print(f"  ✓ {len(result.inserted_ids)} membres insérés.")
    return result.inserted_ids


def generer_projets(db, membre_ids):
    """Génère 5 projets avec des statuts variés."""
    # Récupérer les chefs de projet
    chefs = list(db.members.find({"role": "chef_projet"}))
    if not chefs:
        # Fallback : prendre les 2 premiers membres
        chefs = list(db.members.find().limit(2))

    projets = []
    statuts = ["en_cours", "en_cours", "termine", "planifie", "en_cours"]

    for i in range(5):
        date_debut = fake.date_time_between(start_date="-8m", end_date="-2m")
        duree_prevue = random.randint(60, 180)  # 2 à 6 mois
        date_fin_prevue = date_debut + timedelta(days=duree_prevue)

        statut = statuts[i]
        date_fin_reelle = None
        if statut == "termine":
            # Terminé avec un léger retard ou en avance
            decalage = random.randint(-10, 20)
            date_fin_reelle = date_fin_prevue + timedelta(days=decalage)

        projet = {
            "nom": NOMS_PROJETS[i],
            "description": DESCRIPTIONS_PROJETS[i],
            "date_debut": date_debut,
            "date_fin_prevue": date_fin_prevue,
            "date_fin_reelle": date_fin_reelle,
            "statut": statut,
            "budget": round(random.uniform(15000, 150000), 2),
            "chef_projet_id": random.choice(chefs)["_id"]
        }
        projets.append(projet)

    result = db.projects.insert_many(projets)
    print(f"  ✓ {len(result.inserted_ids)} projets insérés.")
    return result.inserted_ids


def generer_taches(db, projet_ids, membre_ids):
    """
    Génère 40-50 tâches réalistes avec des scénarios variés :
    - Tâches terminées (done)
    - Tâches en cours (in_progress)
    - Tâches à faire (todo)
    - Tâches bloquées (blocked)
    - Tâches en retard (échéance passée mais pas terminées)
    """
    taches = []
    titres_disponibles = TITRES_TACHES.copy()
    random.shuffle(titres_disponibles)

    nb_taches = random.randint(40, 50)
    maintenant = datetime.now()

    for i in range(nb_taches):
        projet_id = random.choice(projet_ids)
        assignee_id = random.choice(membre_ids)

        # Récupérer le projet pour cohérence des dates
        projet = db.projects.find_one({"_id": projet_id})

        titre = titres_disponibles[i % len(titres_disponibles)]
        if i >= len(titres_disponibles):
            titre = f"{titre} (v{i // len(titres_disponibles) + 1})"

        # Dates cohérentes avec le projet
        date_debut_tache = fake.date_time_between(
            start_date=projet["date_debut"],
            end_date=min(projet["date_debut"] + timedelta(days=120), maintenant)
        )

        temps_estime = round(random.uniform(2, 40), 1)

        # Scénarios variés pour les tâches
        scenario = random.random()

        if scenario < 0.30:
            # 30% - Tâches terminées
            statut = "done"
            duree_jours = random.randint(3, 30)
            date_echeance = date_debut_tache + timedelta(days=duree_jours)
            # Terminée avant ou légèrement après l'échéance
            decalage = random.randint(-5, 3)
            date_fin_reelle = date_echeance + timedelta(days=decalage)
            temps_reel = round(temps_estime * random.uniform(0.7, 1.5), 1)

        elif scenario < 0.50:
            # 20% - Tâches EN RETARD (échéance passée, pas terminées)
            statut = random.choice(["in_progress", "todo", "blocked"])
            # Échéance dans le passé
            jours_retard = random.randint(5, 45)
            date_echeance = maintenant - timedelta(days=jours_retard)
            date_fin_reelle = None
            temps_reel = round(temps_estime * random.uniform(0.3, 0.8), 1) if statut == "in_progress" else None

        elif scenario < 0.75:
            # 25% - Tâches en cours (dans les temps)
            statut = "in_progress"
            date_echeance = maintenant + timedelta(days=random.randint(5, 60))
            date_fin_reelle = None
            temps_reel = round(temps_estime * random.uniform(0.2, 0.6), 1)

        elif scenario < 0.90:
            # 15% - Tâches à faire
            statut = "todo"
            date_echeance = maintenant + timedelta(days=random.randint(10, 90))
            date_fin_reelle = None
            temps_reel = None

        else:
            # 10% - Tâches bloquées
            statut = "blocked"
            date_echeance = maintenant + timedelta(days=random.randint(-10, 30))
            date_fin_reelle = None
            temps_reel = round(temps_estime * random.uniform(0.1, 0.4), 1)

        priorite = random.choices(
            ["low", "medium", "high", "critical"],
            weights=[15, 40, 30, 15],
            k=1
        )[0]

        tache = {
            "titre": titre,
            "description": fake.sentence(nb_words=12),
            "projet_id": projet_id,
            "assignee_id": assignee_id,
            "statut": statut,
            "priorite": priorite,
            "date_debut": date_debut_tache,
            "date_echeance": date_echeance,
            "date_fin_reelle": date_fin_reelle,
            "temps_estime_heures": float(temps_estime),
            "temps_reel_heures": float(temps_reel) if temps_reel is not None else None
        }
        taches.append(tache)

    result = db.tasks.insert_many(taches)
    print(f"  ✓ {len(result.inserted_ids)} tâches insérées.")

    # Statistiques des tâches générées
    compteurs = {}
    for t in taches:
        compteurs[t["statut"]] = compteurs.get(t["statut"], 0) + 1

    en_retard = sum(1 for t in taches
                    if t["statut"] != "done" and t["date_echeance"] < maintenant)

    print(f"    Répartition : {compteurs}")
    print(f"    Tâches en retard : {en_retard}")

    return result.inserted_ids


def generer():
    """Point d'entrée : génère toutes les données mock."""
    print("=" * 60)
    print("  GÉNÉRATION DES DONNÉES MOCK")
    print("=" * 60)

    # Initialiser la base si nécessaire
    client, db = get_database()

    # Nettoyer les données existantes
    print("\n--- Nettoyage des données existantes ---")
    for col in ["tasks", "projects", "members"]:
        count = db[col].count_documents({})
        if count > 0:
            db[col].delete_many({})
            print(f"  ✓ {count} documents supprimés de '{col}'.")

    print("\n--- Génération des membres ---")
    membre_ids = generer_membres(db)

    print("\n--- Génération des projets ---")
    projet_ids = generer_projets(db, membre_ids)

    print("\n--- Génération des tâches ---")
    generer_taches(db, projet_ids, membre_ids)

    print("\n" + "=" * 60)
    print("  DONNÉES GÉNÉRÉES AVEC SUCCÈS")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    # S'assurer que la base est initialisée
    initialiser()
    generer()
