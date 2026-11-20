import logging
from typing import Any, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app import config

logger = logging.getLogger("helpbox.db")

# Create SQLAlchemy engine
# pool_pre_ping tests connections before using them to prevent stale connections
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> Dict[str, Any]:
    """
    Test live PostgreSQL connection and pgvector extension status.
    """
    try:
        with engine.connect() as conn:
            version_row = conn.execute(text("SELECT version();")).fetchone()
            pg_version = version_row[0] if version_row else "Unknown"

            ext_row = conn.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            ).fetchone()

            has_vector = ext_row is not None
            vector_version = ext_row[1] if ext_row else None

            return {
                "connected": True,
                "postgres_version": pg_version,
                "pgvector_active": has_vector,
                "pgvector_version": vector_version,
            }
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return {
            "connected": False,
            "error": str(e),
            "pgvector_active": False,
        }


def init_db():
    """
    Ensure pgvector extension is enabled and create all database tables.
    """
    logger.info("Initializing PostgreSQL schema and pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

    # Import models so SQLAlchemy registers them with Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")
