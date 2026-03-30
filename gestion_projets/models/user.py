"""
models/user.py — Classe User Flask-Login + chargement depuis MongoDB.
"""
from bson import ObjectId
from flask_login import UserMixin

from models.database import db


class User(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.username = doc["username"]
        self.email = doc["email"]
        self.app_role = doc["app_role"]
        self.member_oid = doc.get("member_id")
        self.is_active_account = doc.get("is_active", True)

    @property
    def is_admin(self):
        return self.app_role == "admin"

    @property
    def is_chef(self):
        return self.app_role == "chef_projet"

    @property
    def is_membre(self):
        return self.app_role == "membre"

    def get_id(self):
        return self.id

    @staticmethod
    def get_by_id(user_id):
        doc = db.users.find_one({"_id": ObjectId(user_id)})
        return User(doc) if doc else None

    @staticmethod
    def get_by_username(username):
        return db.users.find_one({"username": username})
