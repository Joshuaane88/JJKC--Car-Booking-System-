"""Booking blueprint — FR-5 (availability search), FR-6 (create booking),
FR-10 (history/cancel), FR-16 (reject overlapping bookings)."""

import secrets
from datetime import date, datetime

from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
)

from ..auth import login_required
from ..db import get_db

bp = Blueprint("booking", __name__, url_prefix="/bookings")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_date(value):
    """Parse an ISO date string ('YYYY-MM-DD'). Returns None if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_between(start, end):
    """Rental length in days. A single-day rental counts as 1 day."""
    return (end - start).days + 1


def calculate_cost(daily_rate, start, end):
    """Booking.calculateCost() — FR-6. daily_rate × number of days."""
    return round(daily_rate * days_between(start, end), 2)


def generate_reference():
    """Booking.generateReference() — FR-8. Short, unique, human-readable."""
    return "CR-" + secrets.token_hex(4).upper()


# ---------------------------------------------------------------------------
# BookingService — the only writer of Booking rows
# ---------------------------------------------------------------------------

def check_availability(vehicle_id, start, end, exclude_booking_id=None):
    """BookingService.checkAvailability() — FR-16.

    THE single enforcement point for the overlap rule. Returns True if the
    vehicle is free for [start, end], False if any confirmed booking overlaps.

    The rule (from the SRS):
        existing.start_date <= end AND existing.end_date >= start

    Two ranges overlap unless one ends entirely before the other begins.
    Note this treats the range as INCLUSIVE on both ends: a booking ending
    2026-10-05 blocks a new booking starting 2026-10-05. That is the
    same-day boundary decision — the vehicle needs to be returned and turned
    around before it goes out again.

    Maintenance rows (type='maintenance') are stored in this same table, so
    this one query covers both customer bookings and maintenance windows.
    """
    db = get_db()

    sql = (
        "SELECT COUNT(*) AS conflicts FROM bookings"
        " WHERE vehicle_id = ?"
        "   AND status = 'confirmed'"
        "   AND start_date <= ?"
        "   AND end_date >= ?"
    )
    params = [vehicle_id, end.isoformat(), start.isoformat()]

    # Used when editing an existing booking so it doesn't conflict with itself
    if exclude_booking_id is not None:
        sql += " AND id != ?"
        params.append(exclude_booking_id)

    row = db.execute(sql, params).fetchone()
    return row["conflicts"] == 0


def search_available(start, end, category=None):
    """BookingService.searchAvailable() — FR-5.

    Returns vehicles with no conflicting confirmed booking for the full range.
    Out-of-service vehicles are excluded outright (FR-12).
    """
    db = get_db()

    sql = (
        "SELECT v.* FROM vehicles v"
        " WHERE v.status != 'out_of_service'"
        "   AND NOT EXISTS ("
        "       SELECT 1 FROM bookings b"
        "        WHERE b.vehicle_id = v.id"
        "          AND b.status = 'confirmed'"
        "          AND b.start_date <= ?"
        "          AND b.end_date >= ?"
        "   )"
    )
    params = [end.isoformat(), start.isoformat()]

    if category:
        sql += " AND v.category = ?"
        params.append(category)

    sql += " ORDER BY v.daily_rate, v.make"

    return db.execute(sql, params).fetchall()


def create_booking(user_id, vehicle_id, start, end):
    """BookingService.createBooking() — FR-6.

    Re-checks availability immediately before inserting (the second check in
    the booking flow) so a vehicle that was taken between search and submit
    cannot be double-booked. Returns the new booking id, or None on conflict.
    """
    db = get_db()

    # Second availability check — before any payment is attempted
    if not check_availability(vehicle_id, start, end):
        return None

    vehicle = db.execute(
        "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()

    if vehicle is None or vehicle["status"] == "out_of_service":
        return None

    total_cost = calculate_cost(vehicle["daily_rate"], start, end)

    cursor = db.execute(
        "INSERT INTO bookings"
        " (vehicle_id, user_id, start_date, end_date, total_cost,"
        "  status, type, reference)"
        " VALUES (?, ?, ?, ?, ?, 'confirmed', 'rental', ?)",
        (
            vehicle_id,
            user_id,
            start.isoformat(),
            end.isoformat(),
            total_cost,
            generate_reference(),
        ),
    )
    db.commit()

    return cursor.lastrowid


def create_maintenance_block(vehicle_id, start, end):
    """BookingService.createMaintenanceBlock() — FR-13.

    Called by AdminService.blockMaintenance(). AdminService does NOT write
    Booking rows directly: routing through here keeps BookingService the
    single writer, so the overlap check can never be bypassed.
    """
    db = get_db()

    if not check_availability(vehicle_id, start, end):
        return None

    cursor = db.execute(
        "INSERT INTO bookings"
        " (vehicle_id, user_id, start_date, end_date, total_cost,"
        "  status, type, reference)"
        " VALUES (?, NULL, ?, ?, NULL, 'confirmed', 'maintenance', NULL)",
        (vehicle_id, start.isoformat(), end.isoformat()),
    )
    db.commit()

    return cursor.lastrowid


def find_conflicts(vehicle_id, from_date=None):
    """BookingService.findConflicts() — used by the admin out-of-service flow.

    Returns confirmed customer bookings for this vehicle ending on or after
    from_date (defaults to today).
    """
    db = get_db()
    from_date = from_date or date.today()

    return db.execute(
        "SELECT * FROM bookings"
        " WHERE vehicle_id = ?"
        "   AND status = 'confirmed'"
        "   AND type = 'rental'"
        "   AND end_date >= ?"
        " ORDER BY start_date",
        (vehicle_id, from_date.isoformat()),
    ).fetchall()


def get_booking(booking_id):
    """Fetch a single booking joined with its vehicle details."""
    db = get_db()
    return db.execute(
        "SELECT b.*, v.make, v.model, v.year, v.category, v.daily_rate"
        "  FROM bookings b"
        "  JOIN vehicles v ON v.id = b.vehicle_id"
        " WHERE b.id = ?",
        (booking_id,),
    ).fetchone()


def booking_history(user_id):
    """Customer.viewBookingHistory() — FR-10."""
    db = get_db()
    return db.execute(
        "SELECT b.*, v.make, v.model, v.year"
        "  FROM bookings b"
        "  JOIN vehicles v ON v.id = b.vehicle_id"
        " WHERE b.user_id = ?"
        "   AND b.type = 'rental'"
        " ORDER BY b.start_date DESC",
        (user_id,),
    ).fetchall()


def cancel_booking(booking_id, user_id=None):
    """BookingService.cancelBooking() — FR-10.

    A customer may only cancel a booking that has not started. Passing
    user_id restricts cancellation to that customer's own bookings; admins
    call this without it.
    """
    db = get_db()
    booking = get_booking(booking_id)

    if booking is None:
        return False, "Booking not found."

    if user_id is not None and booking["user_id"] != user_id:
        return False, "That booking does not belong to you."

    if booking["status"] != "confirmed":
        return False, "Only confirmed bookings can be cancelled."

    if parse_date(booking["start_date"]) <= date.today():
        return False, "A booking that has already started cannot be cancelled."

    db.execute(
        "UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,)
    )
    db.commit()

    return True, "Booking cancelled."


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/search")
def search():
    """FR-5 — enter a date range, see only vehicles free for that full range."""
    start_raw = request.args.get("start", "")
    end_raw = request.args.get("end", "")
    category = request.args.get("category") or None

    start = parse_date(start_raw)
    end = parse_date(end_raw)
    vehicles = None
    error = None

    if start_raw or end_raw:
        if start is None or end is None:
            error = "Please enter both dates in YYYY-MM-DD format."
        elif end < start:
            error = "The return date cannot be before the pickup date."
        elif start < date.today():
            error = "The pickup date cannot be in the past."
        else:
            vehicles = search_available(start, end, category)

    if error:
        flash(error)

    return render_template(
        "booking/search.html",
        vehicles=vehicles,
        start=start_raw,
        end=end_raw,
        selected_category=category,
        days=days_between(start, end) if (start and end and end >= start) else None,
    )


@bp.route("/create", methods=("POST",))
@login_required
def create():
    """FR-6 — create a booking, then hand off to the payment step."""
    vehicle_id = request.form.get("vehicle_id", type=int)
    start = parse_date(request.form.get("start"))
    end = parse_date(request.form.get("end"))

    if not vehicle_id or start is None or end is None or end < start:
        flash("Invalid booking details.")
        return redirect(url_for("booking.search"))

    booking_id = create_booking(g.user["id"], vehicle_id, start, end)

    if booking_id is None:
        # FR-16 rejection — no payment row is written
        flash("Sorry, that vehicle is no longer available for those dates.")
        return redirect(url_for("booking.search", start=request.form.get("start"),
                                end=request.form.get("end")))

    return redirect(url_for("payment.checkout", booking_id=booking_id))


@bp.route("/history")
@login_required
def history():
    """FR-10 — a customer views their booking history."""
    bookings = booking_history(g.user["id"])
    return render_template("booking/history.html", bookings=bookings,
                            today=date.today().isoformat())


@bp.route("/<int:booking_id>/cancel", methods=("POST",))
@login_required
def cancel(booking_id):
    """FR-10 — cancel a booking that has not started."""
    ok, message = cancel_booking(booking_id, user_id=g.user["id"])
    flash(message)
    return redirect(url_for("booking.history"))
