#!/usr/bin/env python3
"""
app.py — Point d'entrée de l'application (factory MVC).

Architecture :
  models/       — accès aux données (MongoDB)
  controllers/  — logique métier + routes (Flask Blueprints)
  templates/    — vues Jinja2

Rôles :
  admin       - accès total
  chef_projet - ses projets + toutes les tâches dedans + lecture membres/stats
  membre      - uniquement ses tâches assignées + projets concernés (lecture)
"""
from datetime import datetime

from bson import ObjectId
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_login import LoginManager

from models.user import User
from controllers.utils import register_filters
from controllers import (auth, dashboard, projets, taches, membres,
                          stats, recherche, exports)


# ── JSON provider (sérialise ObjectId et datetime) ────────────────────

class MongoJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# ── Factory ───────────────────────────────────────────────────────────

def create_app():
    app = Flask(__name__)
    app.json_provider_class = MongoJSONProvider
    app.json = MongoJSONProvider(app)
    app.secret_key = "gestion_projets_tp_secret_key_v2"

    # Flask-Login
    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(user_id)

    # Filtres Jinja2
    register_filters(app)

    # Blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(projets.bp)
    app.register_blueprint(taches.bp)
    app.register_blueprint(membres.bp)
    app.register_blueprint(stats.bp)
    app.register_blueprint(recherche.bp)
    app.register_blueprint(exports.bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
