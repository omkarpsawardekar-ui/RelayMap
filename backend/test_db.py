
from app.db.session import check_database_connection

try:
    check_database_connection()
    print("SUCCESS: Connected to RelayMap PostgreSQL database!")
except Exception as e:
    print("DATABASE CONNECTION FAILED:")
    print(e)
