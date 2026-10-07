"""Seed the database with sample data so the app is demoable rather than empty.

Usage:
    python seed.py

Creates ~12 vehicles across all four categories, one admin account, one
customer account, and a couple of bookings (including a maintenance block)
so the availability logic has something to work against.
"""

from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from src import create_app
from src.db import get_db, init_db

VEHICLES = [
    # (make, model, year, category, daily_rate, photo_url)
    ("Toyota", "Corolla", 2022, "economy", 38.00, "img/corolla.webp"),
    ("Honda", "Civic", 2023, "economy", 42.00, "img/Honda_civic.webp"),
    ("Nissan", "Versa", 2021, "economy", 34.50, "img/versa.webp"),
    ("Toyota", "Camry", 2023, "sedan", 58.00, "img/camry.webp"),
    ("Honda", "Accord", 2022, "sedan", 55.00, "img/accord.webp"),
    ("Mazda", "Mazda6", 2023, "sedan", 61.00, "img/mazda.webp"),
    ("Toyota", "RAV4", 2023, "suv", 72.00, "img/rav4.jpg"),
    ("Honda", "CR-V", 2022, "suv", 70.00, "img/crv.webp"),
    ("Jeep", "Grand Cherokee", 2023, "suv", 89.00, "img/cherokee.jpg"),
    ("Subaru", "Outback", 2022, "suv", 75.00, "img/subaru.png"),
    ("Ford", "F-150", 2023, "truck", 95.00, "img/F-150.webp"),
    ("Chevrolet", "Silverado", 2022, "truck", 92.00, "img/chevrolet.jpg"),
    ("Toyota", "Tacoma", 2023, "truck", 84.00, "img/taycoma.jpg"),
]
USERS = [
    # (name, email, phone, password, role)
    ("Dealership Admin", "admin@carrental.test", "315-555-0100", "admin123", "admin"),
    ("Jordan Reyes", "jordan@example.test", "315-555-0142", "customer123", "customer"),
    ("Sam Okafor", "sam@example.test", "315-555-0188", "customer123", "customer"),
]


def seed():
    app = create_app()

    with app.app_context():
        # Fresh start — drop and recreate every table
        db = get_db()
        for table in ("payments", "bookings", "vehicles", "users"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
        db.commit()

        init_db()
        db = get_db()

        # --- Users ---
        for name, email, phone, password, role in USERS:
            db.execute(
                "INSERT INTO users (name, email, phone, password_hash, role)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, email, phone, generate_password_hash(password), role),
            )

        # --- Vehicles ---
        for make, model, year, category, rate, photo in VEHICLES:
            db.execute(
                "INSERT INTO vehicles (make, model, year, category, daily_rate,"
                " status, photo_url) VALUES (?, ?, ?, ?, ?, 'available', ?)",
                (make, model, year, category, rate, photo),
            )

        db.commit()

        # --- Sample bookings, so availability search has something to exclude ---
        today = date.today()

        def iso(days_from_now):
            return (today + timedelta(days=days_from_now)).isoformat()

        # A confirmed customer rental on vehicle 1 (Corolla), next week
        db.execute(
            "INSERT INTO bookings (vehicle_id, user_id, start_date, end_date,"
            " total_cost, status, type, reference)"
            " VALUES (1, 2, ?, ?, ?, 'confirmed', 'rental', 'CR-SEED0001')",
            (iso(7), iso(10), 38.00 * 4),
        )

        # A confirmed rental on vehicle 7 (RAV4), starting in three days
        db.execute(
            "INSERT INTO bookings (vehicle_id, user_id, start_date, end_date,"
            " total_cost, status, type, reference)"
            " VALUES (7, 3, ?, ?, ?, 'confirmed', 'rental', 'CR-SEED0002')",
            (iso(3), iso(5), 72.00 * 3),
        )

        # A maintenance block on vehicle 11 (F-150) — no customer, no cost,
        # no reference. Proves FR-13 shares the bookings table.
        db.execute(
            "INSERT INTO bookings (vehicle_id, user_id, start_date, end_date,"
            " total_cost, status, type, reference)"
            " VALUES (11, NULL, ?, ?, NULL, 'confirmed', 'maintenance', NULL)",
            (iso(2), iso(9)),
        )

        # One vehicle parked out of service outright (FR-12)
        db.execute("UPDATE vehicles SET status = 'out_of_service' WHERE id = 4")

        db.commit()

        print(f"Seeded {len(USERS)} users and {len(VEHICLES)} vehicles.")
        print("  Admin:    admin@carrental.test / admin123")
        print("  Customer: jordan@example.test / customer123")
        print(f"  Corolla booked {iso(7)} to {iso(10)}")
        print(f"  RAV4 booked {iso(3)} to {iso(5)}")
        print(f"  F-150 in maintenance {iso(2)} to {iso(9)}")
        print("  Camry (id 4) is out of service")


if __name__ == "__main__":
    seed()
