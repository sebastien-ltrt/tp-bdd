# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Application de gestion de projets en Python/Flask avec MongoDB. Sujet TP : stocker projets, tâches, délais et membres d'équipe, puis produire des états d'avancement, retards et taux de charge via des pipelines d'agrégation MongoDB.

## Setup & Commands

**Prérequis** : Python 3.8+, MongoDB 6.0+ sur `localhost:27017`

```bash
pip install -r requirements.txt   # Installer les dépendances

python init_db.py                 # Créer collections + validation JSON Schema + index
python generate_mock_data.py      # Générer 10 membres, 5 projets, 40-50 tâches réalistes
python views.py                   # Créer les 4 vues MongoDB
python aggregations.py            # Exécuter et afficher les 6 pipelines d'agrégation
python app.py                     # Lancer l'application Flask (http://localhost:5000)
```

Pour réinitialiser proprement la base de données, relancer `init_db.py` puis `generate_mock_data.py`.

## Architecture

### Collections MongoDB (`gestion_projets` database)

Les tâches sont dans une collection **séparée** (référencement, pas d'imbrication) parce que :
- Volume : un projet peut avoir 50+ tâches (limite 16 Mo par document)
- Requêtes transversales : tâches en retard tous projets confondus, charge par membre
- Mises à jour fréquentes de statut plus simples sur documents dédiés

| Collection | Champs clés | Statuts/Rôles |
|------------|-------------|----------------|
| `members` | nom, prenom, email (unique), role, competences[], date_embauche | developpeur, designer, chef_projet, testeur, devops, analyste |
| `projects` | nom, chef_projet_id (ref), dates, statut, budget | planifie, en_cours, termine, annule, en_pause |
| `tasks` | titre, projet_id (ref), assignee_id (ref), statut, priorite, temps_estime/reel_heures | todo, in_progress, done, blocked / low, medium, high, critical |

**Références** : on stocke des `ObjectId` et on utilise `$lookup` pour les jointures — pas de dénormalisation.

### Vues MongoDB (`views.py`)

Vues read-only créées avec `db.create_collection(viewOn=...)` — recalculées à chaque requête, utilisent `$$NOW` pour la date courante :

- `vue_taches_en_retard` — tâches non terminées avec échéance passée + détails projet/membre
- `vue_avancement_projets` — % d'avancement et répartition des statuts par projet
- `vue_charge_membres` — nombre de tâches actives par membre et par statut
- `vue_dashboard` — KPI globaux (synthèse, faceted aggregation)

### Pipelines d'agrégation (`aggregations.py`)

6 fonctions standalone affichant des résultats formatés en console :

1. `avancement_par_projet()` — % avancement avec barre visuelle `█░`
2. `taches_en_retard()` — liste avec jours de retard
3. `charge_par_membre()` — charge active par statut
4. `duree_moyenne_taches_par_projet()` — temps réel moyen (tâches done uniquement)
5. `membres_plus_moins_charges()` — top/flop membres
6. `retard_moyen_par_projet()` — retard moyen en jours par projet

### Application Flask (`app.py`)

Routes organisées par ressource. Connexion MongoDB à `localhost:27017/gestion_projets`.

**Dashboard** : `/` — KPIs, top 10 tâches en retard, avancement projets

**Projets** : `/projets` CRUD + `/projets/<id>` detail avec tâches et stats d'avancement

**Tâches** : `/taches` avec filtres (statut, priorité, projet) + `/taches/<id>/statut` (gère `date_fin_reelle` automatiquement) + `/taches/retard`

**Membres** : `/membres` CRUD avec vérification d'intégrité référentielle avant suppression

**Statistiques** : `/stats` — affiche les 6 agrégations complètes

**Filtres Jinja2** : `datefr` (date JJ/MM/AAAA), `statut_badge` et `priorite_badge` (classes Bootstrap)

### Templates

`base.html` fournit le layout : sidebar fixe 260px, Bootstrap 5, support dark/light theme via `data-bs-theme`, Font Awesome intégré. Toutes les pages héritent de ce base.

## Agent Guidelines

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
