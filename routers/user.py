from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from .. import schemmas
from ..auth import create_access_token, get_current_user
from ..controllers import user as user_controller
from ..database import get_db
from .. import models

router = APIRouter(prefix="/users", tags=["users"])

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"


@router.post("/register", response_model=schemmas.UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: schemmas.UserCreate, db: Session = Depends(get_db)):
    # Comentario: validar unicidade de username e telefone.
    if db.query(models.User).filter(models.User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username ja existe")
    if user_in.phone and db.query(models.User).filter(models.User.phone == user_in.phone).first():
        raise HTTPException(status_code=400, detail="Telefone ja existe")
    return user_controller.create_user(db, user_in)


@router.post("/login", response_model=schemmas.Token)
def login(payload: schemmas.LoginRequest, db: Session = Depends(get_db)):
    user = user_controller.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    token = create_access_token({"sub": user.id})
    return schemmas.Token(access_token=token)


@router.get("/me", response_model=schemmas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=schemmas.UserOut)
def update_me(
    user_in: schemmas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return user_controller.update_user(db, current_user, user_in)


@router.post("/me/avatar", response_model=schemmas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Comentario: valida tipo do arquivo e salva na pasta uploads.
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    filename = f"{current_user.id}_{uuid4().hex}{file_ext}"
    file_path = UPLOADS_DIR / filename

    content = await file.read()
    file_path.write_bytes(content)

    current_user.avatar = f"uploads/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user_controller.delete_user(db, current_user)
    return None
