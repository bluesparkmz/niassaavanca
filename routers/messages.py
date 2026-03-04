from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemmas
import models
from auth import get_current_user
from controllers import message as message_controller
from controllers.conection_manager import global_connection_manager
from controllers.push_notifications import send_expo_push, is_expo_push_token
from controllers.storage_manager import storage_manager, MESSAGES_FOLDER
from database import get_db

router = APIRouter(prefix="/messages", tags=["messages"])


def _serialize_message(message: models.Message) -> dict:
    return {
        "id": message.id,
        "content": message.content,
        "sender_id": message.sender_id,
        "receiver_id": message.receiver_id,
        "group_id": message.group_id,
        "media_url": message.media_url,
        "media_type": message.media_type,
        "created_at": message.created_at.isoformat(),
    }


async def _broadcast_message(message: models.Message) -> None:
    response = {"type": "message", "message": _serialize_message(message)}
    if message.group_id:
        await global_connection_manager.send_group(message.group_id, response)
    elif message.receiver_id:
        await global_connection_manager.send_personal(message.receiver_id, response)
        await global_connection_manager.send_personal(message.sender_id, response)


def _build_push_preview(message: models.Message) -> str:
    if (message.content or "").strip():
        preview = message.content.strip()
        return preview[:120]
    if message.media_type == "image":
        return "Enviou uma imagem."
    if message.media_type == "audio":
        return "Enviou um audio."
    return "Nova mensagem."


def _send_push_notifications(db: Session, message: models.Message) -> None:
    sender = db.query(models.User).filter(models.User.id == message.sender_id).first()
    sender_name = sender.name if sender else "Novo contato"
    body = _build_push_preview(message)

    if message.receiver_id:
        receiver = db.query(models.User).filter(models.User.id == message.receiver_id).first()
        if (
            receiver
            and is_expo_push_token(receiver.expo_push_token)
            and not global_connection_manager.is_user_online(receiver.id)
        ):
            send_expo_push(
                to_token=receiver.expo_push_token,  # type: ignore[arg-type]
                title=sender_name,
                body=body,
                data={"chat_type": "direct", "chat_id": message.sender_id},
            )
        return

    if message.group_id:
        memberships = (
            db.query(models.GroupMember)
            .filter(models.GroupMember.group_id == message.group_id, models.GroupMember.user_id != message.sender_id)
            .all()
        )
        for membership in memberships:
            user = db.query(models.User).filter(models.User.id == membership.user_id).first()
            if not user or not is_expo_push_token(user.expo_push_token):
                continue
            if global_connection_manager.is_user_online(user.id):
                continue
            send_expo_push(
                to_token=user.expo_push_token,  # type: ignore[arg-type]
                title=sender_name,
                body=body,
                data={"chat_type": "group", "chat_id": message.group_id},
            )


@router.post("/", response_model=schemmas.MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_in: schemmas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not message_in.receiver_id and not message_in.group_id:
        raise HTTPException(status_code=400, detail="receiver_id ou group_id e obrigatorio")
    if not (message_in.content or "").strip() and not message_in.media_url:
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    message = message_controller.create_message(db, current_user.id, message_in)
    await _broadcast_message(message)
    _send_push_notifications(db, message)
    return message


@router.post("/upload", response_model=schemmas.MessageOut, status_code=status.HTTP_201_CREATED)
async def upload_message_media(
    file: UploadFile = File(...),
    receiver_id: int | None = Form(None),
    group_id: int | None = Form(None),
    content: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not receiver_id and not group_id:
        raise HTTPException(status_code=400, detail="receiver_id ou group_id e obrigatorio")

    if not file.content_type:
        raise HTTPException(status_code=400, detail="Tipo de arquivo invalido")

    if file.content_type.startswith("image/"):
        media_type = "image"
    elif file.content_type.startswith("audio/"):
        media_type = "audio"
    else:
        raise HTTPException(status_code=400, detail="Apenas imagem e audio sao suportados")

    media_url = await storage_manager.upload_file(
        file,
        MESSAGES_FOLDER,
        allowed_mime_prefixes=("image/", "audio/"),
    )

    message_in = schemmas.MessageCreate(
        content=(content or "").strip(),
        receiver_id=receiver_id,
        group_id=group_id,
        media_url=media_url,
        media_type=media_type,
    )
    message = message_controller.create_message(db, current_user.id, message_in)
    await _broadcast_message(message)
    _send_push_notifications(db, message)
    return message


@router.get("/conversation/{other_user_id}", response_model=list[schemmas.MessageOut])
def get_conversation(
    other_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return message_controller.get_conversation(db, current_user.id, other_user_id)


@router.get("/chats", response_model=list[schemmas.ChatSummary])
def list_chats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Comentario: MVP simples - percorre mensagens mais recentes e monta lista.
    chats: list[schemmas.ChatSummary] = []
    direct_map: dict[int, schemmas.ChatSummary] = {}

    direct_messages = (
        db.query(models.Message)
        .filter(
            models.Message.group_id.is_(None),
            (
                (models.Message.sender_id == current_user.id)
                | (models.Message.receiver_id == current_user.id)
            ),
        )
        .order_by(models.Message.created_at.desc())
        .all()
    )

    for message in direct_messages:
        other_id = message.receiver_id if message.sender_id == current_user.id else message.sender_id
        if other_id is None:
            continue
        if other_id not in direct_map:
            other_user = db.query(models.User).filter(models.User.id == other_id).first()
            unread_count = (
                db.query(func.count(models.Message.id))
                .outerjoin(
                    models.MessageRead,
                    (models.MessageRead.message_id == models.Message.id)
                    & (models.MessageRead.user_id == current_user.id),
                )
                .filter(
                    models.Message.group_id.is_(None),
                    models.Message.sender_id == other_id,
                    models.Message.receiver_id == current_user.id,
                    models.MessageRead.id.is_(None),
                )
                .scalar()
            )
            direct_map[other_id] = schemmas.ChatSummary(
                chat_type="direct",
                chat_id=other_id,
                name=other_user.name if other_user else None,
                avatar=other_user.avatar if other_user else None,
                last_message=(
                    message.content
                    or ("[Imagem]" if message.media_type == "image" else "[Audio]" if message.media_type == "audio" else "")
                ),
                last_message_at=message.created_at,
                last_message_id=message.id,
                last_message_sender_id=message.sender_id,
                unread_count=unread_count or 0,
            )

    chats.extend(direct_map.values())

    group_ids = [
        membership.group_id
        for membership in db.query(models.GroupMember)
        .filter(models.GroupMember.user_id == current_user.id)
        .all()
    ]

    if group_ids:
        group_messages = (
            db.query(models.Message)
            .filter(models.Message.group_id.in_(group_ids))
            .order_by(models.Message.created_at.desc())
            .all()
        )
        group_map: dict[int, schemmas.ChatSummary] = {}
        for message in group_messages:
            group_id = message.group_id
            if group_id is None or group_id in group_map:
                continue
            group = db.query(models.Group).filter(models.Group.id == group_id).first()
            unread_count = (
                db.query(func.count(models.Message.id))
                .outerjoin(
                    models.MessageRead,
                    (models.MessageRead.message_id == models.Message.id)
                    & (models.MessageRead.user_id == current_user.id),
                )
                .filter(
                    models.Message.group_id == group_id,
                    models.Message.sender_id != current_user.id,
                    models.MessageRead.id.is_(None),
                )
                .scalar()
            )
            group_map[group_id] = schemmas.ChatSummary(
                chat_type="group",
                chat_id=group_id,
                name=group.name if group else None,
                avatar=None,
                last_message=(
                    message.content
                    or ("[Imagem]" if message.media_type == "image" else "[Audio]" if message.media_type == "audio" else "")
                ),
                last_message_at=message.created_at,
                last_message_id=message.id,
                last_message_sender_id=message.sender_id,
                unread_count=unread_count or 0,
            )
        chats.extend(group_map.values())

    chats.sort(key=lambda item: item.last_message_at or 0, reverse=True)
    return chats


@router.post("/chats/{chat_type}/{chat_id}/read")
def mark_chat_read(
    chat_type: str,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if chat_type == "dm":
        chat_type = "direct"

    if chat_type not in {"direct", "group"}:
        raise HTTPException(status_code=400, detail="chat_type invalido")

    message_ids: list[int] = []
    if chat_type == "direct":
        # Comentario: marca mensagens recebidas desse usuario.
        messages = (
            db.query(models.Message.id)
            .outerjoin(
                models.MessageRead,
                (models.MessageRead.message_id == models.Message.id)
                & (models.MessageRead.user_id == current_user.id),
            )
            .filter(
                models.Message.group_id.is_(None),
                models.Message.sender_id == chat_id,
                models.Message.receiver_id == current_user.id,
                models.MessageRead.id.is_(None),
            )
            .all()
        )
        message_ids = [row.id for row in messages]
    else:
        membership = (
            db.query(models.GroupMember)
            .filter(models.GroupMember.group_id == chat_id, models.GroupMember.user_id == current_user.id)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Usuario nao faz parte do grupo")
        messages = (
            db.query(models.Message.id)
            .outerjoin(
                models.MessageRead,
                (models.MessageRead.message_id == models.Message.id)
                & (models.MessageRead.user_id == current_user.id),
            )
            .filter(
                models.Message.group_id == chat_id,
                models.Message.sender_id != current_user.id,
                models.MessageRead.id.is_(None),
            )
            .all()
        )
        message_ids = [row.id for row in messages]

    created = message_controller.mark_messages_read(db, message_ids, current_user.id)
    return {"marked_read": created}


@router.put("/{message_id}", response_model=schemmas.MessageOut)
def update_message(
    message_id: int,
    payload: schemmas.MessageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o sender pode editar")
    return message_controller.update_message(db, message, payload.content)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o sender pode apagar")
    message_controller.delete_message(db, message)
    return None


@router.post("/{message_id}/read")
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    if message.receiver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o receptor pode marcar como lida")
    created = message_controller.mark_message_read(db, message_id, current_user.id)
    return {"marked": created}


@router.get("/group/{group_id}", response_model=list[schemmas.MessageOut])
def get_group_messages(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Comentario: validar se o usuario pertence ao grupo.
    membership = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == current_user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Usuario nao faz parte do grupo")
    return message_controller.get_group_messages(db, group_id)


@router.post("/groups", response_model=schemmas.GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    group_in: schemmas.GroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = message_controller.create_group(db, current_user.id, group_in)
    # Comentario: adiciona o owner como membro.
    message_controller.add_group_member(
        db,
        group.id,
        schemmas.GroupMemberAdd(user_id=current_user.id, role="owner"),
    )
    return group


@router.put("/groups/{group_id}", response_model=schemmas.GroupOut)
def update_group(
    group_id: int,
    group_in: schemmas.GroupUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o owner pode editar")
    return message_controller.update_group(db, group, group_in)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o owner pode apagar")
    message_controller.delete_group(db, group)
    return None


@router.post("/groups/{group_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    group_id: int,
    member_in: schemmas.GroupMemberAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o owner pode adicionar")
    return message_controller.add_group_member(db, group_id, member_in)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")
    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Apenas o owner pode remover")
    message_controller.remove_group_member(db, group_id, user_id)
    return None
