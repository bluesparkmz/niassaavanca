from datetime import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import requests

import schemmas
import models
from auth import create_access_token, get_current_user
from controllers import user as user_controller
from controllers import whatsapp as whatsapp_controller
from controllers.storage_manager import storage_manager, AVATARS_FOLDER
from database import get_db

router = APIRouter(prefix="/users", tags=["users"])

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_DEFAULT_CLIENT_ID = "690521786732-6rh6blrhbu1ndqrpc2513mlv3mvrdacg.apps.googleusercontent.com"


def _verify_google_id_token(id_token: str) -> dict:
    try:
        response = requests.get(
            GOOGLE_TOKENINFO_URL,
            params={"id_token": id_token},
            timeout=10,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Falha ao validar token Google") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Token Google invalido")

    payload = response.json()
    sub = payload.get("sub")
    aud = payload.get("aud")
    exp = payload.get("exp")
    if not sub or not aud or not exp:
        raise HTTPException(status_code=401, detail="Token Google invalido")

    allowed = os.getenv("GOOGLE_CLIENT_IDS", GOOGLE_DEFAULT_CLIENT_ID)
    allowed_client_ids = {item.strip() for item in allowed.split(",") if item.strip()}
    if aud not in allowed_client_ids:
        raise HTTPException(status_code=401, detail="Cliente Google nao autorizado")

    try:
        expires_at = int(exp)
    except Exception:
        raise HTTPException(status_code=401, detail="Token Google expirado")

    if expires_at <= int(datetime.utcnow().timestamp()):
        raise HTTPException(status_code=401, detail="Token Google expirado")

    return payload


@router.post("/register", response_model=schemmas.UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    phone: str | None = Form(None),
    sex: str | None = Form(None),
    birth_date: str | None = Form(None),
    avatar: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    # Comentario: validar senha minima (4).
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 4 caracteres")

    # Comentario: validar unicidade de username e telefone.
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username ja existe")
    if phone and db.query(models.User).filter(models.User.phone == phone).first():
        raise HTTPException(status_code=400, detail="Telefone ja existe")

    avatar_path: str | None = None
    if avatar:
        avatar_path = await storage_manager.upload_file(
            avatar,
            AVATARS_FOLDER,
            allowed_mime_prefixes=("image/",),
        )

    parsed_birth_date = None
    if birth_date:
        try:
            parsed_birth_date = schemmas.date.fromisoformat(birth_date)
        except Exception:
            raise HTTPException(status_code=400, detail="birth_date invalida, use YYYY-MM-DD")

    user_in = schemmas.UserCreate(
        name=name,
        avatar=avatar_path,
        username=username,
        phone=phone,
        sex=sex,
        birth_date=parsed_birth_date,
        password=password,
    )
    return user_controller.create_user(db, user_in)


@router.post("/login", response_model=schemmas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Comentario: login via form-data (Swagger UI).
    user = user_controller.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    token = create_access_token({"sub": user.id})
    return schemmas.Token(access_token=token)


@router.post("/login-json", response_model=schemmas.Token)
def login_json(payload: schemmas.LoginRequest, db: Session = Depends(get_db)):
    # Comentario: login via JSON para clientes custom.
    user = user_controller.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    token = create_access_token({"sub": user.id})
    return schemmas.Token(access_token=token)


@router.post("/login-google", response_model=schemmas.Token)
def login_google(payload: schemmas.GoogleLoginRequest, db: Session = Depends(get_db)):
    claims = _verify_google_id_token(payload.id_token)
    google_sub = str(claims["sub"])
    username = f"google_{google_sub}"[:50]
    user = db.query(models.User).filter(models.User.username == username).first()

    if not user:
        user = models.User(
            name=(claims.get("name") or claims.get("email") or "Google User")[:120],
            avatar=claims.get("picture"),
            username=username,
            password_hash=user_controller.get_password_hash(f"google_{google_sub}_{datetime.utcnow().timestamp()}"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if not user.avatar and claims.get("picture"):
            user.avatar = claims.get("picture")
            changed = True
        if claims.get("name") and user.name != claims.get("name"):
            user.name = str(claims["name"])[:120]
            changed = True
        if changed:
            db.commit()
            db.refresh(user)

    token = create_access_token({"sub": user.id})
    return schemmas.Token(access_token=token)


@router.get("/me", response_model=schemmas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/me/push-token", response_model=schemmas.UserOut)
def set_push_token(
    payload: schemmas.PushTokenIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.token:
        push_device = None
        if payload.device_id:
            push_device = (
                db.query(models.PushDevice)
                .filter(
                    models.PushDevice.user_id == current_user.id,
                    models.PushDevice.device_id == payload.device_id,
                )
                .first()
            )
        if not push_device:
            push_device = (
                db.query(models.PushDevice)
                .filter(
                    models.PushDevice.user_id == current_user.id,
                    models.PushDevice.token == payload.token,
                )
                .first()
            )
        if not push_device:
            push_device = models.PushDevice(
                user_id=current_user.id,
                token=payload.token,
                device_id=payload.device_id,
                platform=payload.platform,
                last_seen_at=datetime.utcnow(),
            )
            db.add(push_device)
        else:
            push_device.token = payload.token
            push_device.device_id = payload.device_id or push_device.device_id
            push_device.platform = payload.platform or push_device.platform
            push_device.last_seen_at = datetime.utcnow()
        # Compatibilidade com clientes antigos que leem um unico campo.
        current_user.expo_push_token = payload.token
    else:
        delete_query = db.query(models.PushDevice).filter(models.PushDevice.user_id == current_user.id)
        if payload.device_id:
            delete_query = delete_query.filter(models.PushDevice.device_id == payload.device_id)
        delete_query.delete(synchronize_session=False)
        current_user.expo_push_token = None

    db.commit()
    db.refresh(current_user)
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
    current_user.avatar = await storage_manager.upload_file(
        file,
        AVATARS_FOLDER,
        allowed_mime_prefixes=("image/",),
    )
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


@router.get("/friends", response_model=list[schemmas.UserOut])
def list_friends(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Comentario: lista simples de usuarios (exceto o atual).
    users = db.query(models.User).filter(models.User.id != current_user.id).all()
    return users


@router.post("/password/otp/request")
def request_password_reset(payload: schemmas.OTPRequest, db: Session = Depends(get_db)):
    # Comentario: envia OTP via WhatsApp para o numero cadastrado.
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    if not user.phone:
        raise HTTPException(status_code=400, detail="Usuario sem telefone cadastrado")

    otp = whatsapp_controller.create_password_reset_otp(db, user)
    response = whatsapp_controller.send_password_reset_otp(user.phone, otp.code)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Falha ao enviar OTP")
    return {"detail": "OTP enviado"}


@router.post("/password/otp/verify")
def verify_password_reset(payload: schemmas.OTPVerify, db: Session = Depends(get_db)):
    # Comentario: valida OTP e atualiza senha.
    otp = (
        db.query(models.PasswordResetOTP)
        .filter(
            models.PasswordResetOTP.phone == payload.phone,
            models.PasswordResetOTP.code == payload.code,
            models.PasswordResetOTP.used.is_(False),
        )
        .order_by(models.PasswordResetOTP.created_at.desc())
        .first()
    )
    if not otp:
        raise HTTPException(status_code=400, detail="OTP invalido")
    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expirado")

    user = db.query(models.User).filter(models.User.id == otp.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    user_controller.set_password(db, user, payload.new_password)
    otp.used = True
    db.commit()
    return {"detail": "Senha atualizada"}
