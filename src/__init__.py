"""Application factory for the Car Rental Booking System."""

import os

from flask import Flask, render_template


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-in-production"),
        DATABASE=os.path.join(app.instance_path, "carrental.sqlite"),
    )

    if test_config is None:
        # Load config.py from the instance folder if it exists (not committed to git)
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    # The instance folder holds the SQLite file; Flask doesn't create it automatically.
    os.makedirs(app.instance_path, exist_ok=True)

    # Register database hooks and the init-db CLI command
    from . import db
    db.init_app(app)

    # Register blueprints — one per module from the Week 1 architecture
    from .auth import bp as auth_bp
    from .catalog import bp as catalog_bp
    from .booking import bp as booking_bp
    from .payment import bp as payment_bp
    from .admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        """Landing page — redirects into the vehicle catalogue."""
        return render_template("index.html")

    return app
