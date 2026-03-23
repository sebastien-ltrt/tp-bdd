# Gestion de Projets — TP Application avec MongoDB

Application de gestion de projets en Python/PyMongo avec MongoDB.

## Architecture MongoDB

### Collections

| Collection | Description |
|------------|-------------|
| `members`  | Membres de l'équipe (nom, prénom, email, rôle, compétences, date_embauche) |
| `projects` | Projets (nom, description, dates, statut, budget, chef_projet_id) |
| `tasks`    | Tâches avec références vers projets et membres |

### Choix : Référencement vs Imbrication

Les **tâches sont dans une collection séparée** (référencement) plutôt qu'imbriquées dans les projets. Voici pourquoi :

1. **Volume** — Un projet peut avoir des dizaines de tâches. Imbriquer risquerait de dépasser la limite de 16 Mo par document et rendrait les mises à jour coûteuses (`$push`, `$pull` sur des tableaux profonds).

2. **Requêtes transversales** — On a besoin de requêter les tâches *indépendamment* des projets : tâches en retard tous projets confondus, charge par membre, etc. Avec l'imbrication, chaque requête nécessiterait `$unwind`, ce qui est moins performant.

3. **Mises à jour fréquentes** — Les tâches changent souvent de statut et de temps réel. Modifier un sous-document imbriqué est plus complexe qu'un simple `update_one` sur un document dédié.

4. **Agrégations et vues** — Les pipelines d'agrégation et les vues MongoDB fonctionnent naturellement avec `$lookup` entre collections séparées.

### Dénormalisation

Pas de dénormalisation excessive : on stocke les `ObjectId` comme références et on utilise `$lookup` pour les jointures. C'est le bon compromis entre intégrité des données et performance pour ce volume de données.

### Index

- `members` : index unique sur `email`, index sur `role`
- `projects` : index sur `statut`, `chef_projet_id`, `date_fin_prevue`
- `tasks` : index sur `projet_id`, `assignee_id`, `statut`, `date_echeance` + index composés pour les requêtes fréquentes (tâches en retard, charge par membre)

### Vues MongoDB

4 vues créées via `db.createView` :
- `vue_taches_en_retard` — Tâches non terminées dont l'échéance est passée
- `vue_avancement_projets` — Pourcentage d'avancement par projet
- `vue_charge_membres` — Nombre de tâches actives par membre
- `vue_dashboard` — Synthèse globale (KPI, répartition, avancement)

## Prérequis

- Python 3.8+
- MongoDB 6.0+ tournant sur `localhost:27017`

## Installation

```bash
cd gestion_projets/
pip install -r requirements.txt
```

## Utilisation

### 1. Initialiser la base de données

Crée les collections avec validation JSON Schema et les index :

```bash
python init_db.py
```

### 2. Générer les données de test

Génère 10 membres, 5 projets et 40-50 tâches réalistes :

```bash
python generate_mock_data.py
```

### 3. Voir les agrégations

Exécute et affiche les 6 pipelines d'agrégation :

```bash
python aggregations.py
```

### 4. Créer les vues MongoDB

```bash
python views.py
```

### 5. Lancer l'application interactive

```bash
python app.py
```

Menu interactif avec 15 options : CRUD projets/tâches/membres, dashboard, statistiques.

## Structure du projet

```
gestion_projets/
├── init_db.py              # Initialisation BDD (collections, validation, index)
├── generate_mock_data.py   # Génération de données réalistes avec Faker
├── aggregations.py         # 6 pipelines d'agrégation MongoDB
├── views.py                # 4 vues MongoDB (createView)
├── app.py                  # Application CLI interactive
├── requirements.txt        # Dépendances Python
└── README.md               # Ce fichier
```
