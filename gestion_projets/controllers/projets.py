"""
controllers/projets.py — Blueprint CRUD projets.
"""
from datetime import datetime

from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from pymongo.errors import PyMongoError

from controllers.utils import require_role, get_projet_filter
import models.projet as ProjetModel
import models.membre as MembreModel
import models.tache as TacheModel

bp = Blueprint("projets", __name__, url_prefix="/projets")

STATUTS = ["planifie", "en_cours", "termine", "annule", "en_pause"]

_SORT_MAP = {
    "nom":        lambda o: {"nom": o},
    "date_debut": lambda o: {"date_debut": o},
    "budget":     lambda o: {"budget": o},
    "avancement": lambda o: {"pct_avancement": o},
    "statut":     lambda o: {"statut": o},
    "nb_taches":  lambda o: {"nb_taches": o},
}


@bp.route("/")
@login_required
def liste():
    proj_filter = get_projet_filter()
    filtre_statut = request.args.get("statut")
    q     = request.args.get("q", "").strip()
    tri   = request.args.get("tri", "date_debut")
    ordre = request.args.get("ordre", "desc")
    ordre_val = -1 if ordre == "desc" else 1

    if filtre_statut:
        proj_filter["statut"] = filtre_statut

    if q:
        proj_filter["$or"] = [
            {"nom": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]

    sort_stage = _SORT_MAP.get(tri, _SORT_MAP["date_debut"])(ordre_val)
    projets = ProjetModel.liste(proj_filter, sort_stage)

    return render_template("projets/liste.html", projets=projets,
                           filtre_statut=filtre_statut, q=q, tri=tri, ordre=ordre,
                           statuts_projet=STATUTS)


@bp.route("/<id>")
@login_required
def detail(id):
    proj_filter = {**get_projet_filter(), "_id": ObjectId(id)}
    projet = ProjetModel.get_by_id(id, get_projet_filter())
    if not projet:
        flash("Projet introuvable ou accès refusé.", "danger")
        return redirect(url_for("projets.liste"))

    from models.database import db
    chef = db.members.find_one({"_id": projet["chef_projet_id"]})

    tache_match = {"projet_id": ObjectId(id)}
    if current_user.is_membre and current_user.member_oid:
        tache_match["assignee_id"] = current_user.member_oid

    taches = TacheModel.liste(tache_match,
                               {"priorite": -1, "date_echeance": 1})

    now   = datetime.now()
    total = len(taches)
    done  = sum(1 for t in taches if t["statut"] == "done")
    stats = {
        "total":      total,
        "done":       done,
        "in_progress":sum(1 for t in taches if t["statut"] == "in_progress"),
        "todo":       sum(1 for t in taches if t["statut"] == "todo"),
        "blocked":    sum(1 for t in taches if t["statut"] == "blocked"),
        "en_retard":  sum(1 for t in taches if t["statut"] != "done" and t["date_echeance"] < now),
        "pct":        round((done / total * 100), 1) if total > 0 else 0,
        "h_est":      round(sum(t["temps_estime_heures"] for t in taches), 1),
        "h_reel":     round(sum(t.get("temps_reel_heures", 0) or 0 for t in taches), 1),
    }

    return render_template("projets/detail.html",
                           projet=projet, chef=chef, taches=taches,
                           stats=stats, now=now)


@bp.route("/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def ajouter():
    if request.method == "POST":
        try:
            projet = {
                "nom":           request.form["nom"],
                "description":   request.form["description"],
                "date_debut":    datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_fin_prevue": datetime.strptime(request.form["date_fin_prevue"], "%Y-%m-%d"),
                "date_fin_reelle": None,
                "statut":        request.form["statut"],
                "budget":        float(request.form["budget"]),
                "chef_projet_id": ObjectId(request.form["chef_projet_id"]),
            }
            ProjetModel.creer(projet)
            flash("Projet ajouté avec succès.", "success")
            return redirect(url_for("projets.liste"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    membres = MembreModel.tous({"nom": 1, "prenom": 1})
    return render_template("projets/form.html", projet=None, membres=membres)


@bp.route("/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def modifier(id):
    projet = ProjetModel.get_by_id(id)
    if not projet:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projets.liste"))

    if current_user.is_chef and projet.get("chef_projet_id") != current_user.member_oid:
        flash("Accès refusé : ce n'est pas votre projet.", "danger")
        return redirect(url_for("projets.liste"))

    if request.method == "POST":
        try:
            modifications = {
                "nom":           request.form["nom"],
                "description":   request.form["description"],
                "date_debut":    datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_fin_prevue": datetime.strptime(request.form["date_fin_prevue"], "%Y-%m-%d"),
                "statut":        request.form["statut"],
                "budget":        float(request.form["budget"]),
                "chef_projet_id": ObjectId(request.form["chef_projet_id"]),
            }
            if request.form["statut"] == "termine" and request.form.get("date_fin_reelle"):
                modifications["date_fin_reelle"] = datetime.strptime(
                    request.form["date_fin_reelle"], "%Y-%m-%d")
            else:
                modifications["date_fin_reelle"] = None

            ProjetModel.modifier(id, modifications)
            flash("Projet modifié avec succès.", "success")
            return redirect(url_for("projets.detail", id=id))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    membres = MembreModel.tous({"nom": 1, "prenom": 1})
    return render_template("projets/form.html", projet=projet, membres=membres)


@bp.route("/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin")
def supprimer(id):
    try:
        ProjetModel.supprimer(id)
        flash("Projet et tâches associées supprimés.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("projets.liste"))
