"""Database connection and initialisation for the Car Rental Booking System."""

import sqlite3
from pathlib import Path

import click
from flask import current_app, g


def get_db():
    """Return a connection for the current request, creating one if needed.

    Rows come back as sqlite3.Row so they can be accessed by column name,
    e.g. vehicle['make'] instead of vehicle[1].
    """
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        # Foreign keys are off by default in SQLite and must be enabled per connection.
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(e=None):
    """Close the connection at the end of the request, if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables by running schema.sql."""
    db = get_db()
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()


@click.command("init-db")
def init_db_command():
    """CLI command: flask --app src init-db"""
    init_db()
    click.echo("Initialised the database.")


def init_app(app):
    """Register database hooks and CLI commands with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
