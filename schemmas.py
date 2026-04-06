from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    name: str
    avatar: Optional[str] = None
    username: str
    phone: Optional[str] = None
    sex: Optional[str] = None
    birth_date: Optional[date] = None


class UserCreate(UserBase):
    password: str = Field(min_length=4)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    sex: Optional[str] = None
    birth_date: Optional[date] = None


class UserOut(UserBase):
    id: int
    expo_push_token: Optional[str] = None
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class MessageCreate(BaseModel):
    content: Optional[str] = None
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    content: str
    sender_id: int
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
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
    media_url: Optional[str] = None
    media_type: Optional[str] = None
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


class OTPRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
    code: str
    new_password: str = Field(min_length=4)


class PushTokenIn(BaseModel):
    token: Optional[str] = None
    device_id: Optional[str] = None
    platform: Optional[str] = None


TopicLiteral = Literal["natureza", "agricultura", "turismo"]


class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    content: str = Field(min_length=3)
    topic: Optional[TopicLiteral] = None
    category: Optional[TopicLiteral] = None
    image_url: Optional[str] = None


class PostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=180)
    content: Optional[str] = Field(default=None, min_length=3)
    topic: Optional[TopicLiteral] = None
    category: Optional[TopicLiteral] = None
    image_url: Optional[str] = None


class PostAuthor(BaseModel):
    id: int
    name: str
    username: str
    avatar: Optional[str] = None

    class Config:
        from_attributes = True


class PostOut(BaseModel):
    id: int
    title: str
    content: str
    topic: TopicLiteral
    category: TopicLiteral
    image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    likes_count: int = 0
    comments_count: int = 0
    liked_by_me: bool = False
    author: PostAuthor


class PostCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PostCommentOut(BaseModel):
    id: int
    post_id: int
    content: str
    created_at: datetime
    updated_at: datetime
    user: PostAuthor


class PostLikeToggleOut(BaseModel):
    liked: bool
    likes_count: int


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(min_length=1, max_length=8000)


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[AIChatMessage] = Field(default_factory=list)


class AIChatResponse(BaseModel):
    reply: str
    model: str


class AIRealtimeClientEvent(BaseModel):
    type: Literal["prompt", "audio", "image", "end_turn", "ping"]
    text: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = None
