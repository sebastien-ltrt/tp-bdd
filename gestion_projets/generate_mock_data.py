#!/usr/bin/env python3
"""
generate_mock_data.py - Génère des données de test réalistes
  - 100 membres d'équipe
  - 10 projets
  - ~150 tâches distribuées
  - 1 compte utilisateur par membre (liés via member_id)
"""

import random
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from faker import Faker
from werkzeug.security import generate_password_hash

from init_db import get_database

fake = Faker("fr_FR")
random.seed(42)
fake.seed_instance(42)

# ──────────────────────────────────────────────
#  Constantes
# ──────────────────────────────────────────────

COMPETENCES_PAR_ROLE = {
    "developpeur":  ["Python", "JavaScript", "React", "Node.js", "SQL", "Git", "Docker", "TypeScript", "Java", "FastAPI"],
    "designer":     ["Figma", "Adobe XD", "CSS", "HTML", "UX Research", "Sketch", "Illustrator", "Photoshop", "Prototypage"],
    "chef_projet":  ["Scrum", "Kanban", "JIRA", "Gestion d'équipe", "Budget", "Planification", "Confluence", "Reporting"],
    "testeur":      ["Selenium", "Pytest", "JMeter", "Postman", "TDD", "BDD", "Cypress", "Jest", "SonarQube"],
    "devops":       ["Docker", "Kubernetes", "CI/CD", "AWS", "Terraform", "Linux", "Ansible", "GitLab CI", "Prometheus"],
    "analyste":     ["SQL", "Power BI", "Excel", "Python", "Pandas", "Tableau", "Analyse de données", "Reporting"],
}

NOMS_PROJETS = [
    "Refonte du site e-commerce",
    "Développement de l'application mobile",
    "Migration vers le cloud AWS",
    "Système de gestion des stocks",
    "Plateforme de formation en ligne",
    "Tableau de bord analytique",
    "API de paiement sécurisé",
    "Portail client self-service",
    "Infrastructure DevSecOps",
    "Système de recommandation IA",
]

DESC_PROJETS = [
    "Modernisation complète de la boutique en ligne avec nouveau design et tunnel d'achat optimisé.",
    "Application iOS et Android pour accès aux services clients depuis mobile.",
    "Migration de l'infrastructure on-premise vers AWS avec haute disponibilité.",
    "Outil de gestion temps réel des stocks, alertes et réapprovisionnement automatique.",
    "LMS complet avec cours vidéo, quiz, certification et suivi des apprenants.",
    "Dashboard BI pour visualiser les KPIs métier et décisions data-driven.",
    "Intégration Stripe, PayPal et virement bancaire avec conformité PCI-DSS.",
    "Espace client en ligne pour gérer contrats, factures et support.",
    "Pipeline CI/CD sécurisé, scanning de vulnérabilités et monitoring.",
    "Moteur de recommandation basé sur le comportement utilisateur et ML.",
]

STATUTS_PROJET  = ["planifie", "en_cours", "termine", "annule", "en_pause"]
STATUTS_PROJ_W  = [0.10, 0.55, 0.20, 0.05, 0.10]

STATUTS_TACHE   = ["todo", "in_progress", "done", "blocked"]
STATUTS_TACHE_W = [0.25, 0.30, 0.35, 0.10]

PRIORITES   = ["low", "medium", "high", "critical"]
PRIORITES_W = [0.15, 0.40, 0.35, 0.10]

TITRES_TACHES = [
    "Analyse des besoins", "Rédaction du cahier des charges", "Setup environnement de dev",
    "Conception de la base de données", "Développement API REST", "Intégration frontend",
    "Tests unitaires", "Tests d'intégration", "Review de code", "Déploiement en staging",
    "Recette utilisateur", "Correction de bugs", "Optimisation des performances",
    "Rédaction de la documentation", "Mise en production", "Formation des utilisateurs",
    "Audit de sécurité", "Refactoring du code", "Mise à jour des dépendances",
    "Monitoring et alertes", "Backup et reprise sur incident", "Design des maquettes",
    "Prototype interactif", "Revue des spécifications", "Réunion de sprint",
    "Démonstration client", "Rapport d'avancement", "Plan de test", "Analyse des logs",
    "Configuration du pipeline CI/CD", "Création des fixtures de test", "Validation RGPD",
]

# Répartition des 100 membres par rôle
DIST_ROLES = {
    "developpeur":  40,
    "testeur":      15,
    "designer":     12,
    "devops":       10,
    "analyste":     8,
    "chef_projet":  15,
}

DEFAULT_PASSWORD = "password123"


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def rand_date(start: datetime, end: datetime) -> datetime:
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def pick_competences(role: str) -> list:
    pool = COMPETENCES_PAR_ROLE[role]
    return random.sample(pool, random.randint(3, min(6, len(pool))))


# ──────────────────────────────────────────────
#  Génération membres
# ──────────────────────────────────────────────

def generer_membres() -> list:
    roles_liste = []
    for role, count in DIST_ROLES.items():
        roles_liste.extend([role] * count)
    random.shuffle(roles_liste)

    membres = []
    emails_vus = set()

    for role in roles_liste:
        prenom = fake.first_name()
        nom = fake.last_name()

        prenom_ascii = unicodedata.normalize("NFKD", prenom).encode("ascii", "ignore").decode()
        nom_ascii = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
        base = f"{prenom_ascii.lower()}.{nom_ascii.lower()}"
        base = "".join(c for c in base if c.isalnum() or c == ".")
        email = f"{base}@entreprise.fr"
        i = 1
        while email in emails_vus:
            email = f"{base}{i}@entreprise.fr"
            i += 1
        emails_vus.add(email)

        membres.append({
            "nom": nom,
            "prenom": prenom,
            "email": email,
            "role": role,
            "competences": pick_competences(role),
            "date_embauche": rand_date(datetime(2018, 1, 1), datetime(2024, 6, 1)),
        })
    return membres


# ──────────────────────────────────────────────
#  Génération projets
# ──────────────────────────────────────────────

def generer_projets(chef_ids: list) -> list:
    projets = []
    statuts = random.choices(STATUTS_PROJET, weights=STATUTS_PROJ_W, k=len(NOMS_PROJETS))

    for i, nom in enumerate(NOMS_PROJETS):
        debut = rand_date(datetime(2023, 1, 1), datetime(2025, 1, 1))
        fin_prevue = debut + timedelta(days=random.randint(90, 365))
        statut = statuts[i]

        fin_reelle = None
        if statut == "termine":
            fin_reelle = fin_prevue + timedelta(days=random.randint(-10, 30))

        projets.append({
            "nom": nom,
            "description": DESC_PROJETS[i],
            "date_debut": debut,
            "date_fin_prevue": fin_prevue,
            "date_fin_reelle": fin_reelle,
            "statut": statut,
            "budget": round(random.uniform(15_000, 200_000), 2),
            "chef_projet_id": random.choice(chef_ids),
        })
    return projets


# ──────────────────────────────────────────────
#  Génération tâches
# ──────────────────────────────────────────────

def generer_taches(projets_docs: list, membre_ids: list) -> list:
    taches = []
    now = datetime.now()

    for projet in projets_docs:
        debut_proj = projet["date_debut"]
        fin_proj = projet["date_fin_prevue"]
        nb = random.randint(12, 20)
        titres_utilises = set()

        for _ in range(nb):
            titre = random.choice(TITRES_TACHES)
            if titre in titres_utilises:
                titre = f"{titre} #{random.randint(2, 9)}"
            titres_utilises.add(titre)

            t_debut = rand_date(debut_proj, fin_proj - timedelta(days=7))
            t_echeance = t_debut + timedelta(days=random.randint(3, 45))

            # 30 % des tâches ont une échéance déjà passée
            if random.random() < 0.30:
                t_echeance = rand_date(datetime(2024, 6, 1), now - timedelta(days=1))

            statut = random.choices(STATUTS_TACHE, weights=STATUTS_TACHE_W)[0]
            priorite = random.choices(PRIORITES, weights=PRIORITES_W)[0]
            temps_estime = round(random.uniform(2.0, 40.0), 1)

            temps_reel = None
            date_fin_reelle = None
            if statut == "done":
                temps_reel = round(temps_estime * random.uniform(0.7, 1.4), 1)
                date_fin_reelle = t_echeance + timedelta(days=random.randint(-5, 10))

            taches.append({
                "titre": titre,
                "description": f"Tâche '{titre}' — projet '{projet['nom']}'.",
                "projet_id": projet["_id"],
                "assignee_id": random.choice(membre_ids),
                "statut": statut,
                "priorite": priorite,
                "date_debut": t_debut,
                "date_echeance": t_echeance,
                "date_fin_reelle": date_fin_reelle,
                "temps_estime_heures": temps_estime,
                "temps_reel_heures": temps_reel,
            })
    return taches


# ──────────────────────────────────────────────
#  Génération comptes utilisateurs (un par membre)
# ──────────────────────────────────────────────

def generer_users(membres_docs: list) -> list:
    users = []
    default_hash = generate_password_hash(DEFAULT_PASSWORD)
    for membre in membres_docs:
        app_role = "chef_projet" if membre["role"] == "chef_projet" else "membre"
        username = membre["email"].split("@")[0]
        users.append({
            "username": username,
            "password_hash": default_hash,
            "email": membre["email"],
            "app_role": app_role,
            "member_id": membre["_id"],
            "is_active": True,
            "created_at": membre["date_embauche"],
        })
    return users


# ──────────────────────────────────────────────
#  Point d'entrée
# ──────────────────────────────────────────────

def generer():
    client, db = get_database()

    print("=" * 60)
    print("  GÉNÉRATION DES DONNÉES DE TEST")
    print("=" * 60)

    # Nettoyage (on garde les admins si existants)
    print("\n--- Nettoyage des collections ---")
    db.members.delete_many({})
    db.projects.delete_many({})
    db.tasks.delete_many({})
    db.users.delete_many({"app_role": {"$ne": "admin"}})
    print("  ✓ Collections nettoyées (admins conservés).")

    # ── Membres ───────────────────────────────
    print("\n--- Membres ---")
    membres = generer_membres()
    res = db.members.insert_many(membres)
    membre_ids = res.inserted_ids
    print(f"  ✓ {len(membre_ids)} membres insérés.")
    for role, count in sorted(Counter(m["role"] for m in membres).items()):
        print(f"    · {role}: {count}")

    membres_docs = list(db.members.find())
    chef_ids = [m["_id"] for m in membres_docs if m["role"] == "chef_projet"]

    # ── Projets ───────────────────────────────
    print("\n--- Projets ---")
    projets = generer_projets(chef_ids)
    db.projects.insert_many(projets)
    print(f"  ✓ {len(projets)} projets insérés.")
    for statut, count in sorted(Counter(p["statut"] for p in projets).items()):
        print(f"    · {statut}: {count}")

    projets_docs = list(db.projects.find())

    # ── Tâches ────────────────────────────────
    print("\n--- Tâches ---")
    taches = generer_taches(projets_docs, membre_ids)
    db.tasks.insert_many(taches)
    print(f"  ✓ {len(taches)} tâches insérées.")
    for statut, count in sorted(Counter(t["statut"] for t in taches).items()):
        print(f"    · {statut}: {count}")
    retard = sum(
        1 for t in taches
        if t["statut"] != "done" and t["date_echeance"] < datetime.now()
    )
    print(f"    → {retard} tâches en retard")

    # ── Utilisateurs ──────────────────────────
    print("\n--- Comptes utilisateurs ---")
    users = generer_users(membres_docs)
    db.users.insert_many(users)
    chefs = sum(1 for u in users if u["app_role"] == "chef_projet")
    print(f"  ✓ {len(users)} comptes créés ({chefs} chefs de projet, {len(users)-chefs} membres).")
    print(f"  Mot de passe par défaut : '{DEFAULT_PASSWORD}'")
    print("  Compte admin : utilisez create_admin.py")

    print("\n" + "=" * 60)
    print("  GÉNÉRATION TERMINÉE")
    print("=" * 60)
    client.close()


if __name__ == "__main__":
    generer()
