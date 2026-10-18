# Private Chat + Realtime (#50)

**Язык:** Русский · [English](en/chat-realtime.md) · [Оглавление](README.md)


`chat` (требует `users`) реализует 1:1 диалоги через HTTP.
`realtime` (требует `users`) добавляет необязательный ASGI WebSocket transport.
`organizations` и `storage` — необязательные зависимости. Нет автоматических
глобальных подписок, Redis, RabbitMQ или Channels.

## Генерация и миграции

```bash
uv run python scripts/new_project.py ../private-api --name private-api --apps chat realtime organizations storage
cd ../private-api
uv run python manage.py makemigrations users organizations storage chat
uv run python manage.py migrate
```

Client-проект хранит и версионирует **свои** миграции; source-каталог не содержит
исторических migrations. В существующем проекте любое добавление таблиц требует
review схемы и отдельного rollout. Индексы обеспечивают уникальность пары пользователей
в scope и последовательности сообщений в диалоге. `SELECT FOR UPDATE` защищает
счётчик `last_sequence` от одновременных авторов на PostgreSQL; SQLite не гарантирует
эквивалентных блокировок.

## HTTP контракт

Все адреса требуют аутентификации, verified email и участия в диалоге:

- `GET/POST /api/v1/chats/` — список/создание `{"recipient_id":"UUID","organization_id":"UUID|null"}`; повторное создание того же 1:1 диалога возвращает тот же ID.
- `GET /api/v1/chats/{id}/` — метаданные, `last_sequence`, последние прочитанные номера обоих участников.
- `GET /api/v1/chats/{id}/messages/?after=0&limit=50` — события с возрастанием sequence, `next_after` для reconnect.
- `POST /api/v1/chats/{id}/messages/` — `{"body":"text","attachment_id":"UUID|null"}`. Только автор сообщения задаёт текст и вложение, не sender/sequence/TTL.
- `POST /api/v1/chats/{id}/read/` — `{"sequence":12}`; счётчик чтения монотонный.
- `GET /api/v1/chats/{id}/messages/{message_id}/attachment/` — приватная передача файла из Storage.

Личный диалог доступен только двум участникам. Для tenant scope оба участника обязаны
состоять в одной активной Organization. При каждом запросе членство проверяется
заново; даже staff/superuser не получает доступа к чужим диалогам. Вложение может
прикрепить только его владелец и только в том же personal/tenant scope, где создан
диалог. Получатель скачивает через проверенный chat endpoint; после удаления
StoredFile скачивание становится недоступным. При отсутствии организаций или
хранилища соответствующая интеграция закрыта по умолчанию.

## WebSocket протокол (opt-in)

В клиентском Django-проекте задайте `REALTIME_ENABLED=true` и
`REALTIME_ALLOWED_ORIGINS=https://frontend.example.com` (точный allowlist Origin).
Запускайте ASGI-сервер, например с установленным uvicorn. WSGI WebSocket не
обслуживает. `/ws/v1/chats/{dialogue_uuid}/?after=0` подключается **только к одному**
явно указанному диалогу, без wildcard/global subscriptions.

После WebSocket accept за 5 секунд клиент отправляет
`{"type":"authenticate","access_token":"JWT_ACCESS"}`.
Токены не принимаются через query-string, cookies или subprotocol.
При успехе сервер отдаёт `{"type":"ready","after":0}` и затем
`{"type":"message","sequence":1,...}`. При reconnect клиент выставляет
последний обработанный `after` и устраняет дубликаты по (dialogue_id, sequence).
Все мутации выполняются по HTTP; произвольные WS кадры закрывают соединение.
JWT ограничен своим `exp`; активность пользователя и tenant membership проверяются
при каждом запросе событий. Срок истечения токена может потребовать переподключения.

## Retention, лимиты, масштабирование

`CHAT_RETENTION_DAYS=30` (серверный положительный integer).
Истёкшие сообщения не видны через REST/WS. Запустите периодически
`python manage.py purge_expired_chat` для физического удаления сообщений;
вложения принадлежат Storage и требуют отдельной retention политики/удаления,
включая резервные копии. Удаление сообщений не меняет монотонный sequence.

DRF ScopedRateThrottle — 30 POST/мин, 120 GET/мин на пользователя.
Встроенный LocMemCache ограничивает только один worker: в production требуются
shared/edge rate-limit по IP и identity, лимиты одновременных WebSocket-соединений,
Origin allowlist, TLS/WSS, мониторинг и алерты. На каждое WebSocket-соединение
идёт запрос к PostgreSQL примерно каждые 2 секунды; на 1000 клиентов получается
до 500 polls/с плюс отдельные проверки прав и пользователя. Этот адаптер подходит
для умеренного числа соединений, но не для массового realtime.
При существенном масштабе замените polling на event-driven pub/sub
(например, Channels + Redis) сохраняя PostgreSQL как источник истины и
sequence/replay контракт. Доставка не exactly-once: клиент обязан
дедуплицировать события, а после retention может возникнуть пропуск.
