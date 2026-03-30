"""
controllers/dashboard.py — Blueprint dashboard (page d'accueil).
"""
from datetime import datetime

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from controllers.utils import get_projet_filter, get_tache_filter, get_accessible_projet_ids
from models.database import db
from aggregations import (avancement_par_projet, taches_en_retard,
                           charge_par_membre, retard_moyen_par_projet)

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    proj_filter  = get_projet_filter()
    tache_filter = get_tache_filter()
    proj_ids     = get_accessible_projet_ids()
    now          = datetime.now()

    total_projets = db.projects.count_documents(proj_filter)
    total_membres = db.members.count_documents({}) if not current_user.is_membre else 1
    total_taches  = db.tasks.count_documents(tache_filter)
    taches_done   = db.tasks.count_documents({**tache_filter, "statut": "done"})
    taches_retard = db.tasks.count_documents({
        **tache_filter,
        "statut": {"$ne": "done"},
        "date_echeance": {"$lt": now},
    })
    pct_global = round((taches_done / total_taches * 100), 1) if total_taches > 0 else 0

    return render_template("dashboard.html",
                           total_projets=total_projets,
                           total_membres=total_membres,
                           total_taches=total_taches,
                           taches_done=taches_done,
                           taches_retard=taches_retard,
                           pct_global=pct_global,
                           avancements=avancement_par_projet(db, proj_ids),
                           retards=taches_en_retard(db, proj_ids)[:10],
                           charges=charge_par_membre(db, proj_ids) if not current_user.is_membre else [],
                           retard_projets=retard_moyen_par_projet(db, proj_ids))
