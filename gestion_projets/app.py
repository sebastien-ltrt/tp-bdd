#!/usr/bin/env python3
"""
app.py - Application web Flask de gestion de projets
Avec authentification (flask-login) et contrôle d'accès par rôle.

Rôles :
  admin       - accès total
  chef_projet - ses projets + toutes les tâches dedans + lecture membres/stats
  membre      - uniquement ses tâches assignées + projets concernés (lecture)
"""

import csv
import io
from datetime import datetime
from functools import wraps

from bson import ObjectId
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, Response)
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash

from init_db import get_database
from aggregations import (
    avancement_par_projet, taches_en_retard, charge_par_membre,
    duree_moyenne_taches_par_projet, membres_plus_moins_charges,
    retard_moyen_par_projet
)

app = Flask(__name__)
app.secret_key = "gestion_projets_tp_secret_key_v2"

# ── MongoDB ────────────────────────────────────────────────────────────
_client, db = get_database()

# ── Flask-Login ────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "warning"


class User(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.username = doc["username"]
        self.email = doc["email"]
        self.app_role = doc["app_role"]
        self.member_oid = doc.get("member_id")   # ObjectId ou None
        self.is_active_account = doc.get("is_active", True)

    # Alias courts utiles dans les templates
    @property
    def is_admin(self):
        return self.app_role == "admin"

    @property
    def is_chef(self):
        return self.app_role == "chef_projet"

    @property
    def is_membre(self):
        return self.app_role == "membre"

    def get_id(self):
        return self.id


@login_manager.user_loader
def load_user(user_id):
    doc = db.users.find_one({"_id": ObjectId(user_id)})
    return User(doc) if doc else None


# ── Décorateur rôle ────────────────────────────────────────────────────

def require_role(*roles):
    """Vérifie que l'utilisateur a l'un des rôles autorisés."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if current_user.app_role not in roles:
                flash("Accès refusé : droits insuffisants.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Helpers accès par rôle ─────────────────────────────────────────────

def get_projet_filter():
    """Retourne un filtre MongoDB projets selon le rôle courant."""
    if current_user.is_admin:
        return {}
    if current_user.is_chef and current_user.member_oid:
        return {"chef_projet_id": current_user.member_oid}
    if current_user.is_membre and current_user.member_oid:
        proj_ids = db.tasks.distinct("projet_id", {"assignee_id": current_user.member_oid})
        return {"_id": {"$in": proj_ids}}
    return {"_id": None}  # aucun accès


def get_tache_filter():
    """Retourne un filtre MongoDB tâches selon le rôle courant."""
    if current_user.is_admin:
        return {}
    if current_user.is_chef and current_user.member_oid:
        proj_ids = db.projects.distinct("_id", {"chef_projet_id": current_user.member_oid})
        return {"projet_id": {"$in": proj_ids}}
    if current_user.is_membre and current_user.member_oid:
        return {"assignee_id": current_user.member_oid}
    return {"_id": None}


def get_accessible_projet_ids():
    """Retourne la liste des ObjectId de projets accessibles (ou None = tous)."""
    if current_user.is_admin:
        return None
    proj_filter = get_projet_filter()
    return db.projects.distinct("_id", proj_filter)


# ──────────────────────────────────────────────────────────────────────
#  Filtres Jinja2
# ──────────────────────────────────────────────────────────────────────

@app.template_filter("datefr")
def format_date_fr(value):
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)


@app.template_filter("statut_badge")
def statut_badge(statut):
    badges = {
        "todo": "secondary", "in_progress": "primary", "done": "success", "blocked": "danger",
        "planifie": "info", "en_cours": "primary", "termine": "success",
        "annule": "dark", "en_pause": "warning",
    }
    return badges.get(statut, "secondary")


@app.template_filter("priorite_badge")
def priorite_badge(priorite):
    badges = {"low": "success", "medium": "info", "high": "warning", "critical": "danger"}
    return badges.get(priorite, "secondary")


# ──────────────────────────────────────────────────────────────────────
#  AUTHENTIFICATION
# ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user_doc = db.users.find_one({"username": username})
        if not user_doc or not check_password_hash(user_doc["password_hash"], password):
            flash("Identifiant ou mot de passe incorrect.", "danger")
            return render_template("auth/login.html")

        if not user_doc.get("is_active", True):
            flash("Ce compte est désactivé. Contactez un administrateur.", "warning")
            return render_template("auth/login.html")

        user = User(user_doc)
        login_user(user, remember=request.form.get("remember") == "on")
        flash(f"Bienvenue, {user.username} !", "success")

        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard"))

    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("login"))


# ──────────────────────────────────────────────────────────────────────
#  DASHBOARD
# ──────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    proj_filter = get_projet_filter()
    tache_filter = get_tache_filter()
    now = datetime.now()

    proj_ids = get_accessible_projet_ids()

    total_projets = db.projects.count_documents(proj_filter)
    total_membres = db.members.count_documents({}) if not current_user.is_membre else 1
    total_taches = db.tasks.count_documents(tache_filter)
    taches_done = db.tasks.count_documents({**tache_filter, "statut": "done"})
    taches_retard = db.tasks.count_documents({
        **tache_filter,
        "statut": {"$ne": "done"},
        "date_echeance": {"$lt": now},
    })
    pct_global = round((taches_done / total_taches * 100), 1) if total_taches > 0 else 0

    avancements = avancement_par_projet(db, proj_ids)
    retards = taches_en_retard(db, proj_ids)
    charges = charge_par_membre(db, proj_ids) if not current_user.is_membre else []
    retard_projets = retard_moyen_par_projet(db, proj_ids)

    return render_template("dashboard.html",
                           total_projets=total_projets,
                           total_membres=total_membres,
                           total_taches=total_taches,
                           taches_done=taches_done,
                           taches_retard=taches_retard,
                           pct_global=pct_global,
                           avancements=avancements,
                           retards=retards[:10],
                           charges=charges,
                           retard_projets=retard_projets)


# ──────────────────────────────────────────────────────────────────────
#  PROJETS
# ──────────────────────────────────────────────────────────────────────

@app.route("/projets")
@login_required
def liste_projets():
    proj_filter = get_projet_filter()
    projets = list(db.projects.aggregate([
        {"$match": proj_filter},
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
        {"$sort": {"date_debut": -1}},
    ]))
    return render_template("projets/liste.html", projets=projets)


@app.route("/projets/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def ajouter_projet():
    if request.method == "POST":
        try:
            projet = {
                "nom": request.form["nom"],
                "description": request.form["description"],
                "date_debut": datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_fin_prevue": datetime.strptime(request.form["date_fin_prevue"], "%Y-%m-%d"),
                "date_fin_reelle": None,
                "statut": request.form["statut"],
                "budget": float(request.form["budget"]),
                "chef_projet_id": ObjectId(request.form["chef_projet_id"]),
            }
            db.projects.insert_one(projet)
            flash("Projet ajouté avec succès.", "success")
            return redirect(url_for("liste_projets"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    membres = list(db.members.find().sort("nom", 1))
    return render_template("projets/form.html", projet=None, membres=membres)


@app.route("/projets/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def modifier_projet(id):
    projet = db.projects.find_one({"_id": ObjectId(id)})
    if not projet:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("liste_projets"))

    # Chef de projet ne peut modifier que ses projets
    if current_user.is_chef and projet.get("chef_projet_id") != current_user.member_oid:
        flash("Accès refusé : ce n'est pas votre projet.", "danger")
        return redirect(url_for("liste_projets"))

    if request.method == "POST":
        try:
            modifications = {
                "nom": request.form["nom"],
                "description": request.form["description"],
                "date_debut": datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_fin_prevue": datetime.strptime(request.form["date_fin_prevue"], "%Y-%m-%d"),
                "statut": request.form["statut"],
                "budget": float(request.form["budget"]),
                "chef_projet_id": ObjectId(request.form["chef_projet_id"]),
            }
            if request.form["statut"] == "termine" and request.form.get("date_fin_reelle"):
                modifications["date_fin_reelle"] = datetime.strptime(
                    request.form["date_fin_reelle"], "%Y-%m-%d")
            else:
                modifications["date_fin_reelle"] = None

            db.projects.update_one({"_id": ObjectId(id)}, {"$set": modifications})
            flash("Projet modifié avec succès.", "success")
            return redirect(url_for("detail_projet", id=id))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    membres = list(db.members.find().sort("nom", 1))
    return render_template("projets/form.html", projet=projet, membres=membres)


@app.route("/projets/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin")
def supprimer_projet(id):
    try:
        db.tasks.delete_many({"projet_id": ObjectId(id)})
        db.projects.delete_one({"_id": ObjectId(id)})
        flash("Projet et tâches associées supprimés.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("liste_projets"))


@app.route("/projets/<id>")
@login_required
def detail_projet(id):
    proj_filter = {**get_projet_filter(), "_id": ObjectId(id)}
    projet = db.projects.find_one(proj_filter)
    if not projet:
        flash("Projet introuvable ou accès refusé.", "danger")
        return redirect(url_for("liste_projets"))

    chef = db.members.find_one({"_id": projet["chef_projet_id"]})

    # Tâches : membre ne voit que les siennes
    tache_match = {"projet_id": ObjectId(id)}
    if current_user.is_membre and current_user.member_oid:
        tache_match["assignee_id"] = current_user.member_oid

    taches = list(db.tasks.aggregate([
        {"$match": tache_match},
        {"$lookup": {"from": "members", "localField": "assignee_id",
                     "foreignField": "_id", "as": "assignee"}},
        {"$unwind": {"path": "$assignee", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {"assignee_nom": {"$concat": [
            {"$ifNull": ["$assignee.prenom", ""]}, " ",
            {"$ifNull": ["$assignee.nom", "N/A"]}
        ]}}},
        {"$sort": {"priorite": -1, "date_echeance": 1}},
    ]))

    total = len(taches)
    done = sum(1 for t in taches if t["statut"] == "done")
    in_progress = sum(1 for t in taches if t["statut"] == "in_progress")
    todo = sum(1 for t in taches if t["statut"] == "todo")
    blocked = sum(1 for t in taches if t["statut"] == "blocked")
    en_retard = sum(1 for t in taches
                    if t["statut"] != "done" and t["date_echeance"] < datetime.now())
    pct = round((done / total * 100), 1) if total > 0 else 0
    h_est = sum(t["temps_estime_heures"] for t in taches)
    h_reel = sum(t.get("temps_reel_heures", 0) or 0 for t in taches)

    stats = {"total": total, "done": done, "in_progress": in_progress,
             "todo": todo, "blocked": blocked, "en_retard": en_retard,
             "pct": pct, "h_est": round(h_est, 1), "h_reel": round(h_reel, 1)}

    return render_template("projets/detail.html",
                           projet=projet, chef=chef, taches=taches, stats=stats, now=datetime.now())


# ──────────────────────────────────────────────────────────────────────
#  TÂCHES
# ──────────────────────────────────────────────────────────────────────

@app.route("/taches")
@login_required
def liste_taches():
    base_filter = get_tache_filter()
    filtre_statut = request.args.get("statut")
    filtre_priorite = request.args.get("priorite")
    filtre_projet = request.args.get("projet_id")
    filtre_membre = request.args.get("assignee_id")

    filtre = dict(base_filter)
    if filtre_statut:
        filtre["statut"] = filtre_statut
    if filtre_priorite:
        filtre["priorite"] = filtre_priorite
    if filtre_projet:
        filtre["projet_id"] = ObjectId(filtre_projet)
    if filtre_membre and not current_user.is_membre:
        filtre["assignee_id"] = ObjectId(filtre_membre)

    taches = list(db.tasks.aggregate([
        {"$match": filtre},
        {"$lookup": {"from": "projects", "localField": "projet_id",
                     "foreignField": "_id", "as": "projet"}},
        {"$unwind": "$projet"},
        {"$lookup": {"from": "members", "localField": "assignee_id",
                     "foreignField": "_id", "as": "assignee"}},
        {"$unwind": "$assignee"},
        {"$addFields": {
            "nom_projet": "$projet.nom",
            "assignee_nom": {"$concat": ["$assignee.prenom", " ", "$assignee.nom"]},
            "est_en_retard": {"$and": [
                {"$ne": ["$statut", "done"]},
                {"$lt": ["$date_echeance", datetime.now()]},
            ]},
        }},
        {"$sort": {"est_en_retard": -1, "date_echeance": 1}},
    ]))

    proj_filter = get_projet_filter()
    projets = list(db.projects.find(proj_filter, {"nom": 1}).sort("nom", 1))
    membres = list(db.members.find({}, {"nom": 1, "prenom": 1}).sort("nom", 1))
    return render_template("taches/liste.html",
                           taches=taches, projets=projets, membres=membres,
                           filtre_statut=filtre_statut, filtre_priorite=filtre_priorite,
                           filtre_projet=filtre_projet, filtre_membre=filtre_membre)


@app.route("/taches/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def ajouter_tache():
    if request.method == "POST":
        try:
            tache = {
                "titre": request.form["titre"],
                "description": request.form.get("description", ""),
                "projet_id": ObjectId(request.form["projet_id"]),
                "assignee_id": ObjectId(request.form["assignee_id"]),
                "statut": "todo",
                "priorite": request.form["priorite"],
                "date_debut": datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_echeance": datetime.strptime(request.form["date_echeance"], "%Y-%m-%d"),
                "date_fin_reelle": None,
                "temps_estime_heures": float(request.form["temps_estime_heures"]),
                "temps_reel_heures": None,
            }
            db.tasks.insert_one(tache)
            flash("Tâche ajoutée avec succès.", "success")
            return redirect(url_for("liste_taches"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    proj_filter = get_projet_filter()
    projets = list(db.projects.find(proj_filter).sort("nom", 1))
    membres = list(db.members.find().sort("nom", 1))
    return render_template("taches/form.html", tache=None, projets=projets, membres=membres)


@app.route("/taches/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin", "chef_projet")
def modifier_tache(id):
    tache = db.tasks.find_one({"_id": ObjectId(id)})
    if not tache:
        flash("Tâche introuvable.", "danger")
        return redirect(url_for("liste_taches"))

    if request.method == "POST":
        try:
            modifications = {
                "titre": request.form["titre"],
                "description": request.form.get("description", ""),
                "projet_id": ObjectId(request.form["projet_id"]),
                "assignee_id": ObjectId(request.form["assignee_id"]),
                "priorite": request.form["priorite"],
                "date_debut": datetime.strptime(request.form["date_debut"], "%Y-%m-%d"),
                "date_echeance": datetime.strptime(request.form["date_echeance"], "%Y-%m-%d"),
                "temps_estime_heures": float(request.form["temps_estime_heures"]),
            }
            temps_reel = request.form.get("temps_reel_heures")
            if temps_reel:
                modifications["temps_reel_heures"] = float(temps_reel)

            db.tasks.update_one({"_id": ObjectId(id)}, {"$set": modifications})
            flash("Tâche modifiée avec succès.", "success")
            return redirect(url_for("liste_taches"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    proj_filter = get_projet_filter()
    projets = list(db.projects.find(proj_filter).sort("nom", 1))
    membres = list(db.members.find().sort("nom", 1))
    return render_template("taches/form.html", tache=tache, projets=projets, membres=membres)


@app.route("/taches/<id>/statut", methods=["POST"])
@login_required
def changer_statut_tache(id):
    """Changement de statut — membre peut changer le statut de ses propres tâches."""
    tache = db.tasks.find_one({"_id": ObjectId(id)})
    if not tache:
        flash("Tâche introuvable.", "danger")
        return redirect(request.referrer or url_for("liste_taches"))

    # Membre ne peut modifier que ses tâches
    if current_user.is_membre and tache.get("assignee_id") != current_user.member_oid:
        flash("Accès refusé.", "danger")
        return redirect(request.referrer or url_for("liste_taches"))

    nouveau_statut = request.form.get("statut")
    if nouveau_statut not in ["todo", "in_progress", "done", "blocked"]:
        flash("Statut invalide.", "danger")
        return redirect(request.referrer or url_for("liste_taches"))

    try:
        modifications = {"statut": nouveau_statut}
        if nouveau_statut == "done":
            modifications["date_fin_reelle"] = datetime.now()
            temps_reel = request.form.get("temps_reel_heures")
            if temps_reel:
                modifications["temps_reel_heures"] = float(temps_reel)
        elif tache.get("statut") == "done":
            modifications["date_fin_reelle"] = None

        db.tasks.update_one({"_id": ObjectId(id)}, {"$set": modifications})
        flash(f"Statut mis à jour : {nouveau_statut}", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")

    return redirect(request.referrer or url_for("liste_taches"))


@app.route("/taches/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin", "chef_projet")
def supprimer_tache(id):
    try:
        db.tasks.delete_one({"_id": ObjectId(id)})
        flash("Tâche supprimée.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(request.referrer or url_for("liste_taches"))


@app.route("/taches/retard")
@login_required
def taches_en_retard_page():
    proj_ids = get_accessible_projet_ids()
    retards = taches_en_retard(db, proj_ids)
    return render_template("taches/retard.html", retards=retards)


# ──────────────────────────────────────────────────────────────────────
#  MEMBRES
# ──────────────────────────────────────────────────────────────────────

@app.route("/membres")
@login_required
@require_role("admin", "chef_projet")
def liste_membres():
    membres = list(db.members.aggregate([
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
                {"$lt": ["$date_echeance", datetime.now()]},
            ]}}}],
            "as": "taches_retard",
        }},
        {"$addFields": {
            "nb_actives": {"$size": "$taches_actives"},
            "nb_retard": {"$size": "$taches_retard"},
        }},
        {"$project": {"taches_actives": 0, "taches_retard": 0}},
        {"$sort": {"nom": 1}},
    ]))
    return render_template("membres/liste.html", membres=membres)


@app.route("/membres/ajouter", methods=["GET", "POST"])
@login_required
@require_role("admin")
def ajouter_membre():
    if request.method == "POST":
        try:
            competences = [c.strip() for c in request.form["competences"].split(",") if c.strip()]
            membre = {
                "nom": request.form["nom"],
                "prenom": request.form["prenom"],
                "email": request.form["email"],
                "role": request.form["role"],
                "competences": competences,
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d"),
            }
            db.members.insert_one(membre)
            flash("Membre ajouté avec succès.", "success")
            return redirect(url_for("liste_membres"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")
    return render_template("membres/form.html", membre=None)


@app.route("/membres/<id>/modifier", methods=["GET", "POST"])
@login_required
@require_role("admin")
def modifier_membre(id):
    membre = db.members.find_one({"_id": ObjectId(id)})
    if not membre:
        flash("Membre introuvable.", "danger")
        return redirect(url_for("liste_membres"))

    if request.method == "POST":
        try:
            competences = [c.strip() for c in request.form["competences"].split(",") if c.strip()]
            modifications = {
                "nom": request.form["nom"],
                "prenom": request.form["prenom"],
                "email": request.form["email"],
                "role": request.form["role"],
                "competences": competences,
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d"),
            }
            db.members.update_one({"_id": ObjectId(id)}, {"$set": modifications})
            flash("Membre modifié avec succès.", "success")
            return redirect(url_for("liste_membres"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")
    return render_template("membres/form.html", membre=membre)


@app.route("/membres/<id>/supprimer", methods=["POST"])
@login_required
@require_role("admin")
def supprimer_membre(id):
    oid = ObjectId(id)
    nb_taches = db.tasks.count_documents({"assignee_id": oid})
    nb_projets = db.projects.count_documents({"chef_projet_id": oid})

    if nb_taches > 0 or nb_projets > 0:
        flash(f"Impossible : ce membre a {nb_taches} tâche(s) et gère {nb_projets} projet(s). "
              "Réassignez-les d'abord.", "warning")
    else:
        try:
            db.members.delete_one({"_id": oid})
            flash("Membre supprimé.", "success")
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")
    return redirect(url_for("liste_membres"))


# ──────────────────────────────────────────────────────────────────────
#  EXPORTS CSV
# ──────────────────────────────────────────────────────────────────────

@app.route("/export/avancement.csv")
@login_required
@require_role("admin", "chef_projet")
def export_avancement_csv():
    proj_ids = get_accessible_projet_ids()
    data = avancement_par_projet(db, proj_ids)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["projet", "statut", "total_taches", "done", "in_progress", "todo", "blocked", "pct_avancement"])
    for r in data:
        writer.writerow([r["nom_projet"], r["statut_projet"], r["total_taches"],
                         r["taches_terminees"], r["taches_en_cours"],
                         r["taches_todo"], r["taches_bloquees"], r["pourcentage_avancement"]])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=avancement.csv"})


@app.route("/export/retards.csv")
@login_required
@require_role("admin", "chef_projet")
def export_retards_csv():
    proj_ids = get_accessible_projet_ids()
    data = taches_en_retard(db, proj_ids)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tache", "projet", "assignee", "jours_retard", "priorite", "statut", "echeance"])
    for r in data:
        echeance = r["date_echeance"].strftime("%d/%m/%Y") if r.get("date_echeance") else ""
        writer.writerow([r["titre"], r["nom_projet"], r["assignee_nom"],
                         int(r["jours_retard"]), r["priorite"], r["statut"], echeance])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=retards.csv"})


@app.route("/export/charge.csv")
@login_required
@require_role("admin", "chef_projet")
def export_charge_csv():
    proj_ids = get_accessible_projet_ids()
    data = charge_par_membre(db, proj_ids)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["membre", "role", "nb_actives", "in_progress", "todo", "blocked", "heures_estimees"])
    for r in data:
        writer.writerow([r["nom_complet"], r["role"], r["nb_taches_actives"],
                         r["nb_in_progress"], r["nb_todo"], r["nb_blocked"],
                         r["heures_estimees_total"]])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=charge_membres.csv"})


# ──────────────────────────────────────────────────────────────────────
#  STATISTIQUES
# ──────────────────────────────────────────────────────────────────────

@app.route("/stats")
@login_required
@require_role("admin", "chef_projet")
def statistiques():
    proj_ids = get_accessible_projet_ids()
    return render_template("stats.html",
                           avancements=avancement_par_projet(db, proj_ids),
                           retards=taches_en_retard(db, proj_ids),
                           charges=charge_par_membre(db, proj_ids),
                           durees=duree_moyenne_taches_par_projet(db, proj_ids),
                           extremes=membres_plus_moins_charges(db, proj_ids),
                           retard_projets=retard_moyen_par_projet(db, proj_ids))


# ──────────────────────────────────────────────────────────────────────
#  LANCEMENT
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
