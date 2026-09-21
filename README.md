# Car Rental Booking System

A web-based car rental booking platform built for a single local car dealership that owns and rents out its own fleet. Customers can browse available vehicles, select a rental date range, and book online; dealership staff manage the fleet, bookings, and vehicle availability through an admin interface.

Course project for ** CIS 453 — Software Spec. and Design **.

## Team — JJKC

- Joshua Ane
- Jae Nicasio
- Chisimdi Ikeanusi
- Kwadwo Adubofour

## Technology Stack

| Layer | Choice |
|---|---|
| Language | Python 3 |
| Framework | Flask |
| Database | SQLite |
| Views | Jinja2 (server-rendered HTML) |
| Auth | Flask sessions, Werkzeug password hashing |
| Testing | pytest |

## Repository Structure

```
/src      — Flask application, one folder per blueprint
/docs     — SRS, Software Specification, architecture and UML diagrams
/tests    — pytest test suite
```

## Setup

```bash
# clone the repo
git clone <https://github.com/Joshuaane88/JJKC--Car-Booking-System-.git>
cd car-rental-booking-system

# create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# install dependencies
pip install -r requirements.txt
```

## Running the Application

```bash
flask --app src run
```

## Running Tests

```bash
pytest
```

## Branch Convention

- `main` is protected — no direct pushes.
- Work happens on feature branches named `feature/<short-description>` (e.g., `feature/booking-overlap-check`).
- Changes reach `main` through a pull request.

## Key Design Decision — Availability

Vehicle availability is **derived from the Bookings table** rather than stored in a separate availability calendar. A vehicle is available for a requested date range if no confirmed booking for that vehicle overlaps the range. This avoids keeping a second source of truth in sync with actual bookings.

Maintenance blocks are stored as Booking rows with `type = maintenance` and no associated customer, so a single overlap query covers both customer bookings and maintenance windows.

`BookingService` is the only class permitted to write Booking rows — including maintenance blocks, which `AdminService` creates by calling into `BookingService` rather than writing the table directly. This keeps the overlap check from being bypassed.

## Documentation

Full requirements and design documentation is in [`/docs`](./docs):

- Software Requirements Specification (SRS)
- Software Specification — Week 2 Design Addendum
- High-level architecture diagram
- UML class diagram and sequence diagrams
