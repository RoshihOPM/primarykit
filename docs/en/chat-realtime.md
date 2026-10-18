# Private chat and optional WebSocket transport (#50)

**Language:** English · [Русский](../chat-realtime.md) · [Docs index](README.md)

`chat` provides private 1:1 conversations via authenticated HTTP. `realtime` is an optional ASGI WebSocket adapter using PostgreSQL for event sequencing/replay. Neither installs Redis, RabbitMQ or Channels.

## Setup

```bash
uv run python scripts/new_project.py ../chat-api --name chat-api --apps chat realtime organizations storage
cd ../chat-api
uv run python manage.py makemigrations users organizations storage chat
uv run python manage.py migrate
```

Enable WebSockets only in an ASGI client deployment with `REALTIME_ENABLED=true` and an exact `REALTIME_ALLOWED_ORIGINS=https://frontend.example.com`. Configure an ASGI server and reverse proxy that supports WSS. Never expose JWT credentials through WS query parameters.

## Authenticated HTTP paths

- `GET/POST /api/v1/chats/` lists/creates an authorized two-person conversation, with `recipient_id` and optional `organization_id`.
- `GET /api/v1/chats/{id}/` gives accessible metadata and read cursors.
- `GET /api/v1/chats/{id}/messages/?after=0&limit=50` gives ascending sequence and a reconnect cursor.
- `POST /api/v1/chats/{id}/messages/` takes `body` and optional scoped `attachment_id`.
- `POST /api/v1/chats/{id}/read/` advances a monotonic read cursor.
- `GET /api/v1/chats/{id}/messages/{message_id}/attachment/` authorizes an optional Storage download.

Verified active users must be participants. Tenant dialogues require both participants to be active members of the same organization. Staff/superuser does not bypass membership. Attachments must be owned in the same scope.

## WebSocket contract

Connect to `/ws/v1/chats/{dialogue_uuid}/?after=0`. After accept, within five seconds send an authentication frame with `{"type":"authenticate","access_token":"JWT_ACCESS"}`. Success responds with `{"type":"ready","after":0}` followed by sequenced message events; write messages through HTTP. On reconnect resume using `after`, deduplicating by dialogue and sequence.

## Scaling and retention

`CHAT_RETENTION_DAYS=30` is a server-side default. Expired messages are invisible and need a scheduled `python manage.py purge_expired_chat` for physical deletion. Stored file lifecycle is separate.

Current WebSockets poll PostgreSQL about every **two seconds per connection**. Budget DB queries, auth checks, connection count and WSS/Origin controls before enabling. For high-concurrency realtime, explicitly design a pub/sub transport while preserving PostgreSQL sequence/replay and authorization.

[Detailed source reference (RU)](../chat-realtime.md).
