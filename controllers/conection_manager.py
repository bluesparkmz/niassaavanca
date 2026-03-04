from dataclasses import dataclass
from typing import Dict, Set

from fastapi import WebSocket


@dataclass
class Connection:
    id: int
    username: str | None
    name: str | None
    avatar: str | None
    websocket: WebSocket
    app_type: str = "unknown"


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, list[Connection]] = {}
        self.group_connections: Dict[int, Set[str]] = {}
        self.active_calls: Dict[str, dict] = {}

    async def connect(self, connection: Connection) -> None:
        await connection.websocket.accept()
        user_id = str(connection.id)
        first = user_id not in self.active_connections
        self.active_connections.setdefault(user_id, []).append(connection)
        if first:
            await self.broadcast_user_status(user_id, "online")

    async def disconnect(self, user_id: int, websocket: WebSocket | None = None) -> None:
        user_key = str(user_id)
        if user_key not in self.active_connections:
            return
        conns = self.active_connections[user_key]
        if websocket:
            conns = [c for c in conns if c.websocket is not websocket]
        else:
            conns = conns[:-1]
        if conns:
            self.active_connections[user_key] = conns
        else:
            self.active_connections.pop(user_key, None)
            await self.broadcast_user_status(user_key, "offline")

        for group_id in list(self.group_connections.keys()):
            self.group_connections[group_id].discard(user_key)
            if not self.group_connections[group_id]:
                self.group_connections.pop(group_id, None)

    def join_group(self, user_id: int, group_id: int) -> None:
        self.group_connections.setdefault(group_id, set()).add(str(user_id))

    def leave_group(self, user_id: int, group_id: int) -> None:
        if group_id in self.group_connections:
            self.group_connections[group_id].discard(str(user_id))
            if not self.group_connections[group_id]:
                self.group_connections.pop(group_id, None)

    async def send_personal(self, user_id: int, message: dict) -> None:
        user_key = str(user_id)
        for conn in self.active_connections.get(user_key, []):
            await conn.websocket.send_json(message)

    def is_user_online(self, user_id: int) -> bool:
        return str(user_id) in self.active_connections and len(self.active_connections[str(user_id)]) > 0

    async def send_group(self, group_id: int, message: dict) -> None:
        for member_id in self.group_connections.get(group_id, set()):
            for conn in self.active_connections.get(member_id, []):
                await conn.websocket.send_json(message)

    async def send_typing(self, from_user: int, to_user: int) -> None:
        await self.send_personal(
            to_user,
            {"type": "typing", "data": {"from_user": from_user}},
        )

    async def send_recording(self, from_user: int, to_user: int, status: str) -> None:
        await self.send_personal(
            to_user,
            {"type": "recording", "data": {"from_user": from_user, "status": status}},
        )

    def get_online_users(self) -> list[dict]:
        users = []
        for user_id, conns in self.active_connections.items():
            if not conns:
                continue
            conn = conns[0]
            users.append(
                {
                    "id": conn.id,
                    "username": conn.username,
                    "name": conn.name,
                    "avatar": conn.avatar,
                    "sessions": len(conns),
                }
            )
        return users

    async def broadcast_user_status(self, user_id: str, status: str) -> None:
        # Comentario: notifica todos os usuarios conectados.
        payload = {"type": "user_status", "data": {"user_id": user_id, "status": status}}
        for conns in self.active_connections.values():
            for conn in conns:
                try:
                    await conn.websocket.send_json(payload)
                except Exception:
                    pass

    async def create_video_call(self, from_user: int, to_user: int) -> str | None:
        import uuid

        to_user_key = str(to_user)
        if to_user_key not in self.active_connections:
            return None

        call_id = uuid.uuid4().hex
        self.active_calls[call_id] = {
            "caller_id": str(from_user),
            "receiver_id": to_user_key,
            "status": "ringing",
        }

        await self.send_personal(
            to_user,
            {"type": "video_call", "action": "incoming_call", "data": {"call_id": call_id, "from_user": from_user}},
        )
        await self.send_personal(
            from_user,
            {"type": "video_call", "action": "call_created", "data": {"call_id": call_id}},
        )
        return call_id

    async def handle_call_response(self, call_id: str, user_id: int, accepted: bool) -> bool:
        call = self.active_calls.get(call_id)
        if not call or call["receiver_id"] != str(user_id):
            return False
        call["status"] = "accepted" if accepted else "rejected"
        await self.send_personal(
            int(call["caller_id"]),
            {
                "type": "video_call",
                "action": "call_accepted" if accepted else "call_rejected",
                "data": {"call_id": call_id, "by_user": user_id},
            },
        )
        await self.send_personal(
            int(call["receiver_id"]),
            {
                "type": "video_call",
                "action": "call_accepted" if accepted else "call_rejected",
                "data": {"call_id": call_id, "by_user": user_id},
            },
        )
        if not accepted:
            self.active_calls.pop(call_id, None)
        return True

    async def relay_sdp(self, call_id: str, from_user: int, sdp: dict, kind: str) -> bool:
        call = self.active_calls.get(call_id)
        if not call or call["status"] != "accepted":
            return False
        to_user = call["receiver_id"] if str(from_user) == call["caller_id"] else call["caller_id"]
        await self.send_personal(
            int(to_user),
            {"type": "video_call", "action": kind, "data": {"call_id": call_id, "from_user": from_user, "sdp": sdp}},
        )
        return True

    async def relay_ice_candidate(self, call_id: str, from_user: int, candidate: dict) -> bool:
        call = self.active_calls.get(call_id)
        if not call or call["status"] != "accepted":
            return False
        to_user = call["receiver_id"] if str(from_user) == call["caller_id"] else call["caller_id"]
        await self.send_personal(
            int(to_user),
            {
                "type": "video_call",
                "action": "ice_candidate",
                "data": {"call_id": call_id, "from_user": from_user, "candidate": candidate},
            },
        )
        return True

    async def end_call(self, call_id: str, user_id: int) -> bool:
        call = self.active_calls.get(call_id)
        if not call:
            return False
        for pid in [call["caller_id"], call["receiver_id"]]:
            await self.send_personal(
                int(pid),
                {"type": "video_call", "action": "call_ended", "data": {"call_id": call_id, "ended_by": user_id}},
            )
        self.active_calls.pop(call_id, None)
        return True


global_connection_manager = ConnectionManager()
