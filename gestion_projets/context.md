# Contexte du projet — Gestion de Projets MongoDB

## Sujet TP

Application de gestion de projets : une architecture pour stocker des informations sur les projets, les tâches, les délais et les membres de l'équipe.

Déclinaison de scripts pour faire ressortir des états d'avancement, des retards, taux de charge des membres de l'équipe, …

---

## Prompt de continuation

Tu travailles sur un TP de BDD NoSQL (MongoDB) en Python. Le projet est une application de gestion de projets avec une interface web Flask. Voici l'état actuel et ce qui reste à faire.

### Ce qui est déjà fait

- **`init_db.py`** — Crée 3 collections avec validation JSON Schema et index :
  - `members` (nom, prenom, email unique, role, competences[], date_embauche)
  - `projects` (nom, chef_projet_id ref, statut, budget, dates)
  - `tasks` (titre, projet_id ref, assignee_id ref, statut, priorite, temps_estime/reel_heures, dates)

- **`generate_mock_data.py`** — Génère 10 membres, 5 projets, 40-50 tâches avec Faker (fr_FR), scénarios réalistes (30% done, 20% en retard, 25% in_progress, 15% todo, 10% blocked)

- **`aggregations.py`** — 6 pipelines d'agrégation avec affichage console formaté :
  1. Avancement par projet (% + barre visuelle)
  2. Tâches en retard (avec jours de retard)
  3. Charge par membre (tâches actives par statut)
  4. Durée moyenne des tâches par projet (tâches done)
  5. Membres les plus/moins chargés
  6. Retard moyen par projet (en jours)

- **`views.py`** — 4 vues MongoDB read-only (recalculées dynamiquement via `$$NOW`) :
  - `vue_taches_en_retard`
  - `vue_avancement_projets`
  - `vue_charge_membres`
  - `vue_dashboard`

- **`app.py`** — Application Flask (583 lignes) avec CRUD complet :
  - Dashboard `/` avec KPIs et top 10 retards
  - CRUD Projets, Tâches, Membres
  - Page `/stats` avec les 6 agrégations
  - Page `/taches/retard` dédiée
  - Intégrité référentielle (vérif avant suppression membres)
  - Filtres Jinja2 : `datefr`, `statut_badge`, `priorite_badge`

- **Templates Bootstrap 5** (11 fichiers) : sidebar fixe, dark/light theme, formulaires avec datepicker, badges de statut/priorité

### Ce qui reste à faire / améliorer

Voici les pistes pour compléter le TP en lien avec le sujet :

1. **Export des rapports** — Ajouter des routes Flask pour exporter en CSV ou PDF :
   - État d'avancement global (`/export/avancement.csv`)
   - Liste des tâches en retard (`/export/retards.csv`)
   - Rapport de charge par membre (`/export/charge.csv`)

2. **Script de rapport autonome** — Créer un `rapport.py` standalone (sans Flask) qui génère un rapport texte ou HTML complet des états d'avancement, retards et charge — utilisable en cron ou en démo TP.

3. **Filtres et tri avancés sur `/taches`** — Actuellement filtrables par statut/priorité/projet, mais pas par membre assigné ni par date d'échéance.

4. **Graphiques dans le dashboard** — Ajouter Chart.js pour visualiser l'avancement (donut par statut) et la charge membres (bar chart) directement dans `dashboard.html`.

5. **Alertes retards** — Banner ou badge sur les projets/membres ayant des tâches critiques en retard.

6. **Tests de validation** — Vérifier que les contraintes JSON Schema rejettent bien les documents invalides (un petit `test_schema.py` de démonstration TP).

7. **Documentation des agrégations** — Commenter les étapes `$match`, `$lookup`, `$group`, `$project` dans `aggregations.py` pour expliquer la logique MongoDB (utile pour la soutenance).

### Stack technique

- Python 3.8+, Flask 3.0, PyMongo 4.6, Faker 22.0
- MongoDB 6.0+ sur `localhost:27017`, base `gestion_projets`
- Bootstrap 5 + Font Awesome (CDN), pas de frontend JS framework
- Pas de tests automatisés pour l'instant

### Commandes utiles

```bash
python init_db.py            # (Re)créer collections + index
python generate_mock_data.py # Générer les données de test
python views.py              # Créer les vues MongoDB
python aggregations.py       # Afficher les 6 rapports en console
python app.py                # Lancer Flask sur http://localhost:5000
```

### Priorité recommandée

Pour un TP complet et démontrable : **`rapport.py`** en priorité (démontre les agrégations sans dépendance Flask), puis **export CSV**, puis **graphiques Chart.js**.
