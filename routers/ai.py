import asyncio
import base64
import contextlib
import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from starlette.websockets import WebSocketState

import schemmas
from auth import get_current_user, get_user_from_token
from database import SessionLocal

router = APIRouter(prefix="/ai", tags=["ai"])

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "models/gemini-3.1-flash-live-preview")
APP_SYSTEM_INSTRUCTION = os.getenv(
    "AI_SYSTEM_INSTRUCTION",
    (
        "Voce e o assistente oficial do app de natureza Niassa. "
        "Ajude utilizadores com duvidas sobre posts, natureza, turismo, agricultura, "
        "uso do aplicativo e seguranca. Responda em portugues simples, objetiva e amigavel."
    ),
)


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY nao configurada")
    return genai.Client(http_options={"api_version": "v1beta"}, api_key=api_key)


def _extract_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def _build_text_prompt(payload: schemmas.AIChatRequest) -> str:
    lines = [APP_SYSTEM_INSTRUCTION]
    if payload.history:
        lines.append("Historico recente:")
        for item in payload.history[-10:]:
            lines.append(f"{item.role}: {item.content.strip()}")
    lines.append(f"user: {payload.message.strip()}")
    lines.append("assistant:")
    return "\n".join(lines)


@router.post("/chat", response_model=schemmas.AIChatResponse)
def chat_with_ai(
    payload: schemmas.AIChatRequest,
    current_user=Depends(get_current_user),
):
    _ = current_user
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=_build_text_prompt(payload),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com Gemini: {exc}") from exc

    reply = (getattr(response, "text", None) or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail="Gemini nao devolveu texto")
    return schemmas.AIChatResponse(reply=reply, model=TEXT_MODEL)


async def _send_keepalive(websocket: WebSocket, interval_seconds: int = 25) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        if websocket.client_state != WebSocketState.CONNECTED:
            break
        await websocket.send_json({"type": "ping", "ts": datetime.utcnow().isoformat()})


@router.websocket("/ws")
async def ai_realtime_socket(websocket: WebSocket):
    token = _extract_token(websocket)
    if not token:
        await websocket.accept()
        await websocket.close(code=1008, reason="Token obrigatorio")
        return

    db = SessionLocal()
    try:
        get_user_from_token(token, db)
    except HTTPException as exc:
        await websocket.accept()
        await websocket.close(code=1008, reason=exc.detail)
        db.close()
        return
    finally:
        with contextlib.suppress(Exception):
            db.close()

    await websocket.accept()

    client = _get_client()
    config = types.LiveConnectConfig(
        response_modalities=["TEXT", "AUDIO"],
        media_resolution="MEDIA_RESOLUTION_MEDIUM",
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
            )
        ),
        system_instruction=APP_SYSTEM_INSTRUCTION,
    )

    receive_task: asyncio.Task | None = None
    keepalive_task: asyncio.Task | None = None

    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            async def pump_model_to_client() -> None:
                while True:
                    turn = session.receive()
                    async for response in turn:
                        if getattr(response, "text", None):
                            await websocket.send_json(
                                {
                                    "type": "assistant_text",
                                    "text": response.text,
                                }
                            )
                        if getattr(response, "data", None):
                            encoded = base64.b64encode(response.data).decode("utf-8")
                            await websocket.send_json(
                                {
                                    "type": "assistant_audio",
                                    "data": encoded,
                                    "mime_type": "audio/pcm",
                                }
                            )
                    await websocket.send_json({"type": "turn_complete"})

            receive_task = asyncio.create_task(pump_model_to_client())
            keepalive_task = asyncio.create_task(_send_keepalive(websocket))

            while True:
                raw = await websocket.receive_text()
                payload = schemmas.AIRealtimeClientEvent(**json.loads(raw))

                if payload.type == "ping":
                    await websocket.send_json({"type": "pong", "ts": datetime.utcnow().isoformat()})
                    continue

                if payload.type == "prompt":
                    if not payload.text:
                        await websocket.send_json({"type": "error", "detail": "Campo text obrigatorio"})
                        continue
                    await session.send(input=payload.text, end_of_turn=False)
                    continue

                if payload.type == "audio":
                    if not payload.data:
                        await websocket.send_json({"type": "error", "detail": "Campo data obrigatorio"})
                        continue
                    await session.send(
                        input={
                            "data": base64.b64decode(payload.data),
                            "mime_type": payload.mime_type or "audio/pcm",
                        }
                    )
                    continue

                if payload.type == "image":
                    if not payload.data:
                        await websocket.send_json({"type": "error", "detail": "Campo data obrigatorio"})
                        continue
                    await session.send(
                        input={
                            "data": payload.data,
                            "mime_type": payload.mime_type or "image/jpeg",
                        }
                    )
                    continue

                if payload.type == "end_turn":
                    await session.send(input=".", end_of_turn=True)
                    continue

    except WebSocketDisconnect:
        pass
    except HTTPException:
        raise
    except Exception as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "detail": f"Erro na sessao IA: {exc}"})
    finally:
        for task in (receive_task, keepalive_task):
            if task:
                task.cancel()
                with contextlib.suppress(Exception):
                    await task
