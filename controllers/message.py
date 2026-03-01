from sqlalchemy.orm import Session

from .. import models, schemmas


def create_message(
    db: Session,
    sender_id: int,
    message_in: schemmas.MessageCreate,
) -> models.Message:
    message = models.Message(
        content=message_in.content,
        sender_id=sender_id,
        receiver_id=message_in.receiver_id,
        group_id=message_in.group_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_conversation(db: Session, user_id: int, other_user_id: int) -> list[models.Message]:
    return (
        db.query(models.Message)
        .filter(
            ((models.Message.sender_id == user_id) & (models.Message.receiver_id == other_user_id))
            | ((models.Message.sender_id == other_user_id) & (models.Message.receiver_id == user_id))
        )
        .order_by(models.Message.created_at.asc())
        .all()
    )


def get_group_messages(db: Session, group_id: int) -> list[models.Message]:
    return (
        db.query(models.Message)
        .filter(models.Message.group_id == group_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )


def create_group(db: Session, owner_id: int, group_in: schemmas.GroupCreate) -> models.Group:
    group = models.Group(
        name=group_in.name,
        description=group_in.description,
        owner_id=owner_id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def update_group(db: Session, group: models.Group, group_in: schemmas.GroupUpdate) -> models.Group:
    data = group_in.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group


def delete_group(db: Session, group: models.Group) -> None:
    db.delete(group)
    db.commit()


def add_group_member(db: Session, group_id: int, member_in: schemmas.GroupMemberAdd) -> models.GroupMember:
    member = models.GroupMember(
        group_id=group_id,
        user_id=member_in.user_id,
        role=member_in.role or "member",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_group_member(db: Session, group_id: int, user_id: int) -> None:
    member = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )
    if member:
        db.delete(member)
        db.commit()


def update_message(
    db: Session,
    message: models.Message,
    content: str,
) -> models.Message:
    message.content = content
    db.commit()
    db.refresh(message)
    return message


def delete_message(db: Session, message: models.Message) -> None:
    db.delete(message)
    db.commit()


def mark_messages_read(db: Session, message_ids: list[int], user_id: int) -> int:
    # Comentario: cria marcacoes de leitura ignorando as que ja existem.
    created = 0
    for message_id in message_ids:
        exists = (
            db.query(models.MessageRead)
            .filter(models.MessageRead.message_id == message_id, models.MessageRead.user_id == user_id)
            .first()
        )
        if exists:
            continue
        db.add(models.MessageRead(message_id=message_id, user_id=user_id))
        created += 1
    if created:
        db.commit()
    return created
