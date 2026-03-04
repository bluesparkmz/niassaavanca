import requests


EXPO_PUSH_ENDPOINT = "https://exp.host/--/api/v2/push/send"


def is_expo_push_token(token: str | None) -> bool:
    if not token:
        return False
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


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

