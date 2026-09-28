"""Authentication blueprint — FR-1 (register), FR-2 (login/logout),
NFR-1 (hashed passwords), NFR-2 (role-based route guard)."""

import functools
import sqlite3

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


def hash_password(password):
    """AuthService.hashPassword() — NFR-1. Salted hash, never plain text."""
    return generate_password_hash(password)


def register_user(name, email, phone, password):
    """AuthService.register() — FR-1."""
    db = get_db()
    db.execute(
        "INSERT INTO users (name, email, phone, password_hash, role)"
        " VALUES (?, ?, ?, ?, 'customer')",
        (name, email, phone, hash_password(password)),
    )
    db.commit()


def authenticate(email, password):
    """AuthService.login() — FR-2. Returns the user row, or None if invalid."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        return None

    return user


@bp.before_app_request
def load_logged_in_user():
    """Make the current user available as g.user on every request."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        )


def login_required(view):
    """Guard: redirect anonymous users to the login page."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    """Guard: NFR-2 — admin-only routes, separated from customer routes."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        if g.user["role"] != "admin":
            flash("You do not have permission to access that page.")
            return redirect(url_for("catalog.browse"))
        return view(**kwargs)

    return wrapped_view


@bp.route("/register", methods=("GET", "POST"))
def register():
    """FR-1 — a visitor can register with name, email, phone, password."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        error = None
        if not name:
            error = "Name is required."
        elif not email:
            error = "Email is required."
        elif not password:
            error = "Password is required."

        if error is None:
            try:
                register_user(name, email, phone, password)
            except sqlite3.IntegrityError:
                error = f"An account with the email {email} already exists."
            else:
                return redirect(url_for("auth.login"))

        flash(error)

    return render_template("auth/register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    """FR-2 — log in; the session holds the user id and role."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = authenticate(email, password)

        if user is None:
            flash("Incorrect email or password.")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("catalog.browse"))

    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    """FR-2 — log out, clearing the session."""
    session.clear()
    return redirect(url_for("catalog.browse"))
