from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemmas, models
from ..auth import get_current_user
from ..controllers import message as message_controller
from ..database import get_db

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/", response_model=schemmas.MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    message_in: schemmas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not message_in.receiver_id and not message_in.group_id:
        raise HTTPException(status_code=400, detail="receiver_id ou group_id e obrigatorio")
    return message_controller.create_message(db, current_user.id, message_in)


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
                last_message=message.content,
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
                last_message=message.content,
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
