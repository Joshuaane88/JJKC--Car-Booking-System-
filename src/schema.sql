-- Car Rental Booking System — SQLite schema
-- Dates are stored as ISO-8601 TEXT ('YYYY-MM-DD') so they sort and compare correctly.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    phone           TEXT,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'customer'
                            CHECK (role IN ('customer', 'admin')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vehicles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    make            TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    category        TEXT    NOT NULL
                            CHECK (category IN ('economy', 'sedan', 'suv', 'truck')),
    daily_rate      REAL    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'available'
                            CHECK (status IN ('available', 'rented', 'out_of_service')),
    photo_url       TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      INTEGER NOT NULL,
    user_id         INTEGER,                       -- NULL for maintenance rows (FR-13)
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    total_cost      REAL,                          -- NULL for maintenance rows
    status          TEXT    NOT NULL DEFAULT 'confirmed'
                            CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    type            TEXT    NOT NULL DEFAULT 'rental'
                            CHECK (type IN ('rental', 'maintenance')),
    reference       TEXT    UNIQUE,                -- NULL for maintenance rows
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id),
    FOREIGN KEY (user_id)    REFERENCES users(id),

    CHECK (end_date >= start_date)
);

-- Speeds up the overlap query that enforces FR-16
CREATE INDEX IF NOT EXISTS idx_bookings_vehicle_dates
    ON bookings (vehicle_id, start_date, end_date);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INTEGER NOT NULL,
    amount          REAL    NOT NULL,
    paycode         TEXT    NOT NULL,              -- simulated payment code, no real card data
    status          TEXT    NOT NULL DEFAULT 'paid'
                            CHECK (status IN ('paid', 'refunded', 'failed')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);
