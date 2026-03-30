"""
controllers/auth.py — Blueprint authentification (login / logout).
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from models.user import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user_doc = User.get_by_username(username)
        if not user_doc or not check_password_hash(user_doc["password_hash"], password):
            flash("Identifiant ou mot de passe incorrect.", "danger")
            return render_template("auth/login.html")

        if not user_doc.get("is_active", True):
            flash("Ce compte est désactivé. Contactez un administrateur.", "warning")
            return render_template("auth/login.html")

        user = User(user_doc)
        login_user(user, remember=request.form.get("remember") == "on")
        flash(f"Bienvenue, {user.username} !", "success")

        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard.index"))

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("auth.login"))
