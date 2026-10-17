"""Authenticated ASGI WebSocket transport for explicitly addressed private dialogues.

No implicit subscriptions. The database sequence is the authoritative cursor;
periodic reads work across workers without Redis, at a deliberate scaling cost.
"""

import asyncio
import json
import time
from urllib.parse import parse_qs
from uuid import UUID

from asgiref.sync import sync_to_async
from django.apps import apps as django_apps
from django.conf import settings

from apps.users.authentication import VerifiedJWTAuthentication

MAX_FRAME_BYTES = 8192


def _authenticate_access_token(raw_token):
    auth = VerifiedJWTAuthentication()
    validated = auth.get_validated_token(raw_token)
    return auth.get_user(validated), int(validated["exp"])


def _read_events(*, user_id, dialogue_id, after):
    from apps.chat.serializers import MessageReadSerializer
    from apps.chat.services import visible_messages
    from apps.users.models import User

    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or (
        getattr(settings, "AUTH_REQUIRE_EMAIL_VERIFICATION", True) and not user.email_verified
    ):
        raise PermissionError("Account is no longer active.")
    _, rows = visible_messages(actor=user, dialogue_id=dialogue_id, after=after, limit=50)
    return [{"type": "message", **MessageReadSerializer(row).data} for row in rows]


async def _close(send, code):
    await send({"type": "websocket.close", "code": code})


async def websocket_application(scope, receive, send):
    if not django_apps.is_installed("apps.chat"):
        return await _close(send, 4404)
    path = scope.get("path", "")
    parts = path.strip("/").split("/")
    if len(parts) != 4 or parts[:3] != ["ws", "v1", "chats"]:
        return await _close(send, 4404)
    try:
        dialogue_id = UUID(parts[3])
        query = parse_qs(scope.get("query_string", b"").decode("ascii"))
        if set(query) - {"after"} or len(query.get("after", [])) > 1:
            return await _close(send, 4400)
        after = int(query.get("after", ["0"])[0])
        if after < 0:
            return await _close(send, 4400)
    except (ValueError, UnicodeDecodeError, TypeError):
        return await _close(send, 4400)

    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    origin = headers.get(b"origin")
    allowed_origins = getattr(settings, "REALTIME_ALLOWED_ORIGINS", ())
    if origin is not None and origin.decode("latin1") not in allowed_origins:
        return await _close(send, 4403)
    if not getattr(settings, "REALTIME_ENABLED", False):
        return await _close(send, 4403)

    event = await receive()
    if event["type"] != "websocket.connect":
        return await _close(send, 4400)
    await send({"type": "websocket.accept"})
    # Access token is never accepted in URLs, logs or WebSocket subprotocols.
    try:
        first = await asyncio.wait_for(receive(), timeout=5)
        if first["type"] != "websocket.receive":
            return await _close(send, 4401)
        payload = first.get("text")
        if payload is None or len(payload.encode("utf-8")) > MAX_FRAME_BYTES:
            return await _close(send, 4400)
        credentials = json.loads(payload)
        if (
            not isinstance(credentials, dict)
            or set(credentials) != {"type", "access_token"}
            or credentials["type"] != "authenticate"
            or not isinstance(credentials["access_token"], str)
        ):
            return await _close(send, 4401)
        user, expires_at = await sync_to_async(_authenticate_access_token)(
            credentials["access_token"]
        )
        # Confirm access before emitting READY or any event metadata.
        await sync_to_async(_read_events)(user_id=user.pk, dialogue_id=dialogue_id, after=after)
    except Exception:
        # Authentication/authorization errors are intentionally indistinguishable.
        return await _close(send, 4401)

    await send({"type": "websocket.send", "text": json.dumps({"type": "ready", "after": after})})
    while True:
        if time.time() >= expires_at:
            return await _close(send, 4401)
        try:
            events = await sync_to_async(_read_events)(
                user_id=user.pk, dialogue_id=dialogue_id, after=after
            )
        except Exception:
            # Revoked membership, deleted dialogue, deactivated account -> no further data.
            return await _close(send, 4403)
        for event in events:
            await send({"type": "websocket.send", "text": json.dumps(event, default=str)})
            after = event["sequence"]
        try:
            inbound = await asyncio.wait_for(receive(), timeout=2)
        except TimeoutError:
            continue
        if inbound["type"] == "websocket.disconnect":
            return
        # Read-only transport. Writes and acknowledgments use the HTTP API.
        return await _close(send, 4400)
