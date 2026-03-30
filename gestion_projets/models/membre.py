"""
models/membre.py — Accès aux données des membres (collection 'members').
"""
from datetime import datetime

from bson import ObjectId
from pymongo.errors import PyMongoError

from models.database import db


def liste(match_filter=None, sort_stage=None):
    now = datetime.now()
    pipeline = [
        {"$match": match_filter or {}},
        {"$lookup": {
            "from": "tasks",
            "let": {"mid": "$_id"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$assignee_id", "$$mid"]},
                {"$in": ["$statut", ["in_progress", "todo", "blocked"]]},
            ]}}}],
            "as": "taches_actives",
        }},
        {"$lookup": {
            "from": "tasks",
            "let": {"mid": "$_id"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$assignee_id", "$$mid"]},
                {"$ne": ["$statut", "done"]},
                {"$lt": ["$date_echeance", now]},
            ]}}}],
            "as": "taches_retard",
        }},
        {"$addFields": {
            "nb_actives": {"$size": "$taches_actives"},
            "nb_retard":  {"$size": "$taches_retard"},
        }},
        {"$project": {"taches_actives": 0, "taches_retard": 0}},
        {"$sort": sort_stage or {"nom": 1}},
    ]
    return list(db.members.aggregate(pipeline))


def get_by_id(membre_id):
    return db.members.find_one({"_id": ObjectId(membre_id)})


def taches_du_membre(membre_id, sort_stage=None):
    now = datetime.now()
    pipeline = [
        {"$match": {"assignee_id": ObjectId(membre_id)}},
        {"$lookup": {"from": "projects", "localField": "projet_id",
                     "foreignField": "_id", "as": "projet"}},
        {"$unwind": {"path": "$projet", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {
            "nom_projet":  "$projet.nom",
            "projet_oid":  "$projet._id",
            "est_en_retard": {"$and": [
                {"$ne": ["$statut", "done"]},
                {"$lt": ["$date_echeance", now]},
            ]},
            "priorite_num": {"$switch": {
                "branches": [
                    {"case": {"$eq": ["$priorite", "low"]},      "then": 1},
                    {"case": {"$eq": ["$priorite", "medium"]},   "then": 2},
                    {"case": {"$eq": ["$priorite", "high"]},     "then": 3},
                    {"case": {"$eq": ["$priorite", "critical"]}, "then": 4},
                ],
                "default": 0,
            }},
        }},
        {"$sort": sort_stage or {"date_echeance": 1}},
    ]
    return list(db.tasks.aggregate(pipeline))


def creer(data):
    return db.members.insert_one(data)


def modifier(membre_id, data):
    return db.members.update_one({"_id": ObjectId(membre_id)}, {"$set": data})


def supprimer(membre_id):
    oid = ObjectId(membre_id)
    nb_taches   = db.tasks.count_documents({"assignee_id": oid})
    nb_projets  = db.projects.count_documents({"chef_projet_id": oid})
    if nb_taches > 0 or nb_projets > 0:
        raise ValueError(
            f"Ce membre a {nb_taches} tâche(s) et gère {nb_projets} projet(s). Réassignez-les d'abord."
        )
    db.members.delete_one({"_id": oid})


def tous(projection=None):
    return list(db.members.find({}, projection or {}).sort("nom", 1))
