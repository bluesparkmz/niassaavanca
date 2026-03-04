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
from controllers.push_notifications import is_expo_push_token, send_expo_push
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


def _push_preview(message: models.Message) -> str:
    if (message.content or "").strip():
        return message.content.strip()[:120]
    if message.media_type == "image":
        return "Enviou uma imagem."
    if message.media_type == "audio":
        return "Enviou um audio."
    return "Nova mensagem."


@router.websocket("")
@router.websocket("/chat")
async def chat_socket(websocket: WebSocket):
    user: models.User | None = None
    user_id: int | None = None
    group_ids: list[int] = []
    heartbeat_task: asyncio.Task | None = None
    try:
        token = _extract_token(websocket)
        if not token:
            await websocket.accept()
            await websocket.close(code=1008, reason="Token obrigatorio")
            return

        # Comentario: autentica com sessao curta para nao prender conexao no pool.
        db_auth: Session = SessionLocal()
        try:
            user = get_user_from_token(token, db_auth)
            user_id = user.id
            group_ids = [membership.group_id for membership in user.group_memberships]
        finally:
            db_auth.close()

        connection = Connection(
            id=user.id,
            username=user.username,
            name=user.name,
            avatar=user.avatar,
            websocket=websocket,
            app_type=websocket.query_params.get("app_type", "unknown"),
        )
        await global_connection_manager.connect(connection)

        for group_id in group_ids:
            global_connection_manager.join_group(user.id, group_id)

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
                db_msg: Session = SessionLocal()
                try:
                    messages = (
                        db_msg.query(models.Message)
                        .filter(
                            models.Message.sender_id == payload.receiver_id,
                            models.Message.receiver_id == user.id,
                        )
                        .all()
                    )
                    message_ids = [m.id for m in messages]
                    if message_ids:
                        message_controller.mark_messages_read(db_msg, message_ids, user.id)
                        await global_connection_manager.send_personal(
                            payload.receiver_id,
                            {
                                "type": "messages_read",
                                "data": {"by_user": user.id, "message_ids": message_ids},
                            },
                        )
                finally:
                    db_msg.close()
                continue

            if payload.type == "message":
                message_in = schemmas.MessageCreate(
                    content=payload.content or "",
                    receiver_id=payload.receiver_id,
                    group_id=payload.group_id,
                    media_url=payload.media_url,
                    media_type=payload.media_type,
                )
                db_msg: Session = SessionLocal()
                try:
                    message = message_controller.create_message(db_msg, user.id, message_in)
                    sender_name = user.name or "Novo contato"
                    if message.receiver_id:
                        receiver = db_msg.query(models.User).filter(models.User.id == message.receiver_id).first()
                        if (
                            receiver
                            and is_expo_push_token(receiver.expo_push_token)
                            and not global_connection_manager.is_user_online(receiver.id)
                        ):
                            send_expo_push(
                                to_token=receiver.expo_push_token,  # type: ignore[arg-type]
                                title=sender_name,
                                body=_push_preview(message),
                                data={"chat_type": "direct", "chat_id": message.sender_id},
                            )
                    elif message.group_id:
                        memberships = (
                            db_msg.query(models.GroupMember)
                            .filter(models.GroupMember.group_id == message.group_id, models.GroupMember.user_id != message.sender_id)
                            .all()
                        )
                        for membership in memberships:
                            member_user = db_msg.query(models.User).filter(models.User.id == membership.user_id).first()
                            if not member_user or not is_expo_push_token(member_user.expo_push_token):
                                continue
                            if global_connection_manager.is_user_online(member_user.id):
                                continue
                            send_expo_push(
                                to_token=member_user.expo_push_token,  # type: ignore[arg-type]
                                title=sender_name,
                                body=_push_preview(message),
                                data={"chat_type": "group", "chat_id": message.group_id},
                            )
                finally:
                    db_msg.close()
                response = {
                    "type": "message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "sender_id": message.sender_id,
                        "receiver_id": message.receiver_id,
                        "group_id": message.group_id,
                        "media_url": message.media_url,
                        "media_type": message.media_type,
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
        pass
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        if user_id is not None:
            await global_connection_manager.disconnect(user_id, websocket=websocket)
