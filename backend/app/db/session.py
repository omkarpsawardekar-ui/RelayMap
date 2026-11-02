from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


def get_db():
    db: Session = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def check_database_connection():

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))