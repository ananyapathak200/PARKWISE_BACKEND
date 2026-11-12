"""
Database connection setup for ParkWise.

Creates the SQLAlchemy engine (talks to PostgreSQL) and a session
factory (one session per request, closed automatically afterwards).
All queries go through SQLAlchemy, which always sends values as
parameters — never pasted into the SQL text — so SQL injection is not
possible through the ORM. Don't add raw string-built SQL.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

# connect_args is only needed for SQLite (used in local testing).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_pre_ping drops dead connections (e.g. after a database restart)
# instead of failing the next request with a confusing error.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency — yields a DB session per request and closes it
    afterwards, even if the request raises an error.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
