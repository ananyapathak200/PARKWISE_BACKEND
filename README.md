# ParkWise — Backend

FastAPI + PostgreSQL. Matches the frontend's `js/api.js` exactly.

## What's here

```
backend/
├── main.py               FastAPI app, wires up all routers, /health
├── database.py            SQLAlchemy engine + session (reads DATABASE_URL from .env)
├── models.py               ORM tables: User, ParkingArea, ParkingSlot, Booking, Review
├── schemas.py               Pydantic request/response shapes
├── auth.py                   Password hashing + JWT create/verify
├── dependencies.py            get_current_user, require_role(...)
├── routers/
│   ├── users.py                POST /auth/signup, /auth/login, GET /auth/me
│   ├── parking_areas.py        Listings: create, search (with score), mine, get, update
│   ├── bookings.py             Book, check-in, check-out — includes overlap prevention
│   └── admin.py                Approve/reject listings, stats
├── utils/
│   ├── qr.py                    QR token generation
│   └── scoring.py                Haversine distance + suitability score
├── test_flow.py                An end-to-end smoke test (not part of the app — see below)
├── requirements.txt
└── .env.example
```

## Setup

1. **Create a virtual environment and install dependencies:**
   ```
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set up PostgreSQL:**
   - Install PostgreSQL if you haven't already
   - Create a database: `createdb parkwise` (or via pgAdmin)

3. **Configure environment variables:**
   ```
   cp .env.example .env
   ```
   Edit `.env` and set your real `DATABASE_URL` and a random `JWT_SECRET_KEY`.

4. **Run the server:**
   ```
   uvicorn main:app --reload
   ```
   Tables are created automatically on first run (`Base.metadata.create_all`).

5. **Visit `http://127.0.0.1:8000/docs`** — every endpoint is listed and
   testable right there, including auth. Click "Authorize" and paste
   `Bearer <your_token>` after logging in to test protected routes.

## Verifying it works (optional but recommended)

`test_flow.py` is a self-contained smoke test that runs the *entire*
real flow — signup, role checks, listing creation, admin approval,
search with scoring, booking, **double-booking rejection**, check-in,
check-out, and bill calculation — using a temporary SQLite database so
it needs zero setup:

```
python test_flow.py
```

If everything passes, your core logic is solid before you even touch
the frontend. This file is not part of the actual app — delete it once
you've reviewed it, or keep it as a regression check whenever you
change `bookings.py`.

## Connecting the frontend

In `frontend/js/api.js`, `API_BASE_URL` should already point to
`http://127.0.0.1:8000`. Uncomment the fetch calls in each `api.js`
function to match the endpoints above — the shapes already match what
the backend expects and returns.

## What's deliberately not built yet

Matches the "what to skip" section of the roadmap:
- No real payment gateway (bill is calculated, not charged)
- No camera QR scanning (token is generated and displayed; scanning is
  a frontend concern using any JS QR library)
- Reviews (`Review` model exists, but no router yet — add
  `routers/reviews.py` following the same pattern as the others)
