from database import engine
from sqlalchemy import text

conn = engine.connect()
result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
tables = [r[0] for r in result]
conn.close()

if tables:
    print("Tables found:", tables)
else:
    print("No tables found - DB may not be connected or startup didnt run")
