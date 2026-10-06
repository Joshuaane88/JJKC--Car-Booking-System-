"""Tests for the FR-16 overlap rule — the system's one hard correctness
requirement. Covers the same-day boundary, maintenance blocks, cancelled
bookings, and the pre-insert re-check.
"""

from datetime import date, timedelta

import pytest

from src import create_app
from src.booking import (
    calculate_cost, check_availability, create_booking,
    create_maintenance_block, days_between,
)
from src.db import get_db, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """A fresh app backed by a throwaway SQLite file per test."""
    db_path = tmp_path / "test.sqlite"
    app = create_app({
        "TESTING": True,
        "DATABASE": str(db_path),
        "SECRET_KEY": "test",
    })

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


def add_booking(start_offset, end_offset, status="confirmed",
                btype="rental", vehicle_id=1, user_id=1):
    """Insert a booking row directly, bypassing the service layer."""
    db = get_db()
    db.execute(
        "INSERT INTO bookings (vehicle_id, user_id, start_date, end_date,"
        " total_cost, status, type, reference) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            vehicle_id, user_id,
            d(start_offset).isoformat(), d(end_offset).isoformat(),
            100.00, status, btype,
            f"TEST-{start_offset}-{end_offset}-{btype}",
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Cost calculation (FR-6)
# --------------------------------------------
