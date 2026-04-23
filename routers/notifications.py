from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

import models
import schemmas
from auth import get_current_user, get_user_from_websocket_token
from controllers.notifications import mark_notification_read, notification_manager, notification_out
from database import SessionLocal, get_db


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[schemmas.NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )
    return [notification_out(item) for item in items]


@router.patch("/{notification_id}", response_model=schemmas.NotificationOut)
async def update_notification(
    notification_id: int,
    payload: schemmas.NotificationReadUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Notificacao nao encontrada")
    item = await mark_notification_read(db, item, payload.is_read)
    return notification_out(item)


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket):
    db = SessionLocal()
    user = None
    try:
        user = get_user_from_websocket_token(websocket, db)
        await notification_manager.connect(user.id, websocket)
        unread = (
            db.query(models.Notification)
            .filter(models.Notification.user_id == user.id, models.Notification.is_read == False)
            .order_by(models.Notification.created_at.desc())
            .limit(20)
            .all()
        )
        await websocket.send_json(
            {
                "event": "connected",
                "data": {
                    "user_id": user.id,
                    "unread": [notification_out(item).model_dump(mode="json") for item in unread],
                },
            }
        )
        while True:
            await websocket.receive_text()
            await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close(code=4401)
    finally:
        if user is not None:
            notification_manager.disconnect(user.id, websocket)
        db.close()
