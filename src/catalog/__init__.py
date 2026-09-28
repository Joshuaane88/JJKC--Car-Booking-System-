"""Vehicle Catalogue blueprint — FR-3 (browse/filter fleet), FR-4 (vehicle detail)."""

from flask import Blueprint, abort, render_template, request

from ..db import get_db

bp = Blueprint("catalog", __name__, url_prefix="/vehicles")

VALID_CATEGORIES = ("economy", "sedan", "suv", "truck")


def list_vehicles(category=None):
    """CatalogService.listVehicles(category) — FR-3.

    Returns all vehicles, optionally filtered by category. Vehicles that are
    out of service are excluded from the customer-facing catalogue.
    """
    db = get_db()

    sql = "SELECT * FROM vehicles WHERE status != 'out_of_service'"
    params = []

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY category, make, model"

    return db.execute(sql, params).fetchall()


def get_vehicle(vehicle_id):
    """CatalogService.getVehicle(id) — FR-4.

    Returns a single vehicle row, or None if it doesn't exist.
    """
    db = get_db()
    return db.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()


@bp.route("/")
def browse():
    """FR-3 — browse the fleet, optionally filtered by ?category=."""
    category = request.args.get("category")

    # Ignore an unrecognised category rather than erroring out
    if category not in VALID_CATEGORIES:
        category = None

    vehicles = list_vehicles(category)

    return render_template(
        "catalog/browse.html",
        vehicles=vehicles,
        categories=VALID_CATEGORIES,
        selected_category=category,
    )


@bp.route("/<int:vehicle_id>")
def detail(vehicle_id):
    """FR-4 — vehicle detail page."""
    vehicle = get_vehicle(vehicle_id)

    if vehicle is None:
        abort(404)

    return render_template("catalog/detail.html", vehicle=vehicle)
