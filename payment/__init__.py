"""Payment blueprint — FR-7 (simulated payment), FR-8 (on-screen confirmation),
FR-9 (confirmation email).

Payment is SIMULATED. No real card data is collected, transmitted, or stored
at any point — see the assumptions section of the SRS. PaymentService is kept
as a boundary class with a single method so a real gateway could be swapped
in later without touching BookingService.
"""

import secrets

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, url_for
)

from ..auth import login_required
from ..booking import get_booking
from ..db import get_db

bp = Blueprint("payment", __name__, url_prefix="/payment")


# ---------------------------------------------------------------------------
# PaymentService — boundary class, one method
# ---------------------------------------------------------------------------

def generate_paycode():
    """Simulated transaction identifier. Stands in for a gateway's charge id."""
    return "SIM-" + secrets.token_hex(6).upper()


def process_payment(booking_id, amount):
    """PaymentService.processPayment() — FR-7.

    Records a simulated payment against a booking and returns the new
    Payment row. No external gateway is contacted and no card data is handled.

    Returns None if a payment already exists for this booking, so a booking
    cannot be paid for twice.
    """
    db = get_db()

    existing = db.execute(
        "SELECT id FROM payments WHERE booking_id = ? AND status = 'paid'",
        (booking_id,),
    ).fetchone()

    if existing is not None:
        return None

    cursor = db.execute(
        "INSERT INTO payments (booking_id, amount, paycode, status)"
        " VALUES (?, ?, ?, 'paid')",
        (booking_id, amount, generate_paycode()),
    )
    db.commit()

    return db.execute(
        "SELECT * FROM payments WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def get_payment_for_booking(booking_id):
    """Return the paid Payment row for a booking, or None."""
    db = get_db()
    return db.execute(
        "SELECT * FROM payments WHERE booking_id = ? AND status = 'paid'",
        (booking_id,),
    ).fetchone()


# ---------------------------------------------------------------------------
# NotificationService — FR-9
# ---------------------------------------------------------------------------

def send_confirmation(booking, user):
    """NotificationService.sendConfirmation() — FR-9.

    Sends the booking reference to the customer by email. In the prototype
    this writes to the application log rather than dispatching real mail;
    the call site and signature stay the same, so a real mail backend can be
    substituted without changing the booking or payment flow.
    """
    message = (
        f"Booking confirmed.\n"
        f"Reference: {booking['reference']}\n"
        f"Vehicle: {booking['year']} {booking['make']} {booking['model']}\n"
        f"Dates: {booking['start_date']} to {booking['end_date']}\n"
        f"Total: ${booking['total_cost']:.2f}"
    )

    current_app.logger.info(
        "[EMAIL -> %s]\n%s", user["email"], message
    )

    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/<int:booking_id>/checkout")
@login_required
def checkout(booking_id):
    """Show the payment step for a booking the customer just created."""
    booking = get_booking(booking_id)

    if booking is None:
        abort(404)

    if booking["user_id"] != g.user["id"]:
        abort(403)

    # Already paid — jump straight to the confirmation
    if get_payment_for_booking(booking_id) is not None:
        return redirect(url_for("payment.confirmation", booking_id=booking_id))

    return render_template("payment/checkout.html", booking=booking)


@bp.route("/<int:booking_id>/pay", methods=("POST",))
@login_required
def pay(booking_id):
    """FR-7 — complete the (simulated) payment, then confirm."""
    booking = get_booking(booking_id)

    if booking is None:
        abort(404)

    if booking["user_id"] != g.user["id"]:
        abort(403)

    if booking["status"] != "confirmed":
        flash("That booking is no longer active.")
        return redirect(url_for("booking.history"))

    payment = process_payment(booking_id, booking["total_cost"])

    if payment is None:
        flash("This booking has already been paid for.")
        return redirect(url_for("payment.confirmation", booking_id=booking_id))

    # FR-9 — email the booking reference
    send_confirmation(booking, g.user)

    return redirect(url_for("payment.confirmation", booking_id=booking_id))


@bp.route("/<int:booking_id>/confirmation")
@login_required
def confirmation(booking_id):
    """FR-8 — on-screen confirmation showing the booking reference."""
    booking = get_booking(booking_id)

    if booking is None:
        abort(404)

    if booking["user_id"] != g.user["id"]:
        abort(403)

    payment = get_payment_for_booking(booking_id)

    if payment is None:
        return redirect(url_for("payment.checkout", booking_id=booking_id))

    return render_template(
        "payment/confirmation.html", booking=booking, payment=payment
    )
