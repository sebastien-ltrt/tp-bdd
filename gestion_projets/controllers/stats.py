"""
controllers/stats.py — Blueprint statistiques avec filtres dynamiques.
"""
from datetime import datetime

from bson import ObjectId
from flask import Blueprint, render_template, request
from flask_login import login_required

from controllers.utils import require_role, get_accessible_projet_ids
from models.database import db
from aggregations import (avancement_par_projet, taches_en_retard, charge_par_membre,
                           duree_moyenne_taches_par_projet, membres_plus_moins_charges,
                           retard_moyen_par_projet)

bp = Blueprint("stats", __name__)

ROLES = ["developpeur", "designer", "chef_projet", "testeur", "devops", "analyste"]


@bp.route("/stats")
@login_required
@require_role("admin", "chef_projet")
def statistiques():
    accessible_ids = get_accessible_projet_ids()
    tous_projets = list(db.projects.find(
        {} if accessible_ids is None else {"_id": {"$in": accessible_ids}},
        {"nom": 1, "statut": 1}
    ).sort("nom", 1))

    projets_sel     = request.args.getlist("projets_sel")
    date_debut_str  = request.args.get("date_debut", "")
    date_fin_str    = request.args.get("date_fin", "")
    role_filtre     = request.args.getlist("role_filtre")

    if projets_sel:
        proj_ids = [ObjectId(pid) for pid in projets_sel
                    if accessible_ids is None or ObjectId(pid) in (accessible_ids or [])]
    else:
        proj_ids = accessible_ids

    extra_match = {}
    if date_debut_str:
        try:
            extra_match.setdefault("date_echeance", {})["$gte"] = datetime.strptime(date_debut_str, "%Y-%m-%d")
        except ValueError:
            pass
    if date_fin_str:
        try:
            extra_match.setdefault("date_echeance", {})["$lte"] = datetime.strptime(date_fin_str, "%Y-%m-%d")
        except ValueError:
            pass

    em = extra_match or None
    noms_projets_sel = [p["nom"] for p in tous_projets if str(p["_id"]) in projets_sel]

    return render_template("stats.html",
                           avancements=avancement_par_projet(db, proj_ids, em),
                           retards=taches_en_retard(db, proj_ids, em),
                           charges=charge_par_membre(db, proj_ids, em, role_filtre or None),
                           durees=duree_moyenne_taches_par_projet(db, proj_ids, em),
                           extremes=membres_plus_moins_charges(db, proj_ids),
                           retard_projets=retard_moyen_par_projet(db, proj_ids, em),
                           tous_projets=tous_projets,
                           roles=ROLES,
                           projets_sel=projets_sel,
                           date_debut=date_debut_str,
                           date_fin=date_fin_str,
                           role_filtre=role_filtre,
                           noms_projets_sel=noms_projets_sel)
