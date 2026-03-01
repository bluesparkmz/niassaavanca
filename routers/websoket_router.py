import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

import schemmas
import models
from auth import get_user_from_token
from controllers.conection_manager import ConnectionManager
from controllers import message as message_controller
from database import SessionLocal

router = APIRouter(prefix="/ws", tags=["websocket"])
manager = ConnectionManager()


@router.websocket("/chat")
async def chat_socket(websocket: WebSocket, token: str):
    db: Session = SessionLocal()
    user: models.User | None = None
    try:
        user = get_user_from_token(token, db)
        await manager.connect(user.id, websocket)

        # Comentario: carrega grupos do usuario na memoria para broadcast.
        for membership in user.group_memberships:
            manager.join_group(user.id, membership.group_id)

        while True:
            raw = await websocket.receive_text()
            payload = schemmas.WebSocketPayload(**json.loads(raw))

            if payload.type == "message":
                message_in = schemmas.MessageCreate(
                    content=payload.content or "",
                    receiver_id=payload.receiver_id,
                    group_id=payload.group_id,
                )
                message = message_controller.create_message(db, user.id, message_in)
                response = {
                    "type": "message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "sender_id": message.sender_id,
                        "receiver_id": message.receiver_id,
                        "group_id": message.group_id,
                        "created_at": message.created_at.isoformat(),
                    },
                }
                if message.group_id:
                    await manager.send_group(message.group_id, response)
                elif message.receiver_id:
                    await manager.send_personal(message.receiver_id, response)
                    await manager.send_personal(user.id, response)

            elif payload.type in {"webrtc_offer", "webrtc_answer", "webrtc_ice"}:
                # Comentario: sinalizacao WebRTC via WebSocket.
                if not payload.receiver_id:
                    await websocket.send_json({"type": "error", "detail": "receiver_id e obrigatorio"})
                    continue
                await manager.send_personal(
                    payload.receiver_id,
                    {
                        "type": payload.type,
                        "from_user_id": user.id,
                        "sdp": payload.sdp,
                        "candidate": payload.candidate,
                    },
                )
            else:
                await websocket.send_json({"type": "error", "detail": "Tipo desconhecido"})

    except WebSocketDisconnect:
        if user:
            manager.disconnect(user.id)
    finally:
        db.close()
