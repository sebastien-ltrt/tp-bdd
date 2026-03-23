#!/usr/bin/env python3
"""
views.py - Création des vues MongoDB
Les vues sont des pipelines d'agrégation persistants qui agissent comme des
collections virtuelles en lecture seule. Elles sont recalculées à chaque lecture.
"""

from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from init_db import get_database


def supprimer_vue_si_existe(db, nom_vue):
    """Supprime une vue existante pour la recréer."""
    try:
        db.drop_collection(nom_vue)
    except OperationFailure:
        pass


def creer_vue_taches_en_retard(db):
    """
    Vue 'vue_taches_en_retard' :
    Liste les tâches dont la date d'échéance est passée et qui ne sont pas terminées.
    Inclut les informations du projet et du membre assigné.

    Note: On utilise $$NOW pour avoir la date courante à chaque lecture de la vue.
    """
    supprimer_vue_si_existe(db, "vue_taches_en_retard")

    pipeline = [
        # Tâches non terminées avec échéance passée
        {"$match": {
            "statut": {"$ne": "done"},
            "$expr": {"$lt": ["$date_echeance", "$$NOW"]}
        }},
        # Jointure projet
        {"$lookup": {
            "from": "projects",
            "localField": "projet_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        # Jointure membre
        {"$lookup": {
            "from": "members",
            "localField": "assignee_id",
            "foreignField": "_id",
            "as": "assignee"
        }},
        {"$unwind": "$assignee"},
        # Projection finale
        {"$project": {
            "titre": 1,
            "statut": 1,
            "priorite": 1,
            "date_echeance": 1,
            "date_debut": 1,
            "temps_estime_heures": 1,
            "nom_projet": "$projet.nom",
            "assignee_nom": {"$concat": ["$assignee.prenom", " ", "$assignee.nom"]},
            "assignee_email": "$assignee.email",
            "jours_retard": {
                "$round": [
                    {"$divide": [
                        {"$subtract": ["$$NOW", "$date_echeance"]},
                        86400000
                    ]},
                    0
                ]
            }
        }},
        {"$sort": {"jours_retard": -1}}
    ]

    db.create_collection("vue_taches_en_retard", viewOn="tasks", pipeline=pipeline)
    print("  ✓ Vue 'vue_taches_en_retard' créée.")


def creer_vue_avancement_projets(db):
    """
    Vue 'vue_avancement_projets' :
    Synthèse de l'avancement de chaque projet avec pourcentage et répartition.
    """
    supprimer_vue_si_existe(db, "vue_avancement_projets")

    pipeline = [
        {"$group": {
            "_id": "$projet_id",
            "total_taches": {"$sum": 1},
            "taches_done": {"$sum": {"$cond": [{"$eq": ["$statut", "done"]}, 1, 0]}},
            "taches_in_progress": {"$sum": {"$cond": [{"$eq": ["$statut", "in_progress"]}, 1, 0]}},
            "taches_todo": {"$sum": {"$cond": [{"$eq": ["$statut", "todo"]}, 1, 0]}},
            "taches_blocked": {"$sum": {"$cond": [{"$eq": ["$statut", "blocked"]}, 1, 0]}},
            "heures_estimees": {"$sum": "$temps_estime_heures"},
            "heures_reelles": {
                "$sum": {"$ifNull": ["$temps_reel_heures", 0]}
            }
        }},
        {"$lookup": {
            "from": "projects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        # Jointure chef de projet
        {"$lookup": {
            "from": "members",
            "localField": "projet.chef_projet_id",
            "foreignField": "_id",
            "as": "chef"
        }},
        {"$unwind": {"path": "$chef", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "nom_projet": "$projet.nom",
            "statut_projet": "$projet.statut",
            "budget": "$projet.budget",
            "date_debut": "$projet.date_debut",
            "date_fin_prevue": "$projet.date_fin_prevue",
            "chef_projet": {"$concat": [
                {"$ifNull": ["$chef.prenom", ""]},
                " ",
                {"$ifNull": ["$chef.nom", "N/A"]}
            ]},
            "total_taches": 1,
            "taches_done": 1,
            "taches_in_progress": 1,
            "taches_todo": 1,
            "taches_blocked": 1,
            "pourcentage_avancement": {
                "$round": [
                    {"$multiply": [
                        {"$cond": [
                            {"$eq": ["$total_taches", 0]},
                            0,
                            {"$divide": ["$taches_done", "$total_taches"]}
                        ]},
                        100
                    ]},
                    1
                ]
            },
            "heures_estimees": {"$round": ["$heures_estimees", 1]},
            "heures_reelles": {"$round": ["$heures_reelles", 1]}
        }},
        {"$sort": {"pourcentage_avancement": -1}}
    ]

    db.create_collection("vue_avancement_projets", viewOn="tasks", pipeline=pipeline)
    print("  ✓ Vue 'vue_avancement_projets' créée.")


def creer_vue_charge_membres(db):
    """
    Vue 'vue_charge_membres' :
    Charge de travail de chaque membre avec détail par statut.
    Part de la collection members pour inclure ceux sans tâches.
    """
    supprimer_vue_si_existe(db, "vue_charge_membres")

    pipeline = [
        # Jointure avec toutes les tâches actives du membre
        {"$lookup": {
            "from": "tasks",
            "let": {"member_id": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$assignee_id", "$$member_id"]},
                            {"$in": ["$statut", ["in_progress", "todo", "blocked"]]}
                        ]
                    }
                }}
            ],
            "as": "taches_actives"
        }},
        # Jointure avec les tâches en retard du membre
        {"$lookup": {
            "from": "tasks",
            "let": {"member_id": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$assignee_id", "$$member_id"]},
                            {"$ne": ["$statut", "done"]},
                            {"$lt": ["$date_echeance", "$$NOW"]}
                        ]
                    }
                }}
            ],
            "as": "taches_en_retard"
        }},
        {"$project": {
            "nom_complet": {"$concat": ["$prenom", " ", "$nom"]},
            "email": 1,
            "role": 1,
            "nb_taches_actives": {"$size": "$taches_actives"},
            "nb_taches_en_retard": {"$size": "$taches_en_retard"},
            "heures_estimees_restantes": {
                "$round": [{"$sum": "$taches_actives.temps_estime_heures"}, 1]
            }
        }},
        {"$sort": {"nb_taches_actives": -1}}
    ]

    db.create_collection("vue_charge_membres", viewOn="members", pipeline=pipeline)
    print("  ✓ Vue 'vue_charge_membres' créée.")


def creer_vue_dashboard(db):
    """
    Vue 'vue_dashboard' :
    Synthèse globale — un seul document avec les KPI principaux.
    """
    supprimer_vue_si_existe(db, "vue_dashboard")

    pipeline = [
        # Calculs globaux sur toutes les tâches
        {"$facet": {
            "stats_globales": [
                {"$group": {
                    "_id": None,
                    "total_taches": {"$sum": 1},
                    "taches_done": {"$sum": {"$cond": [{"$eq": ["$statut", "done"]}, 1, 0]}},
                    "taches_in_progress": {"$sum": {"$cond": [{"$eq": ["$statut", "in_progress"]}, 1, 0]}},
                    "taches_todo": {"$sum": {"$cond": [{"$eq": ["$statut", "todo"]}, 1, 0]}},
                    "taches_blocked": {"$sum": {"$cond": [{"$eq": ["$statut", "blocked"]}, 1, 0]}},
                    "heures_estimees_total": {"$sum": "$temps_estime_heures"},
                    "heures_reelles_total": {"$sum": {"$ifNull": ["$temps_reel_heures", 0]}}
                }}
            ],
            "taches_en_retard": [
                {"$match": {
                    "statut": {"$ne": "done"},
                    "$expr": {"$lt": ["$date_echeance", "$$NOW"]}
                }},
                {"$count": "total"}
            ],
            "par_priorite": [
                {"$group": {
                    "_id": "$priorite",
                    "count": {"$sum": 1}
                }}
            ],
            "par_projet": [
                {"$group": {
                    "_id": "$projet_id",
                    "nb_taches": {"$sum": 1},
                    "nb_done": {"$sum": {"$cond": [{"$eq": ["$statut", "done"]}, 1, 0]}}
                }},
                {"$lookup": {
                    "from": "projects",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "projet"
                }},
                {"$unwind": "$projet"},
                {"$project": {
                    "nom": "$projet.nom",
                    "nb_taches": 1,
                    "nb_done": 1,
                    "avancement": {
                        "$round": [{"$multiply": [{"$divide": ["$nb_done", "$nb_taches"]}, 100]}, 1]
                    }
                }}
            ]
        }},
        # Reformatage en un seul document propre
        {"$project": {
            "total_taches": {"$arrayElemAt": ["$stats_globales.total_taches", 0]},
            "taches_done": {"$arrayElemAt": ["$stats_globales.taches_done", 0]},
            "taches_in_progress": {"$arrayElemAt": ["$stats_globales.taches_in_progress", 0]},
            "taches_todo": {"$arrayElemAt": ["$stats_globales.taches_todo", 0]},
            "taches_blocked": {"$arrayElemAt": ["$stats_globales.taches_blocked", 0]},
            "heures_estimees_total": {"$round": [
                {"$arrayElemAt": ["$stats_globales.heures_estimees_total", 0]}, 1
            ]},
            "heures_reelles_total": {"$round": [
                {"$arrayElemAt": ["$stats_globales.heures_reelles_total", 0]}, 1
            ]},
            "nb_taches_en_retard": {
                "$ifNull": [{"$arrayElemAt": ["$taches_en_retard.total", 0]}, 0]
            },
            "repartition_priorite": "$par_priorite",
            "avancement_projets": "$par_projet",
            "pourcentage_global": {
                "$round": [
                    {"$multiply": [
                        {"$cond": [
                            {"$eq": [{"$arrayElemAt": ["$stats_globales.total_taches", 0]}, 0]},
                            0,
                            {"$divide": [
                                {"$arrayElemAt": ["$stats_globales.taches_done", 0]},
                                {"$arrayElemAt": ["$stats_globales.total_taches", 0]}
                            ]}
                        ]},
                        100
                    ]},
                    1
                ]
            }
        }}
    ]

    db.create_collection("vue_dashboard", viewOn="tasks", pipeline=pipeline)
    print("  ✓ Vue 'vue_dashboard' créée.")


def creer_toutes_les_vues():
    """Crée toutes les vues MongoDB."""
    print("=" * 60)
    print("  CRÉATION DES VUES MONGODB")
    print("=" * 60)

    client, db = get_database()

    print("\n--- Création des vues ---")
    creer_vue_taches_en_retard(db)
    creer_vue_avancement_projets(db)
    creer_vue_charge_membres(db)
    creer_vue_dashboard(db)

    # Vérification
    print("\n--- Vérification ---")
    for vue in ["vue_taches_en_retard", "vue_avancement_projets",
                "vue_charge_membres", "vue_dashboard"]:
        count = db[vue].count_documents({})
        print(f"  '{vue}' : {count} document(s)")

    print("\n" + "=" * 60)
    print("  VUES CRÉÉES AVEC SUCCÈS")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    creer_toutes_les_vues()
