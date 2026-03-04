import requests
from sqlalchemy.orm import Session

import models


EXPO_PUSH_ENDPOINT = "https://exp.host/--/api/v2/push/send"


def is_expo_push_token(token: str | None) -> bool:
    if not token:
        return False
    # Comentario: aceita apenas token de app standalone (bloqueia Expo Go).
    return token.startswith("ExpoPushToken[")


def send_expo_push(
    *,
    to_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    if not is_expo_push_token(to_token):
        return False

    payload = {
        "to": to_token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": data or {},
        "priority": "high",
    }
    try:
        response = requests.post(
            EXPO_PUSH_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        return response.status_code < 400
    except Exception:
        return False


def get_user_push_tokens(
    db: Session,
    user_id: int,
    legacy_token: str | None = None,
) -> list[str]:
    tokens: set[str] = set()

    device_tokens = (
        db.query(models.PushDevice.token)
        .filter(models.PushDevice.user_id == user_id)
        .all()
    )
    for row in device_tokens:
        token = row[0]
        if is_expo_push_token(token):
            tokens.add(token)

    if is_expo_push_token(legacy_token):
        tokens.add(legacy_token)  # type: ignore[arg-type]

    return list(tokens)
