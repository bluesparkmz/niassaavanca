from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.orm import Session

import models
import schemmas


class NotificationConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self.active_connections.get(user_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        connections = list(self.active_connections.get(user_id, set()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(user_id, websocket)


notification_manager = NotificationConnectionManager()


def notification_out(item: models.Notification) -> schemmas.NotificationOut:
    return schemmas.NotificationOut(
        id=item.id,
        user_id=item.user_id,
        notification_type=item.notification_type.value if hasattr(item.notification_type, "value") else str(item.notification_type),
        title=item.title,
        body=item.body,
        payload=item.payload,
        is_read=item.is_read,
        created_at=item.created_at,
        read_at=item.read_at,
    )


async def create_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    body: str | None = None,
    payload: dict | None = None,
) -> models.Notification:
    item = models.Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        payload=payload or {},
        is_read=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    await notification_manager.send_to_user(
        user_id,
        {
            "event": "notification",
            "data": notification_out(item).model_dump(mode="json"),
        },
    )
    return item


async def mark_notification_read(db: Session, item: models.Notification, is_read: bool) -> models.Notification:
    item.is_read = is_read
    item.read_at = datetime.utcnow() if is_read else None
    db.commit()
    db.refresh(item)
    await notification_manager.send_to_user(
        item.user_id,
        {
            "event": "notification.updated",
            "data": notification_out(item).model_dump(mode="json"),
        },
    )
    return item
