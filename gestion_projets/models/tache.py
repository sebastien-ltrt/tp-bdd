"""
models/tache.py — Accès aux données des tâches (collection 'tasks').
"""
from datetime import datetime

from bson import ObjectId

from models.database import db

_PRIORITE_NUM = {"$switch": {
    "branches": [
        {"case": {"$eq": ["$priorite", "low"]},      "then": 1},
        {"case": {"$eq": ["$priorite", "medium"]},   "then": 2},
        {"case": {"$eq": ["$priorite", "high"]},     "then": 3},
        {"case": {"$eq": ["$priorite", "critical"]}, "then": 4},
    ],
    "default": 0,
}}


def liste(match_filter=None, sort_stage=None):
    now = datetime.now()
    pipeline = [
        {"$match": match_filter or {}},
        {"$lookup": {"from": "projects", "localField": "projet_id",
                     "foreignField": "_id", "as": "projet"}},
        {"$unwind": "$projet"},
        {"$lookup": {"from": "members", "localField": "assignee_id",
                     "foreignField": "_id", "as": "assignee"}},
        {"$unwind": "$assignee"},
        {"$addFields": {
            "nom_projet":    "$projet.nom",
            "assignee_nom":  {"$concat": ["$assignee.prenom", " ", "$assignee.nom"]},
            "est_en_retard": {"$and": [
                {"$ne": ["$statut", "done"]},
                {"$lt": ["$date_echeance", now]},
            ]},
            "priorite_num": _PRIORITE_NUM,
        }},
        {"$sort": sort_stage or {"est_en_retard": -1, "date_echeance": 1}},
    ]
    return list(db.tasks.aggregate(pipeline))


def get_by_id(tache_id):
    return db.tasks.find_one({"_id": ObjectId(tache_id)})


def get_with_relations(tache_id):
    """Retourne la tâche avec son projet et son assigné."""
    tache = get_by_id(tache_id)
    if not tache:
        return None, None, None
    from models.projet import get_by_id as get_projet
    from models.membre import get_by_id as get_membre
    projet  = get_projet(str(tache["projet_id"]))  if tache.get("projet_id")   else None
    assignee = get_membre(str(tache["assignee_id"])) if tache.get("assignee_id") else None
    return tache, projet, assignee


def creer(data):
    return db.tasks.insert_one(data)


def modifier(tache_id, data):
    return db.tasks.update_one({"_id": ObjectId(tache_id)}, {"$set": data})


def changer_statut(tache_id, nouveau_statut, temps_reel=None):
    modifications = {"statut": nouveau_statut}
    if nouveau_statut == "done":
        modifications["date_fin_reelle"] = datetime.now()
        if temps_reel:
            modifications["temps_reel_heures"] = float(temps_reel)
    else:
        modifications["date_fin_reelle"] = None
    db.tasks.update_one({"_id": ObjectId(tache_id)}, {"$set": modifications})


def supprimer(tache_id):
    db.tasks.delete_one({"_id": ObjectId(tache_id)})


def count(match_filter=None):
    return db.tasks.count_documents(match_filter or {})


def ids_projets_de_membre(membre_oid):
    return db.tasks.distinct("projet_id", {"assignee_id": membre_oid})
