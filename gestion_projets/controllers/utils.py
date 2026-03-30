"""
controllers/utils.py — Helpers partagés entre tous les contrôleurs :
  - décorateur require_role
  - filtres d'accès selon le rôle courant
  - enregistrement des filtres Jinja2
"""
from functools import wraps
from datetime import datetime

from flask import redirect, url_for, flash
from flask_login import current_user

from models.database import db
from models import tache as TacheModel


# ── Décorateur rôle ────────────────────────────────────────────────

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if current_user.app_role not in roles:
                flash("Accès refusé : droits insuffisants.", "danger")
                return redirect(url_for("dashboard.index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Filtres d'accès par rôle ───────────────────────────────────────

def get_projet_filter():
    if current_user.is_admin:
        return {}
    if current_user.is_chef and current_user.member_oid:
        return {"chef_projet_id": current_user.member_oid}
    if current_user.is_membre and current_user.member_oid:
        proj_ids = TacheModel.ids_projets_de_membre(current_user.member_oid)
        return {"_id": {"$in": proj_ids}}
    return {"_id": None}


def get_tache_filter():
    if current_user.is_admin:
        return {}
    if current_user.is_chef and current_user.member_oid:
        proj_ids = db.projects.distinct("_id", {"chef_projet_id": current_user.member_oid})
        return {"projet_id": {"$in": proj_ids}}
    if current_user.is_membre and current_user.member_oid:
        return {"assignee_id": current_user.member_oid}
    return {"_id": None}


def get_accessible_projet_ids():
    if current_user.is_admin:
        return None
    return db.projects.distinct("_id", get_projet_filter())


# ── Enregistrement des filtres Jinja2 ──────────────────────────────

def register_filters(app):
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
            "todo": "secondary", "in_progress": "primary",
            "done": "success",   "blocked": "danger",
            "planifie": "info",  "en_cours": "primary",
            "termine": "success","annule": "dark", "en_pause": "warning",
        }
        return badges.get(statut, "secondary")

    @app.template_filter("priorite_badge")
    def priorite_badge(priorite):
        badges = {"low": "success", "medium": "info",
                  "high": "warning", "critical": "danger"}
        return badges.get(priorite, "secondary")
