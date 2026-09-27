"""Admin Management blueprint — FR-11 (fleet CRUD), FR-12 (vehicle status),
FR-13 (maintenance blocks), FR-14 (view/filter bookings), FR-15 (mark returned).

AdminService never writes Booking rows directly. FR-13 routes through
BookingService.createMaintenanceBlock() so BookingService stays the single
writer and the overlap check cannot be bypassed.
"""

from datetime import date

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for
)

from ..auth import admin_required
from ..booking import (
    cancel_booking, create_maintenance_block, find_conflicts, parse_date
)
from ..db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")

VALID_CATEGORIES = ("economy", "sedan", "suv", "truck")
VALID_STATUSES = ("available", "rented", "out_of_service")


# ---------------------------------------------------------------------------
# AdminService — fleet management (FR-11)
# ---------------------------------------------------------------------------

def add_vehicle(make, model, year, category, daily_rate, photo_url=None):
    """AdminService.addVehicle() — FR-11."""
    db = get_db()
    cursor = db.execute(
        "INSERT INTO vehicles (make, model, year, category, daily_rate,"
        " status, photo_url) VALUES (?, ?, ?, ?, ?, 'available', ?)",
        (make, model, year, category, daily_rate, photo_url),
    )
    db.commit()
    return cursor.lastrowid


def update_vehicle(vehicle_id, make, model, year, category, daily_rate, photo_url=None):
    """AdminService.updateVehicle() — FR-11."""
    db = get_db()
    db.execute(
        "UPDATE vehicles SET make = ?, model = ?, year = ?, category = ?,"
        " daily_rate = ?, photo_url = ? WHERE id = ?",
        (make, model, year, category, daily_rate, photo_url, vehicle_id),
    )
    db.commit()


def remove_vehicle(vehicle_id):
    """AdminService.removeVehicle() — FR-11.

    Refuses to remove a vehicle with confirmed future bookings against it;
    those must be dealt with first, for the same reason FR-12 holds a status
    change back. Returns (ok, message).
    """
    conflicts = find_conflicts(vehicle_id)

    if conflicts:
        return False, (
            f"This vehicle has {len(conflicts)} confirmed booking(s) ending "
            "today or later. Cancel them before removing the vehicle."
        )

    db = get_db()
    db.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    db.commit()

    return True, "Vehicle removed."


# ---------------------------------------------------------------------------
# AdminService — vehicle status (FR-12) and maintenance (FR-13)
# ---------------------------------------------------------------------------

def set_status(vehicle_id, status):
    """AdminService.setStatus() — FR-12.

    Taking a vehicle out of service is held back if confirmed future bookings
    exist against it. The system never silently cancels a customer booking:
    the admin is shown the conflicts and must cancel them explicitly first.

    Returns (ok, message, conflicts).
    """
    if status not in VALID_STATUSES:
        return False, "Invalid status.", []

    if status == "out_of_service":
        conflicts = find_conflicts(vehicle_id)
        if conflicts:
            return False, (
                f"Cannot take this vehicle out of service: "
                f"{len(conflicts)} confirmed booking(s) still stand against it."
            ), conflicts

    db = get_db()
    db.execute("UPDATE vehicles SET status = ? WHERE id = ?", (status, vehicle_id))
    db.commit()

    return True, f"Vehicle status set to {status}.", []


def block_maintenance(vehicle_id, start, end):
    """AdminService.blockMaintenance() — FR-13.

    Delegates the write to BookingService.createMaintenanceBlock() rather than
    inserting into bookings directly, preserving the single-writer rule.
    """
    booking_id = create_maintenance_block(vehicle_id, start, end)

    if booking_id is None:
        return False, (
            "Those dates conflict with an existing booking or maintenance "
            "window for this vehicle."
        )

    return True, "Maintenance window added."


# ---------------------------------------------------------------------------
# AdminService — bookings (FR-14, FR-15)
# ---------------------------------------------------------------------------

def list_bookings(status=None, from_date=None, to_date=None, booking_type=None):
    """AdminService.listBookings() — FR-14. Filter by date or status."""
    db = get_db()

    sql = (
        "SELECT b.*, v.make, v.model, v.year, u.name AS customer_name,"
        "       u.email AS customer_email"
        "  FROM bookings b"
        "  JOIN vehicles v ON v.id = b.vehicle_id"
        "  LEFT JOIN users u ON u.id = b.user_id"
        " WHERE 1 = 1"
    )
    params = []

    if status:
        sql += " AND b.status = ?"
        params.append(status)

    if booking_type:
        sql += " AND b.type = ?"
        params.append(booking_type)

    if from_date:
        sql += " AND b.end_date >= ?"
        params.append(from_date)

    if to_date:
        sql += " AND b.start_date <= ?"
        params.append(to_date)

    sql += " ORDER BY b.start_date DESC"

    return db.execute(sql, params).fetchall()


def mark_returned(booking_id):
    """AdminService.markReturned() — FR-15.

    Closes out the booking and frees the vehicle for display purposes.
    Returns (ok, message).
    """
    db = get_db()

    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?", (booking_id,)
    ).fetchone()

    if booking is None:
        return False, "Booking not found."

    if booking["status"] != "confirmed":
        return False, "Only a confirmed booking can be marked returned."

    db.execute(
        "UPDATE bookings SET status = 'completed' WHERE id = ?", (booking_id,)
    )
    # The vehicle goes back to available unless it's out of service
    db.execute(
        "UPDATE vehicles SET status = 'available'"
        " WHERE id = ? AND status != 'out_of_service'",
        (booking["vehicle_id"],),
    )
    db.commit()

    return True, "Vehicle marked as returned."


# ---------------------------------------------------------------------------
# Routes — all guarded by admin_required (NFR-2)
# ---------------------------------------------------------------------------

@bp.route("/")
@admin_required
def dashboard():
    """Admin landing page: fleet overview plus upcoming bookings."""
    db = get_db()
    vehicles = db.execute(
        "SELECT * FROM vehicles ORDER BY category, make, model"
    ).fetchall()
    upcoming = list_bookings(
        status="confirmed", from_date=date.today().isoformat(), booking_type="rental"
    )
    return render_template(
        "admin/dashboard.html", vehicles=vehicles, upcoming=upcoming
    )


@bp.route("/vehicles/new", methods=("GET", "POST"))
@admin_required
def new_vehicle():
    """FR-11 — add a vehicle."""
    if request.method == "POST":
        make = request.form.get("make", "").strip()
        model = request.form.get("model", "").strip()
        year = request.form.get("year", type=int)
        category = request.form.get("category")
        daily_rate = request.form.get("daily_rate", type=float)
        photo_url = request.form.get("photo_url", "").strip() or None

        error = None
        if not make or not model:
            error = "Make and model are required."
        elif not year:
            error = "Year is required."
        elif category not in VALID_CATEGORIES:
            error = "Please choose a valid category."
        elif not daily_rate or daily_rate <= 0:
            error = "Daily rate must be greater than zero."

        if error is None:
            add_vehicle(make, model, year, category, daily_rate, photo_url)
            flash("Vehicle added.")
            return redirect(url_for("admin.dashboard"))

        flash(error)

    return render_template("admin/vehicle_form.html",
                            vehicle=None, categories=VALID_CATEGORIES)


@bp.route("/vehicles/<int:vehicle_id>/edit", methods=("GET", "POST"))
@admin_required
def edit_vehicle(vehicle_id):
    """FR-11 — edit a vehicle."""
    db = get_db()
    vehicle = db.execute(
        "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()

    if vehicle is None:
        abort(404)

    if request.method == "POST":
        update_vehicle(
            vehicle_id,
            request.form.get("make", "").strip(),
            request.form.get("model", "").strip(),
            request.form.get("year", type=int),
            request.form.get("category"),
            request.form.get("daily_rate", type=float),
            request.form.get("photo_url", "").strip() or None,
        )
        flash("Vehicle updated.")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/vehicle_form.html",
                            vehicle=vehicle, categories=VALID_CATEGORIES)


@bp.route("/vehicles/<int:vehicle_id>/delete", methods=("POST",))
@admin_required
def delete_vehicle(vehicle_id):
    """FR-11 — remove a vehicle."""
    ok, message = remove_vehicle(vehicle_id)
    flash(message)
    return redirect(url_for("admin.dashboard"))


@bp.route("/vehicles/<int:vehicle_id>/status", methods=("POST",))
@admin_required
def change_status(vehicle_id):
    """FR-12 — change vehicle status, holding back on conflicts."""
    status = request.form.get("status")
    ok, message, conflicts = set_status(vehicle_id, status)

    flash(message)

    if not ok and conflicts:
        # Show the admin exactly which bookings are in the way
        return render_template(
            "admin/conflicts.html", vehicle_id=vehicle_id, conflicts=conflicts
        )

    return redirect(url_for("admin.dashboard"))


@bp.route("/vehicles/<int:vehicle_id>/maintenance", methods=("GET", "POST"))
@admin_required
def maintenance(vehicle_id):
    """FR-13 — block a date range for maintenance."""
    db = get_db()
    vehicle = db.execute(
        "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()

    if vehicle is None:
        abort(404)

    if request.method == "POST":
        start = parse_date(request.form.get("start"))
        end = parse_date(request.form.get("end"))

        if start is None or end is None:
            flash("Please enter both dates in YYYY-MM-DD format.")
        elif end < start:
            flash("The end date cannot be before the start date.")
        else:
            ok, message = block_maintenance(vehicle_id, start, end)
            flash(message)
            if ok:
                return redirect(url_for("admin.dashboard"))

    return render_template("admin/maintenance.html", vehicle=vehicle)


@bp.route("/bookings")
@admin_required
def bookings():
    """FR-14 — view all bookings, filtered by date or status."""
    status = request.args.get("status") or None
    from_date = request.args.get("from") or None
    to_date = request.args.get("to") or None

    rows = list_bookings(status=status, from_date=from_date, to_date=to_date)

    return render_template(
        "admin/bookings.html", bookings=rows,
        status=status, from_date=from_date, to_date=to_date,
    )


@bp.route("/bookings/<int:booking_id>/return", methods=("POST",))
@admin_required
def mark_return(booking_id):
    """FR-15 — mark a vehicle as returned."""
    ok, message = mark_returned(booking_id)
    flash(message)
    return redirect(url_for("admin.bookings"))


@bp.route("/bookings/<int:booking_id>/cancel", methods=("POST",))
@admin_required
def admin_cancel(booking_id):
    """Admin-side cancellation, used to clear conflicts before FR-12."""
    ok, message = cancel_booking(booking_id)
    flash(message)
    return redirect(url_for("admin.bookings"))
