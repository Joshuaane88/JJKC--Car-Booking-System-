"""Tests for the FR-16 overlap rule — the system's one hard correctness
requirement. Covers the same-day boundary, maintenance blocks, cancelled
bookings, and the pre-insert re-check.
"""

from datetime import date, timedelta

import pytest

from src import create_app
from src.booking import (
    calculate_cost,
    check_availability,
    create_booking,
    create_maintenance_block,
    days_between,
)
from src.db import get_db, init_db


@pytest.fixture
def app(tmp_path):
    """A fresh app backed by a throwaway SQLite file per test."""
    db_path = tmp_path / "test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(db_path),
            "SECRET_KEY": "test",
        }
    )

    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            "INSERT INTO users (id, name, email, phone, password_hash, role)"
            " VALUES (1, 'Test Customer', 'test@example.test', '000',"
            " 'notarealhash', 'customer')"
        )
        db.execute(
            "INSERT INTO vehicles (id, make, model, year, category,"
            " daily_rate, status) VALUES"
            " (1, 'Toyota', 'Corolla', 2022, 'economy', 40.00, 'available')"
        )
        db.commit()

    return app


def d(offset):
    """A date `offset` days from today."""
    return date.today() + timedelta(days=offset)


def add_booking(
    start_offset,
    end_offset,
    status="confirmed",
    btype="rental",
    vehicle_id=1,
    user_id=1,
):
    """Insert a booking row directly, bypassing the service layer."""
    db = get_db()
    db.execute(
        "INSERT INTO bookings (vehicle_id, user_id, start_date, end_date,"
        " total_cost, status, type, reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            vehicle_id,
            user_id,
            d(start_offset).isoformat(),
            d(end_offset).isoformat(),
            100.00,
            status,
            btype,
            f"TEST-{start_offset}-{end_offset}-{btype}",
        ),
    )
    db.commit()


# --- Cost calculation (FR-6) ---


def test_single_day_rental_counts_as_one_day():
    assert days_between(d(5), d(5)) == 1


def test_days_between_is_inclusive():
    assert days_between(d(10), d(14)) == 5


def test_cost_is_rate_times_days():
    assert calculate_cost(40.00, d(1), d(3)) == 120.00


# --- FR-16: the overlap rule ---


def test_vehicle_is_available_when_no_bookings_exist(app):
    with app.app_context():
        assert check_availability(1, d(1), d(3)) is True


def test_exact_same_range_is_rejected(app):
    with app.app_context():
        add_booking(10, 14)
        assert check_availability(1, d(10), d(14)) is False


def test_range_fully_inside_an_existing_booking_is_rejected(app):
    with app.app_context():
        add_booking(10, 20)
        assert check_availability(1, d(12), d(15)) is False


def test_range_fully_containing_an_existing_booking_is_rejected(app):
    with app.app_context():
        add_booking(12, 15)
        assert check_availability(1, d(10), d(20)) is False


def test_overlap_at_the_start_is_rejected(app):
    with app.app_context():
        add_booking(10, 20)
        assert check_availability(1, d(5), d(12)) is False


def test_overlap_at_the_end_is_rejected(app):
    with app.app_context():
        add_booking(10, 20)
        assert check_availability(1, d(18), d(25)) is False


def test_range_entirely_before_an_existing_booking_is_allowed(app):
    with app.app_context():
        add_booking(10, 20)
        assert check_availability(1, d(1), d(5)) is True


def test_range_entirely_after_an_existing_booking_is_allowed(app):
    with app.app_context():
        add_booking(10, 20)
        assert check_availability(1, d(25), d(30)) is True


# --- The same-day boundary: ranges are INCLUSIVE on both ends ---


def test_new_booking_starting_on_an_existing_end_date_is_rejected(app):
    with app.app_context():
        add_booking(10, 14)
        assert check_availability(1, d(14), d(18)) is False


def test_new_booking_ending_on_an_existing_start_date_is_rejected(app):
    with app.app_context():
        add_booking(10, 14)
        assert check_availability(1, d(6), d(10)) is False


def test_booking_starting_the_day_after_an_existing_end_is_allowed(app):
    with app.app_context():
        add_booking(10, 14)
        assert check_availability(1, d(15), d(18)) is True


def test_booking_ending_the_day_before_an_existing_start_is_allowed(app):
    with app.app_context():
        add_booking(10, 14)
        assert check_availability(1, d(6), d(9)) is True


# --- Status and type handling ---


def test_cancelled_bookings_do_not_block(app):
    with app.app_context():
        add_booking(10, 14, status="cancelled")
        assert check_availability(1, d(10), d(14)) is True


def test_completed_bookings_do_not_block(app):
    with app.app_context():
        add_booking(10, 14, status="completed")
        assert check_availability(1, d(10), d(14)) is True


def test_maintenance_block_prevents_customer_booking(app):
    """FR-13 shares the bookings table, so one overlap query covers both."""
    with app.app_context():
        add_booking(10, 14, btype="maintenance", user_id=None)
        assert check_availability(1, d(11), d(13)) is False


def test_booking_on_another_vehicle_does_not_block_this_one(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO vehicles (id, make, model, year, category,"
            " daily_rate, status) VALUES"
            " (2, 'Honda', 'Civic', 2023, 'economy', 42.00, 'available')"
        )
        db.commit()
        add_booking(10, 14, vehicle_id=2)
        assert check_availability(1, d(10), d(14)) is True


# --- createBooking: the pre-insert re-check ---


def test_create_booking_succeeds_when_available(app):
    with app.app_context():
        assert create_booking(1, 1, d(10), d(14)) is not None


def test_create_booking_returns_none_on_conflict(app):
    with app.app_context():
        assert create_booking(1, 1, d(10), d(14)) is not None
        assert create_booking(1, 1, d(12), d(16)) is None


def test_no_payment_row_exists_for_a_rejected_booking(app):
    with app.app_context():
        create_booking(1, 1, d(10), d(14))
        create_booking(1, 1, d(12), d(16))  # rejected
        count = get_db().execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
        assert count == 0


def test_create_booking_sets_cost_from_rate_times_days(app):
    with app.app_context():
        booking_id = create_booking(1, 1, d(10), d(14))
        row = (
            get_db()
            .execute("SELECT total_cost FROM bookings WHERE id = ?", (booking_id,))
            .fetchone()
        )
        assert row["total_cost"] == 200.00


def test_create_booking_generates_a_reference(app):
    with app.app_context():
        booking_id = create_booking(1, 1, d(10), d(14))
        row = (
            get_db()
            .execute("SELECT reference FROM bookings WHERE id = ?", (booking_id,))
            .fetchone()
        )
        assert row["reference"].startswith("CR-")


def test_out_of_service_vehicle_cannot_be_booked(app):
    """FR-12 blocks new bookings outright, independent of date logic."""
    with app.app_context():
        get_db().execute("UPDATE vehicles SET status = 'out_of_service' WHERE id = 1")
        get_db().commit()
        assert create_booking(1, 1, d(10), d(14)) is None


# --- Maintenance blocks go through BookingService (single-writer rule) ---


def test_maintenance_block_is_created_with_no_customer(app):
    with app.app_context():
        block_id = create_maintenance_block(1, d(10), d(14))
        row = (
            get_db()
            .execute("SELECT * FROM bookings WHERE id = ?", (block_id,))
            .fetchone()
        )
        assert row["type"] == "maintenance"
        assert row["user_id"] is None
        assert row["total_cost"] is None
        assert row["reference"] is None


def test_maintenance_block_is_rejected_when_it_overlaps_a_booking(app):
    with app.app_context():
        add_booking(10, 14)
        assert create_maintenance_block(1, d(12), d(16)) is None
