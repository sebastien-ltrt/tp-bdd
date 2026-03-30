"""
controllers/exports.py — Blueprint exports CSV.
"""
import csv
import io

from flask import Blueprint, Response
from flask_login import login_required

from controllers.utils import require_role, get_accessible_projet_ids
from models.database import db
from aggregations import avancement_par_projet, taches_en_retard, charge_par_membre

bp = Blueprint("exports", __name__, url_prefix="/export")


def _csv_response(rows, headers, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    return Response("\ufeff" + output.getvalue(),
                    mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.route("/avancement.csv")
@login_required
@require_role("admin", "chef_projet")
def avancement_csv():
    proj_ids = get_accessible_projet_ids()
    data = avancement_par_projet(db, proj_ids)
    rows = [[r["nom_projet"], r["statut_projet"], r["total_taches"],
             r["taches_terminees"], r["taches_en_cours"],
             r["taches_todo"], r["taches_bloquees"], r["pourcentage_avancement"]]
            for r in data]
    return _csv_response(rows,
                         ["projet", "statut", "total_taches", "done", "in_progress",
                          "todo", "blocked", "pct_avancement"],
                         "avancement.csv")


@bp.route("/retards.csv")
@login_required
@require_role("admin", "chef_projet")
def retards_csv():
    proj_ids = get_accessible_projet_ids()
    data = taches_en_retard(db, proj_ids)
    rows = [[r["titre"], r["nom_projet"], r["assignee_nom"],
             int(r["jours_retard"]), r["priorite"], r["statut"],
             r["date_echeance"].strftime("%d/%m/%Y") if r.get("date_echeance") else ""]
            for r in data]
    return _csv_response(rows,
                         ["tache", "projet", "assignee", "jours_retard",
                          "priorite", "statut", "echeance"],
                         "retards.csv")


@bp.route("/charge.csv")
@login_required
@require_role("admin", "chef_projet")
def charge_csv():
    proj_ids = get_accessible_projet_ids()
    data = charge_par_membre(db, proj_ids)
    rows = [[r["nom_complet"], r["role"], r["nb_taches_actives"],
             r["nb_in_progress"], r["nb_todo"], r["nb_blocked"],
             r["heures_estimees_total"]]
            for r in data]
    return _csv_response(rows,
                         ["membre", "role", "nb_actives", "in_progress",
                          "todo", "blocked", "heures_estimees"],
                         "charge_membres.csv")
