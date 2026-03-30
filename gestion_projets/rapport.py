#!/usr/bin/env python3
"""
rapport.py - Script standalone de génération de rapports
Usage :
    python rapport.py              → console + HTML
    python rapport.py --console    → console uniquement
    python rapport.py --html       → HTML uniquement
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from init_db import get_database
from aggregations import (
    avancement_par_projet, taches_en_retard, charge_par_membre,
    duree_moyenne_taches_par_projet, membres_plus_moins_charges,
    retard_moyen_par_projet, afficher_resultats
)


# ---------------------------------------------------------------------------
#  Affichage console
# ---------------------------------------------------------------------------

def generer_console(db):
    """Affiche le rapport complet en console (réutilise aggregations.py)."""
    afficher_resultats()


# ---------------------------------------------------------------------------
#  Génération HTML
# ---------------------------------------------------------------------------

def _badge_statut(statut: str) -> str:
    couleurs = {
        "todo": "secondary", "in_progress": "primary",
        "done": "success", "blocked": "danger",
        "planifie": "info", "en_cours": "primary",
        "termine": "success", "annule": "dark", "en_pause": "warning"
    }
    c = couleurs.get(statut, "secondary")
    return f'<span class="badge bg-{c}">{statut}</span>'


def _badge_priorite(priorite: str) -> str:
    couleurs = {"low": "success", "medium": "info", "high": "warning", "critical": "danger"}
    c = couleurs.get(priorite, "secondary")
    return f'<span class="badge bg-{c}">{priorite}</span>'


def _datefr(dt) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y")
    return str(dt)


def generer_html(db) -> str:
    """Génère le rapport HTML complet et retourne la chaîne HTML."""
    maintenant = datetime.now()
    date_str = maintenant.strftime("%d/%m/%Y à %H:%M")

    avancements = avancement_par_projet(db)
    retards = taches_en_retard(db)
    charges = charge_par_membre(db)
    durees = duree_moyenne_taches_par_projet(db)
    extremes = membres_plus_moins_charges(db)
    retard_projets = retard_moyen_par_projet(db)

    # ---- Section 1 : Avancement par projet ----
    rows_avancement = ""
    for a in avancements:
        pct = a["pourcentage_avancement"]
        rows_avancement += f"""
        <div class="mb-3">
            <div class="d-flex justify-content-between mb-1">
                <strong>{a['nom_projet']}</strong>
                <span>{_badge_statut(a['statut_projet'])} &nbsp; <strong>{pct}%</strong></span>
            </div>
            <div class="progress" style="height:14px">
                <div class="progress-bar bg-success" style="width:{pct}%"></div>
            </div>
            <small class="text-muted">
                Terminées: {a['taches_terminees']} | En cours: {a['taches_en_cours']}
                | Todo: {a['taches_todo']} | Bloquées: {a['taches_bloquees']}
                | Total: {a['total_taches']}
            </small>
        </div>"""

    # ---- Section 2 : Tâches en retard ----
    if retards:
        lignes_retard = ""
        for r in retards:
            lignes_retard += f"""
            <tr>
                <td><strong>{r['titre']}</strong></td>
                <td>{r['nom_projet']}</td>
                <td>{r['assignee_nom']}</td>
                <td class="text-center"><span class="badge bg-danger">{int(r['jours_retard'])}j</span></td>
                <td class="text-center">{_badge_priorite(r['priorite'])}</td>
                <td class="text-center">{_badge_statut(r['statut'])}</td>
                <td class="text-center">{_datefr(r['date_echeance'])}</td>
            </tr>"""
        section_retards = f"""
        <div class="table-responsive">
            <table class="table table-sm table-bordered">
                <thead class="table-danger">
                    <tr>
                        <th>Tâche</th><th>Projet</th><th>Assigné</th>
                        <th class="text-center">Retard</th><th class="text-center">Priorité</th>
                        <th class="text-center">Statut</th><th class="text-center">Échéance</th>
                    </tr>
                </thead>
                <tbody>{lignes_retard}</tbody>
            </table>
        </div>"""
    else:
        section_retards = '<p class="text-success">Aucune tâche en retard.</p>'

    # ---- Section 3 : Charge par membre ----
    lignes_charge = ""
    for c in charges:
        badge_blocked = f'<span class="badge bg-danger">{c["nb_blocked"]}</span>' if c["nb_blocked"] > 0 else "0"
        lignes_charge += f"""
        <tr>
            <td><strong>{c['nom_complet']}</strong></td>
            <td>{c['role']}</td>
            <td class="text-center"><span class="badge bg-primary">{c['nb_taches_actives']}</span></td>
            <td class="text-center">{c['nb_in_progress']}</td>
            <td class="text-center">{c['nb_todo']}</td>
            <td class="text-center">{badge_blocked}</td>
            <td class="text-center">{c['heures_estimees_total']}h</td>
        </tr>"""

    # ---- Section 4 : Durée moyenne ----
    if durees:
        lignes_duree = ""
        for d in durees:
            lignes_duree += f"""
            <tr>
                <td>{d['nom_projet']}</td>
                <td class="text-center fw-bold">{d['duree_moyenne_jours']}j</td>
                <td class="text-center text-success">{d['duree_min_jours']}j</td>
                <td class="text-center text-danger">{d['duree_max_jours']}j</td>
                <td class="text-center">{d['nb_taches_terminees']}</td>
            </tr>"""
        section_durees = f"""
        <div class="table-responsive">
            <table class="table table-sm table-bordered">
                <thead class="table-info">
                    <tr>
                        <th>Projet</th>
                        <th class="text-center">Moyenne</th>
                        <th class="text-center">Min</th>
                        <th class="text-center">Max</th>
                        <th class="text-center">Nb tâches</th>
                    </tr>
                </thead>
                <tbody>{lignes_duree}</tbody>
            </table>
        </div>"""
    else:
        section_durees = '<p class="text-muted">Aucune tâche terminée avec date de fin.</p>'

    # ---- Section 5 : Membres extrêmes ----
    plus_charges_html = "".join(
        f'<li><strong>{m["nom_complet"]}</strong> <small class="text-muted">({m["role"]})</small> — '
        f'<span class="badge bg-danger">{m["nb_taches_actives"]} tâches</span></li>'
        for m in extremes.get("plus_charges", [])
    )
    moins_charges_html = "".join(
        f'<li><strong>{m["nom_complet"]}</strong> <small class="text-muted">({m["role"]})</small> — '
        f'<span class="badge bg-success">{m["nb_taches_actives"]} tâches</span></li>'
        for m in extremes.get("moins_charges", [])
    )
    classement_html = "".join(
        f'<tr><td>{i+1}.</td><td>{m["nom_complet"]}</td>'
        f'<td><small class="text-muted">{m["role"]}</small></td>'
        f'<td class="text-end"><span class="badge bg-secondary">{m["nb_taches_actives"]}</span></td></tr>'
        for i, m in enumerate(extremes.get("classement", []))
    )

    # ---- Section 6 : Retard moyen par projet ----
    lignes_retard_projet = ""
    for r in retard_projets:
        lignes_retard_projet += f"""
        <tr>
            <td><strong>{r['nom_projet']}</strong></td>
            <td class="text-center"><span class="badge bg-warning text-dark">{r['retard_moyen_jours']}j</span></td>
            <td class="text-center text-danger">{r['retard_max_jours']}j</td>
            <td class="text-center">{r['nb_taches_en_retard']}</td>
        </tr>"""

    # ---- Assemblage HTML ----
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Rapport Gestion Projets — {date_str}</title>
    <link rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; }}
        .report-header {{ background: linear-gradient(135deg, #0d6efd, #6610f2);
                          color: white; padding: 2rem; border-radius: 12px; margin-bottom: 2rem; }}
        .section-card {{ background: white; border-radius: 10px; padding: 1.5rem;
                         box-shadow: 0 2px 8px rgba(0,0,0,.08); margin-bottom: 1.5rem; }}
        .progress {{ height: 14px; border-radius: 8px; }}
        h5 {{ border-bottom: 2px solid #dee2e6; padding-bottom: .5rem; margin-bottom: 1rem; }}
    </style>
</head>
<body>
<div class="container py-4">

    <div class="report-header">
        <h2 class="mb-1">Rapport de Gestion de Projets</h2>
        <p class="mb-0 opacity-75">Généré le {date_str} · Base MongoDB <code>gestion_projets</code></p>
    </div>

    <!-- 1. Avancement par projet -->
    <div class="section-card">
        <h5>1. Avancement par projet</h5>
        {rows_avancement if rows_avancement else '<p class="text-muted">Aucun projet.</p>'}
    </div>

    <!-- 2. Tâches en retard ({len(retards)}) -->
    <div class="section-card">
        <h5>2. Tâches en retard
            <span class="badge bg-danger ms-2">{len(retards)}</span>
        </h5>
        {section_retards}
    </div>

    <!-- 3. Charge par membre -->
    <div class="section-card">
        <h5>3. Charge par membre</h5>
        <div class="table-responsive">
            <table class="table table-sm table-bordered">
                <thead class="table-primary">
                    <tr>
                        <th>Membre</th><th>Rôle</th>
                        <th class="text-center">Actives</th>
                        <th class="text-center">En cours</th>
                        <th class="text-center">Todo</th>
                        <th class="text-center">Bloquées</th>
                        <th class="text-center">Heures</th>
                    </tr>
                </thead>
                <tbody>{lignes_charge}</tbody>
            </table>
        </div>
    </div>

    <!-- 4. Durée moyenne des tâches -->
    <div class="section-card">
        <h5>4. Durée moyenne des tâches par projet (tâches terminées)</h5>
        {section_durees}
    </div>

    <!-- 5. Membres les plus/moins chargés -->
    <div class="section-card">
        <h5>5. Membres les plus / moins chargés</h5>
        <div class="row">
            <div class="col-md-6">
                <h6 class="text-danger">Plus chargé(s)</h6>
                <ul class="list-unstyled">{plus_charges_html}</ul>
                <h6 class="text-success mt-3">Moins chargé(s)</h6>
                <ul class="list-unstyled">{moins_charges_html}</ul>
            </div>
            <div class="col-md-6">
                <h6>Classement complet</h6>
                <table class="table table-sm">
                    <tbody>{classement_html}</tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 6. Retard moyen par projet -->
    <div class="section-card">
        <h5>6. Retard moyen par projet</h5>
        {f'''<div class="table-responsive">
            <table class="table table-sm table-bordered">
                <thead class="table-warning">
                    <tr>
                        <th>Projet</th>
                        <th class="text-center">Retard moyen</th>
                        <th class="text-center">Retard max</th>
                        <th class="text-center">Nb tâches</th>
                    </tr>
                </thead>
                <tbody>{lignes_retard_projet}</tbody>
            </table>
        </div>''' if retard_projets else '<p class="text-success">Aucun retard de projet.</p>'}
    </div>

    <footer class="text-center text-muted small py-3">
        Rapport généré automatiquement par <strong>rapport.py</strong> — TP BDD NoSQL MongoDB
    </footer>
</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
#  Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Génère un rapport de gestion de projets.")
    parser.add_argument("--console", action="store_true", help="Affichage console uniquement")
    parser.add_argument("--html", action="store_true", help="Génération HTML uniquement")
    args = parser.parse_args()

    # Par défaut : les deux
    mode_console = args.console or (not args.console and not args.html)
    mode_html = args.html or (not args.console and not args.html)

    client, db = get_database()

    try:
        if mode_console:
            print("\nAffichage console des agrégations...")
            afficher_resultats()

        if mode_html:
            html = generer_html(db)
            nom_fichier = f"rapport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            Path(nom_fichier).write_text(html, encoding="utf-8")
            print(f"\nRapport HTML généré : {nom_fichier}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
