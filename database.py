import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

engine = None
SessionLocal = None
is_sqlite = DATABASE_URL.startswith("sqlite") if DATABASE_URL else False

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=not is_sqlite,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _run_migrations() -> None:
    """
    Keep DB schema in sync with Alembic migrations.

    Note: SQLAlchemy `create_all()` does not alter existing tables, so it cannot
    add missing columns like `conference_rooms.price_per_day`.
    """
    from alembic import command
    from alembic.config import Config

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao definido")

    repo_root = Path(__file__).resolve().parent
    alembic_ini_path = repo_root / "alembic.ini"
    if not alembic_ini_path.exists():
        return

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


def init_db() -> None:
    import models  # noqa: F401

    if engine is None:
        raise RuntimeError("DATABASE_URL nao definido")

    run_migrations = os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if run_migrations:
        _run_migrations()
    else:
        Base.metadata.create_all(bind=engine)


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL nao definido")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
