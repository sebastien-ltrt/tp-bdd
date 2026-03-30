"""
models/database.py — Connexion MongoDB partagée.
"""
from init_db import get_database

_client, db = get_database()
