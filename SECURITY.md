# ParkWise security check — 12 Nov 2026

All 15 items were checked across the backend (FastAPI) and the frontend.
`python test_security.py` runs 47 attack checks against the backend; all pass.
`python test_flow.py` (the end-to-end booking flow) also passes.

## Results

| # | Item | Before | Now |
|---|------|--------|-----|
| 1 | Hide API keys | Keys already in `.env`; JWT secret silently fell back to a hard-coded default | All settings read in one place (`config.py`); missing keys stop the server; weak JWT secret refused in production; `.env.example` added |
| 2 | Passwords off GitHub | `.env` never committed (checked full git history); a user's uploaded photo was committed | `uploads/`, databases and backups added to `.gitignore`; the committed photo is untracked |
| 3 | Lock the admin page | **Anyone could sign up as `admin`** | Signup accepts only driver/owner; admins are made with `python create_admin.py` on the server; all `/admin/*` routes check the role from the database |
| 4 | Proper login | Email case-sensitive; outdated `python-jose` | Case-insensitive email; PyJWT with required expiry; forged, unsigned and expired tokens rejected; same response time for unknown emails |
| 5 | Users see only their data | Pending/rejected listings and their reviews visible to anyone with the id; bookings possible on unapproved listings | Pending listings visible only to owner/admin; bookings only on approved listings; someone else's booking returns "not found" |
| 6 | Check every form | Few limits; photo type trusted from the browser, extension from the uploaded filename | Every field has length/format/range limits (backend and HTML); photos checked by their real bytes and renamed by the server; 5 MB read cap; booking dates sanity-checked; old photos deleted when replaced |
| 7 | Stop login spam | No limits | 5 wrong passwords per account per 15 min; 30 logins per IP per 15 min; 5 signups per IP per hour; reset emails 3 per address per hour; bookings, address lookups limited |
| 8 | HTTPS everywhere | Frontend hard-coded to `http://127.0.0.1:9000` | Frontend uses `https://api.<domain>` automatically when live; API sends HSTS in production; CORS limited to your own site; Nginx + Let's Encrypt (see deployment roadmap) |
| 9 | Hash passwords | Passwords bcrypt-hashed ✔; reset tokens stored in plain text | Reset tokens stored as SHA-256 hashes too |
| 10 | Lock the database | App connects as the `postgres` superuser | SQLAlchemy only (no raw SQL, so no SQL injection); **do the steps below to switch to a limited user** |
| 11 | Debug mode | `/docs` always on; `print()` logging of email addresses | `ENVIRONMENT=production` turns off `/docs`, `/redoc`, `/openapi.json`; proper logging without personal data |
| 12 | Error details | Crashes and 422 errors could echo internals and typed passwords | Generic 500 message (details only in the server log); 422 errors list only field + reason; Razorpay outages give a clear 502 |
| 13 | Update packages | Unpinned `>=` versions; `python-jose` + `ecdsa` (known timing weakness) | Exact versions pinned; PyJWT replaces python-jose; gunicorn added for the VPS |
| 14 | Full security check | — | This report + `test_security.py` (47 checks) |
| 15 | Unused code | Unused imports; `test_flow.py` broken | Unused imports removed; `test_flow.py` fixed; frontend has no unused JS/CSS files or functions |

## You need to do these (5 minutes)

1. **Install the updated packages** (in the backend folder, venv active):

   ```
   pip install -r requirements.txt
   pip uninstall -y python-jose ecdsa rsa pyasn1 passlib
   ```

2. **Make your admin account** (sign-up can no longer create one):

   ```
   python create_admin.py
   ```

3. **Lock the database** — create a limited user for the app instead of `postgres`. In `psql -U postgres`:

   ```sql
   CREATE USER parkwise_app WITH PASSWORD 'a-long-random-password';
   ALTER DATABASE parkwise OWNER TO parkwise_app;
   \c parkwise
   REASSIGN OWNED BY postgres TO parkwise_app;  -- only if tables were created as postgres
   ```

   Then set `DATABASE_URL=postgresql+psycopg://parkwise_app:<password>@localhost:5432/parkwise` in `.env`.
   On the VPS, keep PostgreSQL listening on `localhost` only (the default) and never open port 5432 in the firewall.

4. **Production `.env`** on the VPS: `ENVIRONMENT=production`, a new `JWT_SECRET_KEY`
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`), Razorpay **live** keys,
   `CORS_ORIGINS=https://parkwise.in,https://www.parkwise.in`,
   `FRONTEND_RESET_URL=https://parkwise.in/reset-password.html`, `UPLOAD_DIR=/home/parkwise/uploads`.

5. **Commit** the changes (`git add -A && git commit -m "Security hardening"`) — `.env` stays out automatically.

## Known limits (not security holes, worth fixing later)

- Booking times are stored as the driver's local time, while check-in/out use UTC. Works in one time zone (India); move everything to UTC before going multi-region.
- The edit-listing form lets owners change the slot count, but the backend ignores it (slots are fixed at creation).
- Deleting a listing that has past bookings fails, because the bookings still point at its slots. Consider "archive" instead of delete.
- Rate limits live in memory per server process (with `gunicorn -w 2` the real limit is about double). Move to Redis if you add servers.
- Login tokens are kept in the browser's localStorage. That is safe as long as no page inserts unescaped text; every page currently escapes user text. A Content-Security-Policy header in Nginx would add a second layer.
