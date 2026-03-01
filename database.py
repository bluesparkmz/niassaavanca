import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Comentario: usa DATABASE_URL do ambiente (PostgreSQL recomendado).
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL nao definido")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    # Comentario: dependency do FastAPI para abrir/fechar sessoes do banco.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
