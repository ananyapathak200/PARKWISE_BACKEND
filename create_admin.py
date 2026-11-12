"""
create_admin.py — the ONLY way to make an admin account.

Signup on the website can create drivers and owners only, so nobody can
make themselves an admin from the browser. Run this on the server:

    python create_admin.py

It asks for the details (the password is not shown while you type).
If the email already has an account, that account is promoted to admin.
"""

import getpass
import sys

from pydantic import TypeAdapter, ValidationError

import auth as auth_utils
import models
import schemas
from database import Base, SessionLocal, engine


def main() -> int:
    Base.metadata.create_all(bind=engine)
    email = input("Admin email: ").strip().lower()
    try:
        TypeAdapter(schemas.EmailStr).validate_python(email)
    except ValidationError:
        print("That doesn't look like a valid email.")
        return 1

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            if input(f"{email} already exists as '{user.role}'. Make it an admin? [y/N] ").strip().lower() != "y":
                return 1
            user.role = "admin"
        else:
            name = input("Full name: ").strip()
            phone = input("Phone: ").strip()
            password = getpass.getpass("Password (min 12 characters): ")
            if len(password) < 12 or password != getpass.getpass("Repeat password: "):
                print("Passwords must match and be at least 12 characters.")
                return 1
            user = models.User(
                name=name or "Admin",
                email=email,
                phone=phone or "0000000",
                password_hash=auth_utils.hash_password(password),
                role="admin",
            )
            db.add(user)
        db.commit()
        print(f"Done: {email} is an admin.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
