#!/usr/bin/env python3
"""
aggregations.py - Pipelines d'agrégation MongoDB
Fournit des fonctions d'analyse avancée sur les projets, tâches et membres.
"""

from datetime import datetime
from pymongo import MongoClient

from init_db import get_database


def _proj_match(proj_ids):
    """Retourne un stage $match pour filtrer par projet_id, ou {} si aucun filtre."""
    if proj_ids is None:
        return {}
    return {"projet_id": {"$in": proj_ids}}


def _build_task_match(proj_ids=None, extra_match=None):
    """Construit le filtre de base pour les tâches, avec proj_ids et filtres supplémentaires."""
    match = {}
    if proj_ids is not None:
        match["projet_id"] = {"$in": proj_ids}
    if extra_match:
        match.update(extra_match)
    return match


def avancement_par_projet(db, proj_ids=None, extra_match=None):
    """
    Calcule le pourcentage d'avancement par projet.
    Avancement = (nb tâches done / nb tâches total) * 100
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    extra_match : filtres supplémentaires sur les tâches
    """
    pipeline = []
    base = _build_task_match(proj_ids, extra_match)
    if base:
        pipeline.append({"$match": base})
    pipeline += [
        # $group : regroupe tous les documents de la collection tasks par projet_id.
        # Pour chaque groupe, on comptabilise le total et on décompose par statut
        # en utilisant $cond (opérateur ternaire) : si statut == "done" → +1, sinon → +0.
        {"$group": {
            "_id": "$projet_id",
            "total_taches": {"$sum": 1},
            "taches_terminees": {
                "$sum": {"$cond": [{"$eq": ["$statut", "done"]}, 1, 0]}
            },
            "taches_en_cours": {
                "$sum": {"$cond": [{"$eq": ["$statut", "in_progress"]}, 1, 0]}
            },
            "taches_bloquees": {
                "$sum": {"$cond": [{"$eq": ["$statut", "blocked"]}, 1, 0]}
            },
            "taches_todo": {
                "$sum": {"$cond": [{"$eq": ["$statut", "todo"]}, 1, 0]}
            }
        }},
        # $lookup : jointure (équivalent SQL JOIN) entre tasks et projects.
        # localField "_id" (= projet_id groupé) est mis en correspondance avec
        # foreignField "_id" de la collection "projects". Résultat dans "projet".
        {"$lookup": {
            "from": "projects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        # $unwind : déroule le tableau "projet" (issu du $lookup) en un seul document.
        # Sans $unwind, "projet" serait un tableau avec un seul élément.
        {"$unwind": "$projet"},
        # $project : définit les champs à conserver/calculer dans le résultat.
        # $round arrondit le résultat de $divide * 100 à 1 décimale.
        {"$project": {
            "nom_projet": "$projet.nom",
            "statut_projet": "$projet.statut",
            "total_taches": 1,
            "taches_terminees": 1,
            "taches_en_cours": 1,
            "taches_bloquees": 1,
            "taches_todo": 1,
            "pourcentage_avancement": {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$taches_terminees", "$total_taches"]},
                        100
                    ]},
                    1
                ]
            }
        }},
        # $sort : tri décroissant par pourcentage (les projets les plus avancés en premier).
        {"$sort": {"pourcentage_avancement": -1}},
    ]

    return list(db.tasks.aggregate(pipeline))


def taches_en_retard(db, proj_ids=None, extra_match=None):
    """
    Liste toutes les tâches en retard :
    date_echeance < maintenant ET statut != done
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    extra_match : filtres supplémentaires
    """
    maintenant = datetime.now()
    match = {"statut": {"$ne": "done"}, "date_echeance": {"$lt": maintenant}}
    if proj_ids is not None:
        match["projet_id"] = {"$in": proj_ids}
    if extra_match:
        match.update(extra_match)

    pipeline = [
        # $match : filtre les documents — équivalent WHERE en SQL.
        {"$match": match},
        # $lookup : jointure avec projects pour récupérer le nom du projet.
        {"$lookup": {
            "from": "projects",
            "localField": "projet_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        # $lookup : deuxième jointure pour récupérer le nom du membre assigné.
        # MongoDB permet plusieurs $lookup dans un même pipeline.
        {"$lookup": {
            "from": "members",
            "localField": "assignee_id",
            "foreignField": "_id",
            "as": "assignee"
        }},
        {"$unwind": "$assignee"},
        # $project : calcul du retard en jours.
        # $subtract entre deux dates retourne la différence en millisecondes.
        # On divise par 86 400 000 (ms dans 1 jour) pour obtenir des jours.
        # $concat assemble prénom + " " + nom pour l'affichage.
        {"$project": {
            "titre": 1,
            "statut": 1,
            "priorite": 1,
            "date_echeance": 1,
            "nom_projet": "$projet.nom",
            "assignee_nom": {"$concat": ["$assignee.prenom", " ", "$assignee.nom"]},
            "jours_retard": {
                "$round": [
                    {"$divide": [
                        {"$subtract": [maintenant, "$date_echeance"]},
                        86400000  # millisecondes dans un jour
                    ]},
                    0
                ]
            }
        }},
        # $sort : les tâches les plus en retard en premier.
        {"$sort": {"jours_retard": -1}}
    ]

    return list(db.tasks.aggregate(pipeline))


def charge_par_membre(db, proj_ids=None, extra_match=None, role_filtre=None):
    """
    Taux de charge par membre : nombre de tâches actives (in_progress + todo + blocked).
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    extra_match : filtres supplémentaires
    role_filtre : restreindre aux membres d'un rôle donné
    """
    match = {"statut": {"$in": ["in_progress", "todo", "blocked"]}}
    if proj_ids is not None:
        match["projet_id"] = {"$in": proj_ids}
    if extra_match:
        match.update(extra_match)

    pipeline = [
        # $match : on ne prend que les tâches "actives" (non terminées).
        {"$match": match},
        # $group : regroupement par membre (assignee_id).
        # On cumule le total de tâches actives et on décompose par statut.
        {"$group": {
            "_id": "$assignee_id",
            "nb_taches_actives": {"$sum": 1},
            "nb_in_progress": {
                "$sum": {"$cond": [{"$eq": ["$statut", "in_progress"]}, 1, 0]}
            },
            "nb_todo": {
                "$sum": {"$cond": [{"$eq": ["$statut", "todo"]}, 1, 0]}
            },
            "nb_blocked": {
                "$sum": {"$cond": [{"$eq": ["$statut", "blocked"]}, 1, 0]}
            },
            # $sum sur un champ numérique : additionne les heures estimées.
            "heures_estimees_total": {"$sum": "$temps_estime_heures"}
        }},
        # $lookup : jointure avec members pour obtenir nom, prénom, rôle.
        {"$lookup": {
            "from": "members",
            "localField": "_id",
            "foreignField": "_id",
            "as": "membre"
        }},
        {"$unwind": "$membre"},
        {"$project": {
            "nom_complet": {"$concat": ["$membre.prenom", " ", "$membre.nom"]},
            "role": "$membre.role",
            "membre_id": "$membre._id",
            "nb_taches_actives": 1,
            "nb_in_progress": 1,
            "nb_todo": 1,
            "nb_blocked": 1,
            "heures_estimees_total": {"$round": ["$heures_estimees_total", 1]}
        }},
        *([{"$match": {"role": {"$in": role_filtre} if isinstance(role_filtre, list) else role_filtre}}] if role_filtre else []),
        # $sort : du plus chargé au moins chargé.
        {"$sort": {"nb_taches_actives": -1}}
    ]

    return list(db.tasks.aggregate(pipeline))


def duree_moyenne_taches_par_projet(db, proj_ids=None, extra_match=None):
    """
    Durée moyenne des tâches terminées par projet (en jours).
    Calculée sur les tâches ayant une date_fin_reelle.
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    extra_match : filtres supplémentaires
    """
    match = {"statut": "done", "date_fin_reelle": {"$ne": None}}
    if proj_ids is not None:
        match["projet_id"] = {"$in": proj_ids}
    if extra_match:
        match.update(extra_match)

    pipeline = [
        # $match : uniquement les tâches terminées avec une date de fin réelle enregistrée.
        {"$match": match},
        # $project intermédiaire : calcule la durée en jours pour chaque tâche
        # avant le $group. Cela évite de refaire le calcul dans le $group.
        {"$project": {
            "projet_id": 1,
            "duree_jours": {
                "$divide": [
                    {"$subtract": ["$date_fin_reelle", "$date_debut"]},
                    86400000
                ]
            }
        }},
        # $group : calcule moyenne, min, max de la durée par projet.
        # $avg, $min, $max sont des accumulateurs de regroupement MongoDB.
        {"$group": {
            "_id": "$projet_id",
            "duree_moyenne_jours": {"$avg": "$duree_jours"},
            "duree_min_jours": {"$min": "$duree_jours"},
            "duree_max_jours": {"$max": "$duree_jours"},
            "nb_taches_terminees": {"$sum": 1}
        }},
        # $lookup : récupération du nom du projet pour l'affichage.
        {"$lookup": {
            "from": "projects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        {"$project": {
            "nom_projet": "$projet.nom",
            "duree_moyenne_jours": {"$round": ["$duree_moyenne_jours", 1]},
            "duree_min_jours": {"$round": ["$duree_min_jours", 1]},
            "duree_max_jours": {"$round": ["$duree_max_jours", 1]},
            "nb_taches_terminees": 1
        }},
        # $sort : du projet avec les tâches les plus courtes au plus long.
        {"$sort": {"duree_moyenne_jours": 1}}
    ]

    return list(db.tasks.aggregate(pipeline))


def membres_plus_moins_charges(db, proj_ids=None):
    """
    Identifie les membres les plus et les moins chargés.
    Inclut TOUS les membres, même ceux sans tâches actives.
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    """
    proj_cond = []
    if proj_ids is not None:
        proj_cond = [{"$in": ["$projet_id", proj_ids]}]

    pipeline = [
        {"$lookup": {
            "from": "tasks",
            "let": {"member_id": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$assignee_id", "$$member_id"]},
                            {"$in": ["$statut", ["in_progress", "todo", "blocked"]]},
                            *proj_cond,
                        ]
                    }
                }}
            ],
            "as": "taches_actives"
        }},
        # $project : $size retourne le nombre d'éléments dans le tableau "taches_actives".
        # Les membres sans tâches actives auront taches_actives = [] → $size = 0.
        {"$project": {
            "nom_complet": {"$concat": ["$prenom", " ", "$nom"]},
            "role": 1,
            "nb_taches_actives": {"$size": "$taches_actives"}
        }},
        # $sort : décroissant pour avoir les plus chargés en tête du tableau.
        {"$sort": {"nb_taches_actives": -1}}
    ]

    resultats = list(db.members.aggregate(pipeline))

    if not resultats:
        return {"plus_charges": [], "moins_charges": []}

    max_charge = resultats[0]["nb_taches_actives"]
    min_charge = resultats[-1]["nb_taches_actives"]

    return {
        "plus_charges": [r for r in resultats if r["nb_taches_actives"] == max_charge],
        "moins_charges": [r for r in resultats if r["nb_taches_actives"] == min_charge],
        "classement": resultats
    }


def retard_moyen_par_projet(db, proj_ids=None, extra_match=None):
    """
    Retard moyen par projet (en jours).
    proj_ids : liste d'ObjectId à restreindre (None = tous)
    extra_match : filtres supplémentaires
    """
    maintenant = datetime.now()
    proj_filter = {"projet_id": {"$in": proj_ids}} if proj_ids is not None else {}
    if extra_match:
        proj_filter.update(extra_match)

    pipeline = [
        {"$match": {
            **proj_filter,
            "$or": [
                {"statut": "done", "date_fin_reelle": {"$ne": None},
                 "$expr": {"$gt": ["$date_fin_reelle", "$date_echeance"]}},
                {"statut": {"$ne": "done"}, "date_echeance": {"$lt": maintenant}}
            ]
        }},
        # $project avec $cond (ternaire) : selon le statut de la tâche, on calcule
        # le retard différemment :
        #   - done → date_fin_reelle - date_echeance
        #   - autres → maintenant - date_echeance
        {"$project": {
            "projet_id": 1,
            "titre": 1,
            "retard_jours": {
                "$cond": {
                    "if": {"$eq": ["$statut", "done"]},
                    "then": {
                        "$divide": [
                            {"$subtract": ["$date_fin_reelle", "$date_echeance"]},
                            86400000
                        ]
                    },
                    "else": {
                        "$divide": [
                            {"$subtract": [maintenant, "$date_echeance"]},
                            86400000
                        ]
                    }
                }
            }
        }},
        # $group : agrège les retards par projet pour obtenir moyenne et maximum.
        {"$group": {
            "_id": "$projet_id",
            "retard_moyen_jours": {"$avg": "$retard_jours"},
            "retard_max_jours": {"$max": "$retard_jours"},
            "nb_taches_en_retard": {"$sum": 1}
        }},
        # $lookup + $unwind : jointure standard pour récupérer le nom du projet.
        {"$lookup": {
            "from": "projects",
            "localField": "_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        {"$project": {
            "nom_projet": "$projet.nom",
            "retard_moyen_jours": {"$round": ["$retard_moyen_jours", 1]},
            "retard_max_jours": {"$round": ["$retard_max_jours", 1]},
            "nb_taches_en_retard": 1
        }},
        # $sort : les projets avec le plus grand retard moyen en premier.
        {"$sort": {"retard_moyen_jours": -1}}
    ]

    return list(db.tasks.aggregate(pipeline))


def afficher_resultats():
    """Exécute et affiche tous les résultats d'agrégation."""
    client, db = get_database()

    print("\n" + "=" * 70)
    print("  RÉSULTATS DES AGRÉGATIONS")
    print("=" * 70)

    # 1. Avancement par projet
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  1. AVANCEMENT PAR PROJET                                       │")
    print("└─────────────────────────────────────────────────────────────────┘")
    for r in avancement_par_projet(db):
        barre = "█" * int(r["pourcentage_avancement"] / 5) + "░" * (20 - int(r["pourcentage_avancement"] / 5))
        print(f"  {r['nom_projet']:<40} [{barre}] {r['pourcentage_avancement']}%")
        print(f"    Terminées: {r['taches_terminees']} | En cours: {r['taches_en_cours']} "
              f"| Todo: {r['taches_todo']} | Bloquées: {r['taches_bloquees']} "
              f"| Total: {r['total_taches']}")

    # 2. Tâches en retard
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  2. TÂCHES EN RETARD                                            │")
    print("└─────────────────────────────────────────────────────────────────┘")
    retards = taches_en_retard(db)
    if not retards:
        print("  Aucune tâche en retard.")
    for r in retards:
        indicateur = "🔴" if r["jours_retard"] > 20 else "🟡" if r["jours_retard"] > 7 else "🟠"
        print(f"  {indicateur} {r['titre']:<35} | Retard: {r['jours_retard']:.0f}j "
              f"| {r['statut']:<12} | {r['priorite']:<8} | {r['assignee_nom']}")
        print(f"       Projet: {r['nom_projet']}")

    # 3. Charge par membre
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  3. CHARGE PAR MEMBRE                                           │")
    print("└─────────────────────────────────────────────────────────────────┘")
    for r in charge_par_membre(db):
        print(f"  {r['nom_complet']:<25} ({r['role']:<12}) | "
              f"Tâches actives: {r['nb_taches_actives']} "
              f"(prog: {r['nb_in_progress']}, todo: {r['nb_todo']}, "
              f"blocked: {r['nb_blocked']}) | ~{r['heures_estimees_total']}h")

    # 4. Durée moyenne par projet
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  4. DURÉE MOYENNE DES TÂCHES PAR PROJET                         │")
    print("└─────────────────────────────────────────────────────────────────┘")
    for r in duree_moyenne_taches_par_projet(db):
        print(f"  {r['nom_projet']:<40} | Moy: {r['duree_moyenne_jours']}j "
              f"| Min: {r['duree_min_jours']}j | Max: {r['duree_max_jours']}j "
              f"| ({r['nb_taches_terminees']} tâches)")

    # 5. Membres les plus/moins chargés
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  5. MEMBRES LES PLUS / MOINS CHARGÉS                            │")
    print("└─────────────────────────────────────────────────────────────────┘")
    extremes = membres_plus_moins_charges(db)
    print("  Plus chargé(s):")
    for m in extremes.get("plus_charges", []):
        print(f"    ▲ {m['nom_complet']} ({m['role']}) — {m['nb_taches_actives']} tâches")
    print("  Moins chargé(s):")
    for m in extremes.get("moins_charges", []):
        print(f"    ▼ {m['nom_complet']} ({m['role']}) — {m['nb_taches_actives']} tâches")

    # 6. Retard moyen par projet
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│  6. RETARD MOYEN PAR PROJET                                      │")
    print("└─────────────────────────────────────────────────────────────────┘")
    for r in retard_moyen_par_projet(db):
        print(f"  {r['nom_projet']:<40} | Retard moy: {r['retard_moyen_jours']}j "
              f"| Max: {r['retard_max_jours']}j | {r['nb_taches_en_retard']} tâches en retard")

    print("\n" + "=" * 70)
    client.close()


if __name__ == "__main__":
    afficher_resultats()
