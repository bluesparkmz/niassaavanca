import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Comentario: servir uploads para avatars.
uploads_dir = app_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Comentario: cria tabelas no startup (para prototipo).
Base.metadata.create_all(bind=engine)

app.include_router(user_router)
app.include_router(messages_router)
app.include_router(websoket_router)


@app.get("/demo", response_class=HTMLResponse)
def demo_ui(request: Request):
    # Comentario: UI simples para demo no navegador.
    return templates.TemplateResponse("demo.html", {"request": request})
