from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    name: str
    avatar: Optional[str] = None
    username: str
    phone: Optional[str] = None
    sex: Optional[str] = None
    birth_date: Optional[date] = None


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    sex: Optional[str] = None
    birth_date: Optional[date] = None


class UserOut(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class MessageCreate(BaseModel):
    content: str
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    content: str
    sender_id: int
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageUpdate(BaseModel):
    content: str


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class GroupMemberAdd(BaseModel):
    user_id: int
    role: Optional[str] = "member"


class WebSocketPayload(BaseModel):
    type: str
    content: Optional[str] = None
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    # Comentario: campos para sinalizacao WebRTC.
    sdp: Optional[dict] = None
    candidate: Optional[dict] = None


class ChatSummary(BaseModel):
    chat_type: str
    chat_id: int
    name: Optional[str] = None
    avatar: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_message_id: Optional[int] = None
    last_message_sender_id: Optional[int] = None
    unread_count: int = 0


class ChatReadRequest(BaseModel):
    chat_type: str
    chat_id: int
