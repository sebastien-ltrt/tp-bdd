#!/usr/bin/env python3
"""
app.py - Application web Flask de gestion de projets
Interface graphique complète avec dashboard, CRUD et statistiques.
"""

from datetime import datetime
from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from pymongo.errors import PyMongoError

from init_db import get_database
from aggregations import (
    avancement_par_projet, taches_en_retard, charge_par_membre,
    duree_moyenne_taches_par_projet, membres_plus_moins_charges,
    retard_moyen_par_projet
)

app = Flask(__name__)
app.secret_key = "gestion_projets_tp_secret_key"

# --- Connexion MongoDB ---
_client, db = get_database()


# --- Filtres Jinja2 personnalisés ---

@app.template_filter("datefr")
def format_date_fr(value):
    """Formate une date en format français JJ/MM/AAAA."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)


@app.template_filter("statut_badge")
def statut_badge(statut):
    """Retourne la classe CSS Bootstrap pour un statut de tâche."""
    badges = {
        "todo": "secondary",
        "in_progress": "primary",
        "done": "success",
        "blocked": "danger",
        "planifie": "info",
        "en_cours": "primary",
        "termine": "success",
        "annule": "dark",
        "en_pause": "warning"
    }
    return badges.get(statut, "secondary")


@app.template_filter("priorite_badge")
def priorite_badge(priorite):
    """Retourne la classe CSS Bootstrap pour une priorité."""
    badges = {
        "low": "success",
        "medium": "info",
        "high": "warning",
        "critical": "danger"
    }
    return badges.get(priorite, "secondary")


# ========================
#  DASHBOARD (page d'accueil)
# ========================

@app.route("/")
def dashboard():
    """Page d'accueil — dashboard global avec KPI."""
    # Compteurs globaux
    total_projets = db.projects.count_documents({})
    total_membres = db.members.count_documents({})
    total_taches = db.tasks.count_documents({})
    taches_done = db.tasks.count_documents({"statut": "done"})
    taches_retard = db.tasks.count_documents({
        "statut": {"$ne": "done"},
        "date_echeance": {"$lt": datetime.now()}
    })

    pct_global = round((taches_done / total_taches * 100), 1) if total_taches > 0 else 0

    # Agrégations
    avancements = avancement_par_projet(db)
    retards = taches_en_retard(db)
    charges = charge_par_membre(db)
    retard_projets = retard_moyen_par_projet(db)

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


# ========================
#  PROJETS
# ========================

@app.route("/projets")
def liste_projets():
    """Liste tous les projets avec leur avancement."""
    projets = list(db.projects.aggregate([
        {"$lookup": {
            "from": "members",
            "localField": "chef_projet_id",
            "foreignField": "_id",
            "as": "chef"
        }},
        {"$unwind": {"path": "$chef", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "tasks",
            "localField": "_id",
            "foreignField": "projet_id",
            "as": "taches"
        }},
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
        {"$addFields": {
            "pct_avancement": {"$cond": [
                {"$eq": ["$nb_taches", 0]}, 0,
                {"$round": [{"$multiply": [{"$divide": ["$nb_done", "$nb_taches"]}, 100]}, 1]}
            ]}
        }},
        {"$project": {"taches": 0, "chef": 0}},
        {"$sort": {"date_debut": -1}}
    ]))

    return render_template("projets/liste.html", projets=projets)


@app.route("/projets/ajouter", methods=["GET", "POST"])
def ajouter_projet():
    """Formulaire d'ajout de projet."""
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
                "chef_projet_id": ObjectId(request.form["chef_projet_id"])
            }
            db.projects.insert_one(projet)
            flash("Projet ajouté avec succès.", "success")
            return redirect(url_for("liste_projets"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    membres = list(db.members.find().sort("nom", 1))
    return render_template("projets/form.html", projet=None, membres=membres)


@app.route("/projets/<id>/modifier", methods=["GET", "POST"])
def modifier_projet(id):
    """Formulaire de modification de projet."""
    projet = db.projects.find_one({"_id": ObjectId(id)})
    if not projet:
        flash("Projet introuvable.", "danger")
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
                "chef_projet_id": ObjectId(request.form["chef_projet_id"])
            }
            # Date de fin réelle si le statut est terminé
            if request.form["statut"] == "termine" and request.form.get("date_fin_reelle"):
                modifications["date_fin_reelle"] = datetime.strptime(
                    request.form["date_fin_reelle"], "%Y-%m-%d"
                )
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
def supprimer_projet(id):
    """Supprime un projet et ses tâches."""
    try:
        db.tasks.delete_many({"projet_id": ObjectId(id)})
        db.projects.delete_one({"_id": ObjectId(id)})
        flash("Projet et tâches associées supprimés.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("liste_projets"))


@app.route("/projets/<id>")
def detail_projet(id):
    """Dashboard détaillé d'un projet."""
    projet = db.projects.find_one({"_id": ObjectId(id)})
    if not projet:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("liste_projets"))

    # Chef de projet
    chef = db.members.find_one({"_id": projet["chef_projet_id"]})

    # Tâches du projet avec noms des assignés
    taches = list(db.tasks.aggregate([
        {"$match": {"projet_id": ObjectId(id)}},
        {"$lookup": {
            "from": "members",
            "localField": "assignee_id",
            "foreignField": "_id",
            "as": "assignee"
        }},
        {"$unwind": {"path": "$assignee", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {
            "assignee_nom": {"$concat": [
                {"$ifNull": ["$assignee.prenom", ""]}, " ",
                {"$ifNull": ["$assignee.nom", "N/A"]}
            ]}
        }},
        {"$sort": {"priorite": -1, "date_echeance": 1}}
    ]))

    # Stats
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

    stats = {
        "total": total, "done": done, "in_progress": in_progress,
        "todo": todo, "blocked": blocked, "en_retard": en_retard,
        "pct": pct, "h_est": round(h_est, 1), "h_reel": round(h_reel, 1)
    }

    return render_template("projets/detail.html",
                           projet=projet, chef=chef, taches=taches, stats=stats)


# ========================
#  TÂCHES
# ========================

@app.route("/taches")
def liste_taches():
    """Liste toutes les tâches avec filtres."""
    # Filtres depuis les query params
    filtre = {}
    filtre_statut = request.args.get("statut")
    filtre_priorite = request.args.get("priorite")
    filtre_projet = request.args.get("projet_id")

    if filtre_statut:
        filtre["statut"] = filtre_statut
    if filtre_priorite:
        filtre["priorite"] = filtre_priorite
    if filtre_projet:
        filtre["projet_id"] = ObjectId(filtre_projet)

    taches = list(db.tasks.aggregate([
        {"$match": filtre},
        {"$lookup": {
            "from": "projects",
            "localField": "projet_id",
            "foreignField": "_id",
            "as": "projet"
        }},
        {"$unwind": "$projet"},
        {"$lookup": {
            "from": "members",
            "localField": "assignee_id",
            "foreignField": "_id",
            "as": "assignee"
        }},
        {"$unwind": "$assignee"},
        {"$addFields": {
            "nom_projet": "$projet.nom",
            "assignee_nom": {"$concat": ["$assignee.prenom", " ", "$assignee.nom"]},
            "est_en_retard": {"$and": [
                {"$ne": ["$statut", "done"]},
                {"$lt": ["$date_echeance", datetime.now()]}
            ]}
        }},
        {"$sort": {"est_en_retard": -1, "date_echeance": 1}}
    ]))

    projets = list(db.projects.find({}, {"nom": 1}).sort("nom", 1))
    return render_template("taches/liste.html",
                           taches=taches, projets=projets,
                           filtre_statut=filtre_statut,
                           filtre_priorite=filtre_priorite,
                           filtre_projet=filtre_projet)


@app.route("/taches/ajouter", methods=["GET", "POST"])
def ajouter_tache():
    """Formulaire d'ajout de tâche."""
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
                "temps_reel_heures": None
            }
            db.tasks.insert_one(tache)
            flash("Tâche ajoutée avec succès.", "success")
            return redirect(url_for("liste_taches"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    projets = list(db.projects.find().sort("nom", 1))
    membres = list(db.members.find().sort("nom", 1))
    return render_template("taches/form.html", tache=None, projets=projets, membres=membres)


@app.route("/taches/<id>/modifier", methods=["GET", "POST"])
def modifier_tache(id):
    """Formulaire de modification de tâche."""
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

            # Temps réel (optionnel)
            temps_reel = request.form.get("temps_reel_heures")
            if temps_reel:
                modifications["temps_reel_heures"] = float(temps_reel)

            db.tasks.update_one({"_id": ObjectId(id)}, {"$set": modifications})
            flash("Tâche modifiée avec succès.", "success")
            return redirect(url_for("liste_taches"))
        except (PyMongoError, ValueError) as e:
            flash(f"Erreur : {e}", "danger")

    projets = list(db.projects.find().sort("nom", 1))
    membres = list(db.members.find().sort("nom", 1))
    return render_template("taches/form.html", tache=tache, projets=projets, membres=membres)


@app.route("/taches/<id>/statut", methods=["POST"])
def changer_statut_tache(id):
    """Change le statut d'une tâche (appelé en AJAX ou formulaire)."""
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
        else:
            # Si on repasse d'un statut terminé, effacer la date de fin
            tache = db.tasks.find_one({"_id": ObjectId(id)})
            if tache and tache.get("statut") == "done":
                modifications["date_fin_reelle"] = None

        db.tasks.update_one({"_id": ObjectId(id)}, {"$set": modifications})
        flash(f"Statut mis à jour : {nouveau_statut}", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")

    return redirect(request.referrer or url_for("liste_taches"))


@app.route("/taches/<id>/supprimer", methods=["POST"])
def supprimer_tache(id):
    """Supprime une tâche."""
    try:
        db.tasks.delete_one({"_id": ObjectId(id)})
        flash("Tâche supprimée.", "success")
    except PyMongoError as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(request.referrer or url_for("liste_taches"))


@app.route("/taches/retard")
def taches_en_retard_page():
    """Page dédiée aux tâches en retard."""
    retards = taches_en_retard(db)
    return render_template("taches/retard.html", retards=retards)


# ========================
#  MEMBRES
# ========================

@app.route("/membres")
def liste_membres():
    """Liste tous les membres avec leur charge."""
    membres = list(db.members.aggregate([
        {"$lookup": {
            "from": "tasks",
            "let": {"mid": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {
                    "$and": [
                        {"$eq": ["$assignee_id", "$$mid"]},
                        {"$in": ["$statut", ["in_progress", "todo", "blocked"]]}
                    ]
                }}}
            ],
            "as": "taches_actives"
        }},
        {"$lookup": {
            "from": "tasks",
            "let": {"mid": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {
                    "$and": [
                        {"$eq": ["$assignee_id", "$$mid"]},
                        {"$ne": ["$statut", "done"]},
                        {"$lt": ["$date_echeance", datetime.now()]}
                    ]
                }}}
            ],
            "as": "taches_retard"
        }},
        {"$addFields": {
            "nb_actives": {"$size": "$taches_actives"},
            "nb_retard": {"$size": "$taches_retard"}
        }},
        {"$project": {"taches_actives": 0, "taches_retard": 0}},
        {"$sort": {"nom": 1}}
    ]))

    return render_template("membres/liste.html", membres=membres)


@app.route("/membres/ajouter", methods=["GET", "POST"])
def ajouter_membre():
    """Formulaire d'ajout de membre."""
    if request.method == "POST":
        try:
            competences = [c.strip() for c in request.form["competences"].split(",") if c.strip()]
            membre = {
                "nom": request.form["nom"],
                "prenom": request.form["prenom"],
                "email": request.form["email"],
                "role": request.form["role"],
                "competences": competences,
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d")
            }
            db.members.insert_one(membre)
            flash("Membre ajouté avec succès.", "success")
            return redirect(url_for("liste_membres"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")

    return render_template("membres/form.html", membre=None)


@app.route("/membres/<id>/modifier", methods=["GET", "POST"])
def modifier_membre(id):
    """Formulaire de modification de membre."""
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
                "date_embauche": datetime.strptime(request.form["date_embauche"], "%Y-%m-%d")
            }
            db.members.update_one({"_id": ObjectId(id)}, {"$set": modifications})
            flash("Membre modifié avec succès.", "success")
            return redirect(url_for("liste_membres"))
        except PyMongoError as e:
            flash(f"Erreur : {e}", "danger")

    return render_template("membres/form.html", membre=membre)


@app.route("/membres/<id>/supprimer", methods=["POST"])
def supprimer_membre(id):
    """Supprime un membre (vérifie les dépendances)."""
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


# ========================
#  STATISTIQUES
# ========================

@app.route("/stats")
def statistiques():
    """Page de statistiques avec toutes les agrégations."""
    return render_template("stats.html",
                           avancements=avancement_par_projet(db),
                           retards=taches_en_retard(db),
                           charges=charge_par_membre(db),
                           durees=duree_moyenne_taches_par_projet(db),
                           extremes=membres_plus_moins_charges(db),
                           retard_projets=retard_moyen_par_projet(db))


# ========================
#  LANCEMENT
# ========================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
