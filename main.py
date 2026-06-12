import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


app_dir = Path(__file__).resolve().parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from database import init_db  # noqa: E402
from routers.ai import router as ai_router  # noqa: E402
from routers.admin import router as admin_router  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402
from routers.catalog import router as catalog_router  # noqa: E402
from routers.companies import router as companies_router  # noqa: E402
from routers.notifications import router as notifications_router  # noqa: E402


logger = logging.getLogger(__name__)
app = FastAPI(title="Niassa Avança API", version="1.0.0")

DEFAULT_CORS_ORIGINS = ",".join(
    [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "https://niassa.co.mz",
        "https://www.niassa.co.mz",
        "https://api.niassa.co.mz",
        "https://lovable.dev"
    ]
)


def _normalize_cors_origin(origin: str) -> str:
    value = origin.strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("//"):
        return f"https:{value}".rstrip("/")
    if "://" not in value:
        return f"https://{value}"
    return value


cors_origins = os.getenv(
    "CORS_ORIGINS",
    DEFAULT_CORS_ORIGINS,
)
allow_origins = [
    normalized
    for normalized in (_normalize_cors_origin(origin) for origin in cors_origins.split(","))
    if normalized
]
allow_origin_regex = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"^https?://([a-zA-Z0-9-]+\.)*(niassa\.co\.mz|vercel\.app)$",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(companies_router)
app.include_router(catalog_router)
app.include_router(notifications_router)
app.include_router(ai_router)

# Serve uploads folder
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health")
def health():
    return {"status": "ok", "service": "niassaavanca-api"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {str(exc)}"})


def _ensure_admin_user() -> None:
    from auth import get_password_hash
    from database import SessionLocal
    import models

    ADMIN_EMAIL = "djoaquimnamueto@gmail.com"
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first()
        if not user:
            user = models.User(
                full_name="Admin",
                name="Admin",
                username="admin",
                email=ADMIN_EMAIL.lower().strip(),
                phone=None,
                password_hash=get_password_hash("1234"),
                role=models.UserRole.ADMIN,
                is_admin=True,
                is_active=True,
            )
            db.add(user)
            db.commit()
            logger.info("Created admin user: %s (role=%s, is_admin=%s)", ADMIN_EMAIL, user.role.value if hasattr(user.role, "value") else str(user.role), user.is_admin)
        else:
            logger.info("Found existing user: %s (role=%s, is_admin=%s)", ADMIN_EMAIL, user.role.value if hasattr(user.role, "value") else str(user.role), user.is_admin)
            if user.role != models.UserRole.ADMIN or not user.is_admin:
                user.role = models.UserRole.ADMIN
                user.is_admin = True
                db.commit()
                logger.info("Updated user to admin: %s (role=%s, is_admin=%s)", ADMIN_EMAIL, user.role.value if hasattr(user.role, "value") else str(user.role), user.is_admin)
    except Exception as e:
        logger.warning("Could not ensure admin user: %s", e)
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    
    # Run Alembic migrations
    from alembic.config import Config
    from alembic import command
    import os
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "postgresql://user:password@localhost/db"))
    command.upgrade(alembic_cfg, "head")
    
    _ensure_admin_user()

