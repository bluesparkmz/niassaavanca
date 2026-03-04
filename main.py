import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import os

# Comentario: estilo SkyVenda sem pacote.
app_dir = Path(__file__).resolve().parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from routers.user import router as user_router  # noqa: E402
from routers.messages import router as messages_router  # noqa: E402
from routers.websoket_router import router as websoket_router  # noqa: E402

app = FastAPI(title="MeuChat")
templates = Jinja2Templates(directory=str(app_dir / "templates"))

cors_origins = os.getenv(
    "CORS_ORIGINS",
    "https://meuchat-mz.vercel.app,https://www.meuchat-mz.vercel.app,http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081,http://localhost:5173,http://127.0.0.1:5173",
)
allow_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
cors_origin_regex = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"^https://([a-zA-Z0-9-]+\.)?vercel\.app$",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(messages_router)
app.include_router(websoket_router)

