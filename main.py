import sys
from pathlib import Path
from sqlalchemy import inspect, text

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

# Comentario: estilo SkyVenda sem pacote.
app_dir = Path(__file__).resolve().parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from database import engine  # noqa: E402
from models import Base  # noqa: E402
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

# Comentario: servir uploads para avatars.
uploads_dir = app_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Comentario: cria tabelas no startup (para prototipo).
Base.metadata.create_all(bind=engine)

# Comentario: patch leve de schema para ambientes existentes.
inspector = inspect(engine)
message_columns = {column["name"] for column in inspector.get_columns("messages")}
user_columns = {column["name"] for column in inspector.get_columns("users")}
with engine.begin() as conn:
    if "media_url" not in message_columns:
        conn.execute(text("ALTER TABLE messages ADD COLUMN media_url VARCHAR(255)"))
    if "media_type" not in message_columns:
        conn.execute(text("ALTER TABLE messages ADD COLUMN media_type VARCHAR(30)"))
    if "expo_push_token" not in user_columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN expo_push_token VARCHAR(255)"))

app.include_router(user_router)
app.include_router(messages_router)
app.include_router(websoket_router)


@app.get("/demo", response_class=HTMLResponse)
def demo_ui(request: Request):
    # Comentario: UI simples para demo no navegador.
    return templates.TemplateResponse("demo.html", {"request": request})
