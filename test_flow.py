"""
Quick end-to-end smoke test using SQLite (so it runs with zero setup)
and FastAPI's TestClient. This is NOT part of the app — it's just to
prove the logic actually works before handing the code off.
"""

import os

# Use SQLite for this test run only, so it works without a real
# PostgreSQL server. Production still uses the .env DATABASE_URL.
os.environ["DATABASE_URL"] = "sqlite:///./test_parkwise.db"
os.environ["JWT_SECRET_KEY"] = "test-secret"

if os.path.exists("test_parkwise.db"):
    os.remove("test_parkwise.db")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'} — {label}")
    assert condition, label


print("\n--- health check ---")
r = client.get("/health")
check("health endpoint returns ok", r.status_code == 200 and r.json()["status"] == "ok")

print("\n--- signup: driver, owner, admin ---")
driver = client.post("/auth/signup", json={
    "name": "Priya Sharma", "email": "priya@example.com", "phone": "9876500001",
    "password": "password123", "role": "driver"
}).json()
check("driver signup returns token", "access_token" in driver)
driver_token = driver["access_token"]

owner = client.post("/auth/signup", json={
    "name": "Ramesh Owner", "email": "ramesh@example.com", "phone": "9876500002",
    "password": "password123", "role": "owner"
}).json()
owner_token = owner["access_token"]

admin = client.post("/auth/signup", json={
    "name": "Admin User", "email": "admin@example.com", "phone": "9876500003",
    "password": "password123", "role": "admin"
}).json()
admin_token = admin["access_token"]
check("owner and admin signup work", "access_token" in owner and "access_token" in admin)

print("\n--- login ---")
login_r = client.post("/auth/login", json={"email": "priya@example.com", "password": "password123"})
check("login succeeds with correct password", login_r.status_code == 200)

bad_login = client.post("/auth/login", json={"email": "priya@example.com", "password": "wrong"})
check("login rejects wrong password", bad_login.status_code == 401)

print("\n--- owner creates a listing ---")
owner_headers = {"Authorization": f"Bearer {owner_token}"}
listing = client.post("/parking-areas", headers=owner_headers, json={
    "name": "Shastri Nagar Parking", "address": "Sigra, Varanasi",
    "latitude": 25.3061, "longitude": 82.9739,
    "price_per_hour": 20, "slots": 3,
    "opening_time": "20:00", "closing_time": "08:00"
}).json()
check("listing created with status pending", listing["status"] == "pending")
check("listing has 3 total slots", listing["total_slots"] == 3)
listing_id = listing["id"]

print("\n--- driver can't create a listing (role check) ---")
forbidden = client.post("/parking-areas", headers={"Authorization": f"Bearer {driver_token}"}, json={
    "name": "x", "address": "x", "latitude": 0, "longitude": 0, "price_per_hour": 1, "slots": 1
})
check("driver is blocked from creating listings (403)", forbidden.status_code == 403)

print("\n--- pending listing invisible in public search ---")
search_before = client.get("/parking-areas").json()
check("unapproved listing hidden from search", all(l["id"] != listing_id for l in search_before))

print("\n--- admin approves the listing ---")
admin_headers = {"Authorization": f"Bearer {admin_token}"}
approve_r = client.patch(f"/admin/parking-areas/{listing_id}/approve", headers=admin_headers)
check("approve endpoint works", approve_r.status_code == 200 and approve_r.json()["status"] == "approved")

print("\n--- now visible in search, with distance + score when lat/lng given ---")
search_after = client.get("/parking-areas", params={"lat": 25.3176, "lng": 82.9739}).json()
match = next((l for l in search_after if l["id"] == listing_id), None)
check("approved listing now appears in search", match is not None)
check("search returns a real distance_km", match["distance_km"] is not None and match["distance_km"] > 0)
check("search returns a suitability score", match["score"] is not None and 0 <= match["score"] <= 100)

print("\n--- driver books a slot ---")
listing_detail = client.get(f"/parking-areas/{listing_id}").json()
slot_id = None
# fetch a real slot id via the DB directly through the app's session for this test
from database import SessionLocal
import models
db = SessionLocal()
slot = db.query(models.ParkingSlot).filter(models.ParkingSlot.parking_area_id == listing_id).first()
slot_id = slot.id
db.close()

driver_headers = {"Authorization": f"Bearer {driver_token}"}
booking = client.post("/bookings", headers=driver_headers, json={
    "slot_id": slot_id, "vehicle_number": "UP65AB1234",
    "start_time": "2026-08-25T18:00:00", "end_time": "2026-08-25T20:00:00"
}).json()
check("booking created with status reserved", booking["status"] == "reserved")
check("booking has a QR token", booking["qr_code_token"].startswith("PW-"))
booking_id = booking["id"]

print("\n--- double-booking the same slot/time is rejected ---")
conflict = client.post("/bookings", headers=driver_headers, json={
    "slot_id": slot_id, "vehicle_number": "UP65XY9999",
    "start_time": "2026-08-25T18:30:00", "end_time": "2026-08-25T19:30:00"
})
check("overlapping booking rejected with 409", conflict.status_code == 409)

print("\n--- non-overlapping time on same slot succeeds ---")
non_overlap = client.post("/bookings", headers=driver_headers, json={
    "slot_id": slot_id, "vehicle_number": "UP65AB1234",
    "start_time": "2026-08-25T21:00:00", "end_time": "2026-08-25T22:00:00"
})
check("non-overlapping booking on same slot succeeds", non_overlap.status_code == 200)

print("\n--- check in ---")
checkin = client.post(f"/bookings/{booking_id}/checkin", headers=driver_headers)
check("check-in succeeds", checkin.status_code == 200 and checkin.json()["status"] == "checked_in")

print("\n--- check out and bill calculation ---")
checkout = client.post(f"/bookings/{booking_id}/checkout", headers=driver_headers)
checkout_data = checkout.json()
check("check-out succeeds", checkout.status_code == 200 and checkout_data["status"] == "completed")
check("amount was calculated", checkout_data["amount"] is not None and checkout_data["amount"] > 0)
print(f"     billed amount: Rs.{checkout_data['amount']} (minimum 15-min grace period applied since checkout was instant)")

print("\n--- booking history ---")
history = client.get("/bookings/mine", headers=driver_headers).json()
check("booking history returns bookings", len(history) >= 2)

print("\n--- admin stats reflect real activity ---")
stats = client.get("/admin/stats", headers=admin_headers).json()
check("stats show 1 approved listing", stats["approved"] == 1)
check("stats show revenue collected", stats["revenue"] > 0)
print(f"     stats: {stats}")

print("\nALL CHECKS PASSED — the full flow works end to end.\n")
