from sqlalchemy.orm import Session

import models
import schemmas
from auth import get_password_hash, verify_password


def create_user(db: Session, user_in: schemmas.UserCreate) -> models.User:
    user = models.User(
        name=user_in.name,
        avatar=user_in.avatar,
        username=user_in.username,
        phone=user_in.phone,
        sex=user_in.sex,
        birth_date=user_in.birth_date,
        password_hash=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> models.User | None:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def update_user(db: Session, user: models.User, user_in: schemmas.UserUpdate) -> models.User:
    data = user_in.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: models.User) -> None:
    db.delete(user)
    db.commit()
