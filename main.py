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
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def startup() -> None:
    init_db()

