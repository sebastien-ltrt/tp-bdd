"""
controllers/taches.py — Blueprint CRUD tâches.
"""
from datetime import datetime

from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from pymongo.errors import PyMongoError

from controllers.utils import require_role, get_tache_filter, get_projet_filter, get_accessible_projet_ids
import models.tache as TacheModel
import models.projet as ProjetModel
import models.membre as MembreModel
from aggregations import taches_en_retard
from models.database import db

bp = Blueprint("taches", __name__, url_prefix="/taches")

_SORT_MAP = {
    "titre":    lambda o: {"titre": o},
    "statut":   lambda o: {"statut": o},
    "date":     lambda o: {"date_echeance": o},
    "heures":   lambda o: {"temps_estime_heures": o},
    "assignee": lambda o: {"assignee_nom": o},
    "projet":   lambda o: {"nom_projet": o},
    "priorite": lambda o: {"priorite_num": o},
}


@bp.route("/")
@login_required
def liste():
    base_filter    = get_tache_filter()
    filtre_statut  = request.args.get("statut")
    filtre_priorite = request.args.get("priorite")
    filtre_projet  = request.args.get("projet_id")
    filtre_membre  = request.args.get("assignee_id")
    tri   = request.args.get("tri", "retard")
    ordre = request.args.get("ordre", "asc")
    ordre_val = 1 if ordre == "asc" else -1

    filtre = dict(base_filter)
    if filtre_statut:   filtre["statut"]     = filtre_statut
    if filtre_priorite: filtre["priorite"]   = filtre_priorite
    if filtre_projet:   filtre["projet_id"]  = ObjectId(filtre_projet)
    if filtre_membre and not current_user.is_membre:
        filtre["assignee_id"] = ObjectId(filtre_membre)

    sort_stage = _SORT_MAP.get(tri, lambda o: {"est_en_retard": -1, "date_echeance": 1})(ordre_val)
    taches = TacheModel.liste(filtre, sort_stage)

    projets = ProjetModel.tous(get_projet_filter(), {"nom": 1})
    membres = MembreModel.tous({"nom": 1, "prenom": 1})
    return render_template("taches/liste.html",
                           taches=taches, projets=projets, membres=membres,
                           filtre_statut=filtre_statut, filtre_priorite=filtre_priorite,
                           filtre_projet=filtre_projet, filtre_membre=filtre_membre,
                           tri=tri, ordre=ordre)


@bp.route("/<id>")
@login_required
def detail(id):
    tache, projet, assignee = TacheModel.get_with_relations(id)
    if not tache:
        flash("Tâche introuvable.", "danger")
        return redirect(url_for("taches.liste"))

    if current_user.is_membre and tache.get("assignee_id") != current_user.member_oid:
        flash("Accès refusé.", "danger")
        return redirect(url_for("taches.liste"))

    est_en_retard = (tache["statut"] != "done" and
                     tache.get("date_echeance") and
                     tache["date_echeance"] < datetime.now())

    return render_template("taches/detail.html", tache=tache, projet=projet,
                           assignee=assignee, est_en_retard=est_en_retard, now=datetime.now())


@bp.route("/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def ajouter():
    if request.method == "POST":
        try:
            tache = {
                "titre":       request.form["titre"],
                "description": request.form.get("description", ""),
                "projet_id":   ObjectId(request.form["projet_id"]),
                "assignee_id": ObjectId(request.form["assignee_id"]),
                "statut":      "todo",
                "priorite":    request.form["priorite"],
                "date_debut":  datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_echeance": datetime.strptime(request.form["date_echeance"], "%Y-%m-%d"),
                "date_fin_reelle": None,
                "temps_estime_heures": float(request.form["temps_estime_heures"]),
                "temps_reel_heures":   None,
            }
            TacheModel.creer(tache)
            flash("Tâche ajoutée avec succès.", "success")
            return redirect(url_for("taches.liste"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    projets = ProjetModel.tous(get_projet_filter())
    membres = MembreModel.tous()
    return render_template("taches/form.html", tache=None, projets=projets, membres=membres)


@bp.route("/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def modifier(id):
    tache = TacheModel.get_by_id(id)
    if not tache:
        flash("Tâche introuvable.", "danger")
        return redirect(url_for("taches.liste"))

    if request.method == "POST":
        try:
            modifications = {
                "titre":       request.form["titre"],
                "description": request.form.get("description", ""),
                "projet_id":   ObjectId(request.form["projet_id"]),
                "assignee_id": ObjectId(request.form["assignee_id"]),
                "priorite":    request.form["priorite"],
                "date_debut":  datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_echeance": datetime.strptime(request.form["date_echeance"], "%Y-%m-%d"),
                "temps_estime_heures": float(request.form["temps_estime_heures"]),
            }
            temps_reel = request.form.get("temps_reel_heures")
            if temps_reel:
                modifications["temps_reel_heures"] = float(temps_reel)
            TacheModel.modifier(id, modifications)
            flash("Tâche modifiée avec succès.", "success")
            return redirect(url_for("taches.liste"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    projets = ProjetModel.tous(get_projet_filter())
    membres = MembreModel.tous()
    return render_template("taches/form.html", tache=tache, projets=projets, membres=membres)


@bp.route("/<id>/statut", methods=["POST"])
@login_required
def changer_statut(id):
    tache = TacheModel.get_by_id(id)
    if not tache:
        flash("Tâche introuvable.", "danger")
        return redirect(request.referrer or url_for("taches.liste"))

    if current_user.is_membre and tache.get("assignee_id") != current_user.member_oid:
        flash("Accès refusé.", "danger")
        return redirect(request.referrer or url_for("taches.liste"))

    nouveau_statut = request.form.get("statut")
    if nouveau_statut not in ["todo", "in_progress", "done", "blocked"]:
        flash("Statut invalide.", "danger")
        return redirect(request.referrer or url_for("taches.liste"))

    try:
        TacheModel.changer_statut(id, nouveau_statut, request.form.get("temps_reel_heures"))
        flash(f"Statut mis à jour : {nouveau_statut}", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")

    return redirect(request.referrer or url_for("taches.liste"))


@bp.route("/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin", "chef_projet")
def supprimer(id):
    try:
        TacheModel.supprimer(id)
        flash("Tâche supprimée.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(request.referrer or url_for("taches.liste"))


@bp.route("/retard")
@login_required
def retard():
    proj_ids = get_accessible_projet_ids()
    retards  = taches_en_retard(db, proj_ids)

    tri   = request.args.get("tri", "retard")
    ordre = request.args.get("ordre", "desc")
    reverse = (ordre == "desc")
    prio_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    sort_key_map = {
        "retard":   lambda r: r.get("jours_retard", 0),
        "titre":    lambda r: r.get("titre", ""),
        "projet":   lambda r: r.get("nom_projet", ""),
        "assignee": lambda r: r.get("assignee_nom", ""),
        "priorite": lambda r: prio_order.get(r.get("priorite", ""), 0),
        "date":     lambda r: r.get("date_echeance", datetime.min),
        "statut":   lambda r: r.get("statut", ""),
    }
    retards = sorted(retards, key=sort_key_map.get(tri, sort_key_map["retard"]), reverse=reverse)

    return render_template("taches/retard.html", retards=retards, tri=tri, ordre=ordre)
