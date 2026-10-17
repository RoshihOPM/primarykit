# API Keys — переносимые machine credentials

Модуль `api_keys` опционален, управляет **личными ключами**, не имеет публичных маршрутов и не подключается к глобальной DRF authentication. Клиент самостоятельно строит маршруты выдачи/отзыва с подтверждённой JWT/session авторизацией, CSRF, role/tenant policy и edge rate limiting.

## Модель безопасности

- 256-битный secret генерируется `secrets.token_urlsafe(32)` и показывается только при создании; база хранит SHA-256 digest, подходящий **только для случайных высокоэнтропийных ключей**, не пользовательских паролей.
- Формат `pk_<uuidhex>.<secret>` использует публичный UUID для индексируемого lookup; сверка digest выполняется через `hmac.compare_digest`.
- Проверяются срок истечения, отзыв, active/email-verified owner, необходимый scope и **актуальный Django permission** владельца. Пустой `API_KEY_SCOPE_PERMISSIONS` по умолчанию запрещает все scopes.
- Конфигурация проекта: `API_KEY_SCOPE_PERMISSIONS = {"reports.read": "reports.view_report"}`. Метод `issue_api_key(actor=user, name="integration", scopes=("reports.read",), expires_at=aware_datetime)` возвращает `(record, token)` и требует `user.has_perm("reports.view_report")`. Максимальный срок 90 дней и до 16 разных scopes.
- Отзыв `revoke_api_key(actor=user, key_id=key.pk)` проверяет владельца под `select_for_update`; ротация `rotate_api_key(actor=user, key_id=key.pk, expires_at=aware_datetime)` атомарна и немедленно блокирует старый ключ. Для безостановочного переноса сначала выпускают новый, переводят клиентов и отдельно отзывают предыдущий.

## Использование в DRF

Только на конкретном view явно задайте `authentication_classes = [scoped_api_key_authentication("reports.read")]` вместе с `permission_classes = [IsAuthenticated]`. Не включайте этот класс во все `DEFAULT_AUTHENTICATION_CLASSES`: scope локален для endpoint, а не глобальный токен с доступом ко всему аккаунту. Следующий слой должен независимо проверить, имеет ли владелец доступ к конкретной организации, филиалу и ресурсу. Scope не заменяет tenant membership / object-level permissions.

Не помещайте секреты в URL/query string, логи, Audit, response после первичной выдачи, events или exceptions. Требуются HTTPS и ограничение попыток подбора на ingress/Redis; в коде предельное обновление `last_used_at` — раз в 10 минут. При отзыве последующие запросы отвергаются, но уже выполняющийся запрос может завершиться.

## Клиентские миграции и эксплуатация

Ключевые таблицы требуют `makemigrations users api_keys` в **созданном клиентском репозитории** с review/commit; source PrimaryKit не хранит универсальную историю миграций. Архитектура персональная — корпоративное владение ключами требует отдельного organization policy adapter и отрицательных IDOR-тестов.

Нет публичных issuance endpoints, автоматического управления организациями или фонового удаления записей. Операторы должны настроить retention/revocation, аудит и monitoring, прежде чем открыть функцию для пользователей.
