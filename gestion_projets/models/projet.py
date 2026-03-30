"""
models/projet.py — Accès aux données des projets (collection 'projects').
"""
from bson import ObjectId

from models.database import db


def liste(match_filter=None, sort_stage=None):
    pipeline = [
        {"$match": match_filter or {}},
        {"$lookup": {"from": "members", "localField": "chef_projet_id",
                     "foreignField": "_id", "as": "chef"}},
        {"$unwind": {"path": "$chef", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "tasks", "localField": "_id",
                     "foreignField": "projet_id", "as": "taches"}},
        {"$addFields": {
            "chef_nom": {"$concat": [
                {"$ifNull": ["$chef.prenom", ""]}, " ",
                {"$ifNull": ["$chef.nom", "N/A"]}
            ]},
            "nb_taches": {"$size": "$taches"},
            "nb_done": {"$size": {"$filter": {
                "input": "$taches",
                "cond": {"$eq": ["$$this.statut", "done"]}
            }}},
        }},
        {"$addFields": {"pct_avancement": {"$cond": [
            {"$eq": ["$nb_taches", 0]}, 0,
            {"$round": [{"$multiply": [{"$divide": ["$nb_done", "$nb_taches"]}, 100]}, 1]}
        ]}}},
        {"$project": {"taches": 0, "chef": 0}},
        {"$sort": sort_stage or {"date_debut": -1}},
    ]
    return list(db.projects.aggregate(pipeline))


def get_by_id(projet_id, extra_filter=None):
    f = {"_id": ObjectId(projet_id)}
    if extra_filter:
        f.update(extra_filter)
    return db.projects.find_one(f)


def creer(data):
    return db.projects.insert_one(data)


def modifier(projet_id, data):
    return db.projects.update_one({"_id": ObjectId(projet_id)}, {"$set": data})


def supprimer(projet_id):
    oid = ObjectId(projet_id)
    db.tasks.delete_many({"projet_id": oid})
    db.projects.delete_one({"_id": oid})


def tous(match_filter=None, projection=None):
    return list(db.projects.find(match_filter or {}, projection or {}).sort("nom", 1))


def ids_accessibles(match_filter):
    return db.projects.distinct("_id", match_filter)
