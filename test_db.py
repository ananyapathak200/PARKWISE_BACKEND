from sqlalchemy import create_engine, text

URL = "postgresql://postgres.xpxicfxbevygmmhidjkn:Parkwise2006project@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
engine = create_engine(URL)

with engine.connect() as conn:
    print(conn.execute(text("select 1")).scalar())