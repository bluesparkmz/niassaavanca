import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.orm import Session

import schemmas
import models
from auth import get_user_from_token
from controllers.conection_manager import Connection, global_connection_manager
from controllers import message as message_controller
from database import SessionLocal

router = APIRouter(prefix="/ws", tags=["websocket"])


def _extract_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    return token


async def _heartbeat_loop(ws: WebSocket, interval: int = 30):
    while True:
        try:
            if (
                ws.client_state != WebSocketState.CONNECTED
                or ws.application_state != WebSocketState.CONNECTED
            ):
                break
            await ws.send_json({"type": "ping", "ts": datetime.utcnow().isoformat()})
        except Exception:
            break
        await asyncio.sleep(interval)


@router.websocket("/chat")
async def chat_socket(websocket: WebSocket):
    db: Session = SessionLocal()
    user: models.User | None = None
    heartbeat_task: asyncio.Task | None = None
    try:
        token = _extract_token(websocket)
        if not token:
            await websocket.accept()
            await websocket.close(code=1008, reason="Token obrigatorio")
            return

        user = get_user_from_token(token, db)
        connection = Connection(
            id=user.id,
            username=user.username,
            name=user.name,
            avatar=user.avatar,
            websocket=websocket,
            app_type=websocket.query_params.get("app_type", "unknown"),
        )
        await global_connection_manager.connect(connection)

        for membership in user.group_memberships:
            global_connection_manager.join_group(user.id, membership.group_id)

        # Comentario: envia snapshot inicial de usuarios online para o cliente.
        online_user_ids = [online_user["id"] for online_user in global_connection_manager.get_online_users()]
        await websocket.send_json({"type": "online_users", "data": {"user_ids": online_user_ids}})

        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

        while True:
            raw = await websocket.receive_text()
            payload = schemmas.WebSocketPayload(**json.loads(raw))

            if payload.type == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.utcnow().isoformat()})
                continue

            if payload.type == "typing" and payload.receiver_id:
                await global_connection_manager.send_typing(user.id, payload.receiver_id)
                continue

            if payload.type == "recording" and payload.receiver_id:
                await global_connection_manager.send_recording(
                    user.id,
                    payload.receiver_id,
                    payload.content or "start",
                )
                continue

            if payload.type == "read_all" and payload.receiver_id:
                # Comentario: marca mensagens recebidas como lidas e avisa o sender.
                messages = (
                    db.query(models.Message)
                    .filter(
                        models.Message.sender_id == payload.receiver_id,
                        models.Message.receiver_id == user.id,
                    )
                    .all()
                )
                message_ids = [m.id for m in messages]
                if message_ids:
                    message_controller.mark_messages_read(db, message_ids, user.id)
                    await global_connection_manager.send_personal(
                        payload.receiver_id,
                        {
                            "type": "messages_read",
                            "data": {"by_user": user.id, "message_ids": message_ids},
                        },
                    )
                continue

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
                    await global_connection_manager.send_group(message.group_id, response)
                elif message.receiver_id:
                    await global_connection_manager.send_personal(message.receiver_id, response)
                    await global_connection_manager.send_personal(user.id, response)
                continue

            if payload.type == "call_initiate" and payload.receiver_id:
                call_id = await global_connection_manager.create_video_call(user.id, payload.receiver_id)
                if not call_id:
                    await websocket.send_json({"type": "error", "detail": "Usuario offline"})
                continue

            if payload.type == "call_accept" and payload.content:
                await global_connection_manager.handle_call_response(payload.content, user.id, True)
                continue

            if payload.type == "call_reject" and payload.content:
                await global_connection_manager.handle_call_response(payload.content, user.id, False)
                continue

            if payload.type == "sdp_offer" and payload.content and payload.sdp:
                await global_connection_manager.relay_sdp(payload.content, user.id, payload.sdp, "sdp_offer")
                continue

            if payload.type == "sdp_answer" and payload.content and payload.sdp:
                await global_connection_manager.relay_sdp(payload.content, user.id, payload.sdp, "sdp_answer")
                continue

            if payload.type == "ice_candidate" and payload.content and payload.candidate:
                await global_connection_manager.relay_ice_candidate(payload.content, user.id, payload.candidate)
                continue

            if payload.type == "call_end" and payload.content:
                await global_connection_manager.end_call(payload.content, user.id)
                continue

            await websocket.send_json({"type": "error", "detail": "Tipo desconhecido"})

    except WebSocketDisconnect:
        if user:
            await global_connection_manager.disconnect(user.id, websocket=websocket)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        db.close()
