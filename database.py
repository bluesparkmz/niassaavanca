import os

from sqlalchemy import create_engine, inspect, text
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


def _ensure_users_columns() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    statements: list[str] = []

    def add_column(column_name: str, sqlite_sql: str, postgres_sql: str) -> None:
        if column_name not in user_columns:
            statements.append(sqlite_sql if is_sqlite else postgres_sql)

    add_column(
        "avatar",
        "ALTER TABLE users ADD COLUMN avatar VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(255)",
    )
    add_column(
        "email",
        "ALTER TABLE users ADD COLUMN email VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(120)",
    )
    add_column(
        "phone",
        "ALTER TABLE users ADD COLUMN phone VARCHAR(30)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)",
    )
    add_column(
        "sex",
        "ALTER TABLE users ADD COLUMN sex VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sex VARCHAR(20)",
    )
    add_column(
        "birth_date",
        "ALTER TABLE users ADD COLUMN birth_date DATE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE",
    )
    add_column(
        "expo_push_token",
        "ALTER TABLE users ADD COLUMN expo_push_token VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS expo_push_token VARCHAR(255)",
    )
    add_column(
        "is_admin",
        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
    )
    add_column(
        "created_at",
        "ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        if not is_sqlite:
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
            )
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)")
            )


def _ensure_posts_columns() -> None:
    inspector = inspect(engine)
    if "posts" not in inspector.get_table_names():
        return

    post_columns = {col["name"] for col in inspector.get_columns("posts")}
    statements: list[str] = []

    def add_column(column_name: str, sqlite_sql: str, postgres_sql: str) -> None:
        if column_name not in post_columns:
            statements.append(sqlite_sql if is_sqlite else postgres_sql)

    add_column(
        "status",
        "ALTER TABLE posts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'draft'",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        if not is_sqlite:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_posts_status ON posts (status)")
            )


def init_db() -> None:
    # Comentario: garante schema minimo quando o banco sobe vazio.
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_users_columns()
    _ensure_posts_columns()


def get_db():
    # Comentario: dependency do FastAPI para abrir/fechar sessoes do banco.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
