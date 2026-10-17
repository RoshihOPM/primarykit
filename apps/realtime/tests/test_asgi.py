"""WebSocket negative-auth, Origin and reconnect replay tests."""

import asyncio
import json

import pytest
from django.apps import apps as django_apps
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.realtime.asgi import websocket_application
from apps.users.models import User

pytestmark = pytest.mark.django_db(transaction=True)


async def connection(path, frames, *, query=b"", origin=None):
    sent = []
    queue = asyncio.Queue()
    for frame in frames:
        queue.put_nowait(frame)

    async def receive():
        return await queue.get()

    async def send(payload):
        sent.append(payload)

    headers = [(b"origin", origin.encode())] if origin else []
    await websocket_application(
        {"type": "websocket", "path": path, "query_string": query, "headers": headers},
        receive,
        send,
    )
    return sent


@override_settings(REALTIME_ENABLED=True, REALTIME_ALLOWED_ORIGINS=("https://example.test",))
def test_ws_rejects_foreign_origins_and_tokens_in_query():
    if not django_apps.is_installed("apps.chat"):
        pytest.skip("Chat module is not installed.")
    path = "/ws/v1/chats/00000000-0000-0000-0000-000000000001/"
    assert asyncio.run(connection(path, [], origin="https://evil.test"))[-1]["code"] == 4403
    assert asyncio.run(connection(path, [], query=b"token=bad"))[-1]["code"] == 4400


@override_settings(REALTIME_ENABLED=False)
def test_ws_requires_opt_in():
    path = "/ws/v1/chats/00000000-0000-0000-0000-000000000001/"
    expected = 4403 if django_apps.is_installed("apps.chat") else 4404
    assert asyncio.run(connection(path, []))[-1]["code"] == expected


@override_settings(REALTIME_ENABLED=True)
def test_ws_anonymous_connection_never_gets_ready():
    if not django_apps.is_installed("apps.chat"):
        pytest.skip("Chat module is not installed.")
    path = "/ws/v1/chats/00000000-0000-0000-0000-000000000001/"
    frames = [
        {"type": "websocket.connect"},
        {
            "type": "websocket.receive",
            "text": json.dumps({"type": "authenticate", "access_token": "wrong"}),
        },
    ]
    result = asyncio.run(connection(path, frames))
    assert result[-1]["code"] == 4401
    assert all(item["type"] != "websocket.send" for item in result)


@override_settings(REALTIME_ENABLED=True)
def test_ws_verified_scope_replay_and_other_user_denial():
    if not django_apps.is_installed("apps.chat"):
        pytest.skip("Chat module is not installed.")
    from apps.chat.services import create_dialogue, send_message

    user = User.objects.create_user(
        email="ws-member-a@example.test", password="long-password-728", email_verified=True
    )
    friend = User.objects.create_user(
        email="ws-member-b@example.test", password="long-password-728", email_verified=True
    )
    stranger = User.objects.create_user(
        email="ws-member-c@example.test", password="long-password-728", email_verified=True
    )
    chat = create_dialogue(actor=user, recipient_id=friend.pk)
    send_message(actor=user, dialogue_id=chat.pk, body="hello")
    path = f"/ws/v1/chats/{chat.pk}/"

    def frames(who):
        return [
            {"type": "websocket.connect"},
            {
                "type": "websocket.receive",
                "text": json.dumps(
                    {
                        "type": "authenticate",
                        "access_token": str(RefreshToken.for_user(who).access_token),
                    }
                ),
            },
            {"type": "websocket.disconnect"},
        ]

    accepted = asyncio.run(connection(path, frames(user)))
    received = [json.loads(item["text"]) for item in accepted if item["type"] == "websocket.send"]
    assert [item["type"] for item in received] == ["ready", "message"]
    assert received[1]["sequence"] == 1
    assert received[1]["body"] == "hello"
    replay = asyncio.run(connection(path, frames(friend), query=b"after=1"))
    assert [
        json.loads(item["text"])["type"] for item in replay if item["type"] == "websocket.send"
    ] == ["ready"]
    blocked = asyncio.run(connection(path, frames(stranger)))
    assert blocked[-1]["code"] == 4401
    assert all(item["type"] != "websocket.send" for item in blocked)


def test_realtime_without_chat_fails_closed():
    if django_apps.is_installed("apps.chat"):
        pytest.skip("Real-time only project required.")
    path = "/ws/v1/chats/00000000-0000-0000-0000-000000000001/"
    assert asyncio.run(connection(path, []))[-1]["code"] == 4404
