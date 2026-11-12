"""
test_security.py — checks that the security fixes keep working.

Runs on a throwaway SQLite database with fake keys, so it needs no
PostgreSQL, Razorpay or email setup:

    python test_security.py
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="parkwise-test-")
os.environ.update({
    "ENVIRONMENT": "development",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "JWT_SECRET_KEY": "test-only-secret-that-is-long-enough-1234567890",
    "RAZORPAY_KEY_ID": "rzp_test_dummy",
    "RAZORPAY_KEY_SECRET": "dummy_secret",
    "SMTP_EMAIL": "",
    "SMTP_APP_PASSWORD": "",
    "UPLOAD_DIR": os.path.join(_tmp, "uploads"),
    "CORS_ORIGINS": "http://localhost:5500",
})

from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from utils import rate_limit  # noqa: E402

client = TestClient(main.app, raise_server_exceptions=False)
results = []


def check(label, condition):
    results.append((label, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'} — {label}")


def reset_limits():
    for name in dir(rate_limit):
        obj = getattr(rate_limit, name)
        if isinstance(obj, rate_limit.RateLimiter):
            obj._events.clear()


def signup(email, role, password="password123", name="Test User"):
    return client.post("/auth/signup", json={"name": name, "email": email, "phone": "9876543210", "password": password, "role": role})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


print("\n--- 3. admin page locked ---")
r = signup("hacker@example.com", "admin")
check("signup as admin is rejected (422)", r.status_code == 422)
driver = signup("Driver@Example.com", "driver").json()["access_token"]
owner = signup("owner@example.com", "owner").json()["access_token"]
owner2 = signup("owner2@example.com", "owner").json()["access_token"]
driver2 = signup("driver2@example.com", "driver").json()["access_token"]
check("driver cannot open admin stats (403)", client.get("/admin/stats", headers=auth(driver)).status_code == 403)
check("no token cannot open admin stats (401)", client.get("/admin/stats").status_code == 401)
db = SessionLocal()
admin_user = models.User(name="Admin", email="admin@example.com", phone="9876543210",
                         password_hash=__import__("auth").hash_password("adminpass123"), role="admin")
db.add(admin_user); db.commit(); db.close()
admin = client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).json()["access_token"]
check("real admin can open admin stats", client.get("/admin/stats", headers=auth(admin)).status_code == 200)

print("\n--- 4. proper login ---")
reset_limits()
check("email is case-insensitive at login", client.post("/auth/login", json={"email": "driver@example.com", "password": "password123"}).status_code == 200)
check("duplicate email with other case is refused", signup("DRIVER@example.com", "driver").status_code == 400)
forged = jwt.encode({"sub": "x", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-key", algorithm="HS256")
check("token signed with another key is refused", client.get("/auth/me", headers=auth(forged)).status_code == 401)
none_alg = jwt.encode({"sub": "x", "exp": 9999999999}, None, algorithm="none") if hasattr(jwt, "encode") else ""
check("unsigned 'alg: none' token is refused", client.get("/auth/me", headers=auth(none_alg)).status_code == 401)
expired = jwt.encode({"sub": "x", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
check("expired token is refused", client.get("/auth/me", headers=auth(expired)).status_code == 401)

print("\n--- 6. every form checked ---")
reset_limits()
check("signup with bad phone refused", signup("p@example.com", "driver").status_code == 200 and client.post("/auth/signup", json={"name": "A B", "email": "q@example.com", "phone": "<script>", "password": "password123", "role": "driver"}).status_code == 422)
check("signup with 7-char password refused", signup("short@example.com", "driver", password="1234567").status_code == 422)
check("signup with 500-char name refused", signup("long@example.com", "driver", name="x" * 500).status_code == 422)
bad_listing = {"name": "Lot", "address": "Sigra, Varanasi", "latitude": 999, "longitude": 82.9, "price_per_hour": -5, "slots": 2}
check("listing with impossible latitude / negative price refused", client.post("/parking-areas", json=bad_listing, headers=auth(owner)).status_code == 422)
r = client.post("/auth/signup", json={"name": "A B", "email": "z@example.com", "phone": "9876543210", "password": "short", "role": "driver"})
check("validation errors don't echo the password back", "short" not in r.text)
listing = {"name": "Sigra Lot", "address": "Sigra, Varanasi", "latitude": 25.31, "longitude": 82.97, "price_per_hour": 30, "slots": 2, "opening_time": "08:00", "closing_time": "22:00"}
check("listing with bad opening time refused", client.post("/parking-areas", json={**listing, "opening_time": "25:99"}, headers=auth(owner)).status_code == 422)
area = client.post("/parking-areas", json=listing, headers=auth(owner)).json()
area_id = area["id"]
check("new listing starts as pending", area["status"] == "pending")
check("owner can't approve own listing via PATCH", client.patch(f"/parking-areas/{area_id}", json={"status": "approved"}, headers=auth(owner)).json()["status"] == "pending")

print("\n--- 5. users see only their data ---")
reset_limits()
check("pending listing hidden from public", client.get(f"/parking-areas/{area_id}").status_code == 404)
check("pending listing hidden from another owner", client.get(f"/parking-areas/{area_id}", headers=auth(owner2)).status_code == 404)
check("pending listing visible to its owner", client.get(f"/parking-areas/{area_id}", headers=auth(owner)).status_code == 200)
check("another owner can't edit it", client.patch(f"/parking-areas/{area_id}", json={"name": "Mine now"}, headers=auth(owner2)).status_code == 403)
check("another owner can't see its slots", client.get(f"/parking-areas/{area_id}/slots", headers=auth(owner2)).status_code == 403)
slot_id = client.get(f"/parking-areas/{area_id}/slots", headers=auth(owner)).json()[0]["id"]
start = datetime.utcnow() + timedelta(hours=1)
booking_body = {"slot_id": slot_id, "vehicle_number": "up65 ab 1234", "start_time": start.isoformat() + "Z", "end_time": (start + timedelta(hours=2)).isoformat() + "Z"}
check("can't book a slot in an unapproved listing", client.post("/bookings", json=booking_body, headers=auth(driver)).status_code == 404)
client.patch(f"/admin/parking-areas/{area_id}/approve", headers=auth(admin))
b = client.post("/bookings", json=booking_body, headers=auth(driver))
check("driver can book once approved", b.status_code == 200)
booking = b.json()
check("vehicle number stored in capitals", booking.get("vehicle_number") == "UP65 AB 1234")
check("another driver can't check in someone else's booking", client.post(f"/bookings/{booking['id']}/checkin", headers=auth(driver2)).status_code == 404)
check("another driver doesn't see it in their list", client.get("/bookings/mine", headers=auth(driver2)).json() == [])
check("owner can't book (drivers only)", client.post("/bookings", json=booking_body, headers=auth(owner)).status_code == 403)
past = {**booking_body, "start_time": (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z", "end_time": (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"}
check("booking in the past refused", client.post("/bookings", json=past, headers=auth(driver2)).status_code == 400)
check("bad vehicle number refused", client.post("/bookings", json={**booking_body, "vehicle_number": "<img src=x>"}, headers=auth(driver2)).status_code == 422)
check("fake payment signature refused", client.post(f"/bookings/{booking['id']}/verify-payment", json={"razorpay_order_id": "x", "razorpay_payment_id": "y", "razorpay_signature": "z"}, headers=auth(driver)).status_code == 400)

print("\n--- 6b. photo upload ---")
html = b"<html><script>alert(1)</script></html>"
r = client.post(f"/parking-areas/{area_id}/photo", files={"file": ("evil.png", html, "image/png")}, headers=auth(owner))
check("web page disguised as .png refused", r.status_code == 400)
png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
r = client.post(f"/parking-areas/{area_id}/photo", files={"file": ("photo.html", png, "text/html")}, headers=auth(owner))
check("real PNG accepted and saved with .png name", r.status_code == 200 and r.json()["image_url"].endswith(".png"))
big = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024 + 10)
check("image over 5 MB refused", client.post(f"/parking-areas/{area_id}/photo", files={"file": ("big.jpg", big, "image/jpeg")}, headers=auth(owner)).status_code == 400)
check("another owner can't change the photo", client.post(f"/parking-areas/{area_id}/photo", files={"file": ("p.png", png, "image/png")}, headers=auth(owner2)).status_code == 403)

print("\n--- 7. login spam stopped ---")
reset_limits()
codes = [client.post("/auth/login", json={"email": "owner@example.com", "password": "wrong-guess"}).status_code for _ in range(7)]
check("5 wrong passwords, then blocked (429)", codes[:5] == [401] * 5 and codes[5] == 429)
check("blocked even with the right password", client.post("/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 429)
check("other accounts still log in", client.post("/auth/login", json={"email": "owner2@example.com", "password": "password123"}).status_code == 200)
reset_limits()
codes = [client.post("/auth/forgot-password", json={"email": "nobody@example.com"}).status_code for _ in range(7)]
check("password-reset requests limited", 429 in codes)
reset_limits()
codes = [signup(f"bulk{i}@example.com", "driver").status_code for i in range(7)]
check("mass signups limited", 429 in codes)
reset_limits()

print("\n--- 9. passwords and reset links hashed ---")
db = SessionLocal()
u = db.query(models.User).filter(models.User.email == "owner2@example.com").first()
check("password stored as bcrypt hash", u.password_hash.startswith("$2") and "password123" not in u.password_hash)
client.post("/auth/forgot-password", json={"email": "owner2@example.com"})
db.refresh(u)
check("reset token stored only as a hash", u.reset_token is not None and len(u.reset_token) == 64)
check("the stored hash itself doesn't work as a reset link", client.post("/auth/reset-password", json={"token": u.reset_token, "new_password": "newpassword1"}).status_code == 400)
db.close()

print("\n--- 8 / 11 / 12. headers, debug, errors ---")
r = client.get("/health")
check("nosniff + frame-deny headers present", r.headers.get("x-content-type-options") == "nosniff" and r.headers.get("x-frame-options") == "DENY")
r = client.get("/health", headers={"Origin": "https://evil.example"})
check("CORS doesn't allow a random website", "access-control-allow-origin" not in r.headers)
r = client.get("/health", headers={"Origin": "http://localhost:5500"})
check("CORS allows your own site", r.headers.get("access-control-allow-origin") == "http://localhost:5500")


@main.app.get("/__boom")
def _boom():
    raise RuntimeError("secret internal detail /home/parkwise/db password=hunter2")


r = client.get("/__boom")
check("crash returns a plain 500 with no internals", r.status_code == 500 and "hunter2" not in r.text and "Traceback" not in r.text)

failed = [label for label, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
raise SystemExit(1 if failed else 0)
