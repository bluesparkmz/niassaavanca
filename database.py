import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Comentario: usa DATABASE_URL do ambiente (PostgreSQL recomendado).
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL nao definido")

is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # Comentario: pool configuravel para producao.
    pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    # Comentario: garante schema minimo quando o banco sobe vazio.
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    # Comentario: dependency do FastAPI para abrir/fechar sessoes do banco.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
