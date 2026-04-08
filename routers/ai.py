import json
import os
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from groq import Groq

import schemmas
from auth import get_current_user

router = APIRouter(prefix="/ai", tags=["ai"])

TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "qwen/qwen3-32b")
APP_SYSTEM_INSTRUCTION = os.getenv(
    "AI_SYSTEM_INSTRUCTION",
    (
        "Voce e a Niassa AI, assistente oficial do app Niassa Avanca. "
        "Voce foi criada pela Bluespark MZ em parceria com O Destaque, proprietario da plataforma. "
        "Quando perguntarem quem te criou, quem te desenvolveu ou de quem e o app, explique isso com clareza: "
        "a Bluespark MZ e a empresa de desenvolvimento e O Destaque e o dono da plataforma Niassa Avanca. "
        "Ajude utilizadores com duvidas sobre posts, natureza, turismo, agricultura, uso do aplicativo e seguranca. "
        "Responda sempre em portugues simples, natural, objetiva e amigavel. "
        "Nao invente parcerias, empresas, autores ou tecnologias se isso nao tiver sido informado."
    ),
)


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY nao configurada")
    return Groq(api_key=api_key)


def _build_messages(payload: schemmas.AIChatRequest) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": APP_SYSTEM_INSTRUCTION}]
    for item in payload.history[-10:]:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": payload.message.strip()})
    return messages


def _extract_delta_text(chunk) -> str:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if not delta:
        return ""
    content = getattr(delta, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def _build_completion(client: Groq, payload: schemmas.AIChatRequest, stream: bool):
    return client.chat.completions.create(
        model=TEXT_MODEL,
        messages=_build_messages(payload),
        temperature=0.6,
        max_completion_tokens=4096,
        top_p=0.95,
        reasoning_effort="default",
        stream=stream,
        stop=None,
    )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=schemmas.AIChatResponse)
def chat_with_ai(
    payload: schemmas.AIChatRequest,
    current_user=Depends(get_current_user),
):
    _ = current_user
    client = _get_client()
    try:
        completion = _build_completion(client, payload, stream=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao comunicar com Groq: {exc}") from exc

    reply = (getattr(completion, "choices", [None])[0].message.content if getattr(completion, "choices", None) else "") or ""
    reply = reply.strip()
    if not reply:
        raise HTTPException(status_code=502, detail="Groq nao devolveu texto")
    return schemmas.AIChatResponse(reply=reply, model=TEXT_MODEL)


@router.post("/chat/stream")
def chat_with_ai_stream(
    payload: schemmas.AIChatRequest,
    current_user=Depends(get_current_user),
):
    _ = current_user
    client = _get_client()

    def event_stream() -> Iterator[str]:
        full_text = ""
        yield _sse_event("start", {"model": TEXT_MODEL})
        try:
            completion = _build_completion(client, payload, stream=True)
            for chunk in completion:
                delta_text = _extract_delta_text(chunk)
                if not delta_text:
                    continue
                full_text += delta_text
                yield _sse_event("delta", {"text": delta_text, "full_text": full_text})
            yield _sse_event("done", {"reply": full_text, "model": TEXT_MODEL})
        except Exception as exc:
            yield _sse_event("error", {"detail": f"Falha ao comunicar com Groq: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
