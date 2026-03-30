"""
controllers/recherche.py — Blueprint recherche globale avec matching flou.
"""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from rapidfuzz import fuzz

from controllers.utils import get_projet_filter, get_tache_filter
from models.database import db

bp = Blueprint("recherche", __name__)

FUZZY_SEUIL = 70


def _fuzzy_score(q, *champs):
    q_lower = q.lower()
    return max(fuzz.WRatio(q_lower, (c or "").lower()) for c in champs)


@bp.route("/recherche")
@login_required
def index():
    q = request.args.get("q", "").strip()
    if not q:
        return render_template("recherche.html", q=q, projets=[], membres=[], taches=[])

    proj_filter = get_projet_filter()
    tous_projets = list(db.projects.find(proj_filter,
                                         {"nom": 1, "statut": 1, "date_debut": 1, "description": 1}))
    projets = sorted(
        [p for p in tous_projets
         if _fuzzy_score(q, p.get("nom", ""), p.get("description", "")) >= FUZZY_SEUIL],
        key=lambda p: _fuzzy_score(q, p.get("nom", ""), p.get("description", "")),
        reverse=True
    )[:10]

    if not current_user.is_membre:
        tous_membres = list(db.members.find({}, {"nom": 1, "prenom": 1, "email": 1, "role": 1}))
        membres = sorted(
            [m for m in tous_membres
             if _fuzzy_score(q, m.get("nom", ""), m.get("prenom", ""),
                             f"{m.get('prenom','')} {m.get('nom','')}", m.get("email", "")) >= FUZZY_SEUIL],
            key=lambda m: _fuzzy_score(q, m.get("nom", ""), m.get("prenom", ""),
                                       f"{m.get('prenom','')} {m.get('nom','')}"),
            reverse=True
        )[:10]
    else:
        membres = []

    tache_base_filter = get_tache_filter()
    tous_taches = list(db.tasks.aggregate([
        {"$match": tache_base_filter},
        {"$lookup": {"from": "projects", "localField": "projet_id",
                     "foreignField": "_id", "as": "projet"}},
        {"$unwind": {"path": "$projet", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {"nom_projet": "$projet.nom"}},
        {"$project": {"titre": 1, "statut": 1, "priorite": 1, "nom_projet": 1, "projet_id": 1}},
    ]))
    taches = sorted(
        [t for t in tous_taches
         if _fuzzy_score(q, t.get("titre", ""), t.get("nom_projet", "")) >= FUZZY_SEUIL],
        key=lambda t: _fuzzy_score(q, t.get("titre", ""), t.get("nom_projet", "")),
        reverse=True
    )[:10]

    return render_template("recherche.html", q=q, projets=projets, membres=membres, taches=taches)
