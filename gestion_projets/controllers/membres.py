"""
controllers/membres.py — Blueprint CRUD membres.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from pymongo.errors import PyMongoError
from datetime import datetime

from controllers.utils import require_role
import models.membre as MembreModel

bp = Blueprint("membres", __name__, url_prefix="/membres")

ROLES = ["developpeur", "designer", "chef_projet", "testeur", "devops", "analyste"]

_SORT_MAP = {
    "nom":      lambda o: {"nom": o},
    "role":     lambda o: {"role": o},
    "actives":  lambda o: {"nb_actives": o},
    "retard":   lambda o: {"nb_retard": o},
    "embauche": lambda o: {"date_embauche": o},
}


@bp.route("/")
@login_required
@require_role("admin", "chef_projet")
def liste():
    filtre_role = request.args.get("role")
    filtre_q    = request.args.get("q", "").strip()
    tri   = request.args.get("tri", "nom")
    ordre = request.args.get("ordre", "asc")
    ordre_val = 1 if ordre == "asc" else -1

    match_filter = {}
    if filtre_role:
        match_filter["role"] = filtre_role
    if filtre_q:
        match_filter["$or"] = [
            {"nom":    {"$regex": filtre_q, "$options": "i"}},
            {"prenom": {"$regex": filtre_q, "$options": "i"}},
            {"email":  {"$regex": filtre_q, "$options": "i"}},
        ]

    sort_stage = _SORT_MAP.get(tri, _SORT_MAP["nom"])(ordre_val)
    membres = MembreModel.liste(match_filter, sort_stage)

    return render_template("membres/liste.html", membres=membres, roles=ROLES,
                           filtre_role=filtre_role, filtre_q=filtre_q,
                           tri=tri, ordre=ordre)


@bp.route("/<id>")
@login_required
@require_role("admin", "chef_projet")
def detail(id):
    membre = MembreModel.get_by_id(id)
    if not membre:
        flash("Membre introuvable.", "danger")
        return redirect(url_for("membres.liste"))

    tri   = request.args.get("tri", "date")
    ordre = request.args.get("ordre", "asc")
    ordre_val = 1 if ordre == "asc" else -1

    sort_map = {
        "titre":    {"titre": ordre_val},
        "statut":   {"statut": ordre_val},
        "date":     {"date_echeance": ordre_val},
        "heures":   {"temps_estime_heures": ordre_val},
        "priorite": {"priorite_num": ordre_val},
        "projet":   {"nom_projet": ordre_val},
    }
    taches = MembreModel.taches_du_membre(id, sort_map.get(tri, {"date_echeance": ordre_val}))

    nb_done    = sum(1 for t in taches if t["statut"] == "done")
    nb_actives = sum(1 for t in taches if t["statut"] in ("in_progress", "todo", "blocked"))
    nb_retard  = sum(1 for t in taches if t.get("est_en_retard"))
    stats = {
        "total":      len(taches),
        "done":       nb_done,
        "actives":    nb_actives,
        "retard":     nb_retard,
        "h_estimees": round(sum(t.get("temps_estime_heures", 0) or 0 for t in taches), 1),
        "h_reelles":  round(sum(t.get("temps_reel_heures",  0) or 0 for t in taches), 1),
    }

    return render_template("membres/detail.html", membre=membre, taches=taches,
                           stats=stats, tri=tri, ordre=ordre, now=datetime.now())


@bp.route("/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin")
def ajouter():
    if request.method == "POST":
        try:
            competences = [c.strip() for c in request.form["competences"].split(",") if c.strip()]
            membre = {
                "nom":         request.form["nom"],
                "prenom":      request.form["prenom"],
                "email":       request.form["email"],
                "role":        request.form["role"],
                "competences": competences,
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d"),
            }
            MembreModel.creer(membre)
            flash("Membre ajouté avec succès.", "success")
            return redirect(url_for("membres.liste"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")
    return render_template("membres/form.html", membre=None)


@bp.route("/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin")
def modifier(id):
    membre = MembreModel.get_by_id(id)
    if not membre:
        flash("Membre introuvable.", "danger")
        return redirect(url_for("membres.liste"))

    if request.method == "POST":
        try:
            competences = [c.strip() for c in request.form["competences"].split(",") if c.strip()]
            modifications = {
                "nom":         request.form["nom"],
                "prenom":      request.form["prenom"],
                "email":       request.form["email"],
                "role":        request.form["role"],
                "competences": competences,
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d"),
            }
            MembreModel.modifier(id, modifications)
            flash("Membre modifié avec succès.", "success")
            return redirect(url_for("membres.liste"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")
    return render_template("membres/form.html", membre=membre)


@bp.route("/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin")
def supprimer(id):
    try:
        MembreModel.supprimer(id)
        flash("Membre supprimé.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("membres.liste"))
