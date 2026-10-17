# Production operations for generated client projects

Это справочный runbook. Он **не выполняет деплой, миграции или backup автоматически**. Каждый backend владеет конфигурацией и принимает отдельное решение о выпуске.

## Минимальная топология (1 VPS)

- Host Nginx + TLS -> `127.0.0.1:8000` -> Django/Gunicorn production container
- PostgreSQL доступен только из внутренней Docker-сети; `compose.prod.yaml` не публикует порт БД
- Опциональные RabbitMQ/Redis/Celery включаются отдельными Compose-файлами после review
- Storage: приватное S3-хранилище или осознанно разрешённый persistent local volume

Готовый пример конфигурации host Nginx — `deploy/nginx/primarykit.conf.example`. Замените домен, пути сертификатов и upstream; создайте и проверьте сертификат **до** включения HTTPS-сайта. Разрешайте входящие 80/443 только там, где это соответствует вашей схеме. Не открывайте PostgreSQL/Redis/RabbitMQ наружу.

На production используйте `DJANGO_SETTINGS_MODULE=config.settings.production`, сильные secrets, явные `DJANGO_ALLOWED_HOSTS` и `DJANGO_CSRF_TRUSTED_ORIGINS`. Включайте `DJANGO_TRUST_PROXY_SSL_HEADER=true` исключительно если доверенный proxy перезаписывает этот header. Сверьте `client_max_body_size` с лимитом upload и ограничениями upstream.

## Перед каждым релизом

1. Проверить locked dependencies, doctor, Ruff, Django `check --deploy` и тесты бизнес-модулей.
2. На staging с PostgreSQL выполнить миграции из **клиентского Git** и проверку обратной совместимости. Не запускать `makemigrations` на production.
3. Проверить резервную копию и последний успешный **test restore**. Отдельно резервировать S3/файлы и секреты; одного дампа PostgreSQL недостаточно.
4. Убедиться в наличии плана rollback и мониторинга `/health/live/` и `/health/ready/`.
5. Развёртывать через явный deploy job с остановкой при ошибках. Миграции необратимых изменений требуют expand/contract подхода.

## Резервная копия PostgreSQL (пример)

Для single-node `compose.prod.yaml` и установленных `pg_dump`:

```bash
docker compose -f compose.prod.yaml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > db-backup.dump
```

Храните дамп **вне VPS**, с шифрованием, ограничением доступа, retention и аудитом. Проверьте ненулевой размер, целостность (`pg_restore --list`) и регулярно восстанавливайте дамп в **отдельную пустую тестовую БД**; никогда не выполняйте необдуманный restore поверх production.

## Эксплуатационные границы

- При росте нагрузки вынесите PostgreSQL/Storage с хоста до горизонтального масштабирования API; настройте connection pool и мониторинг соединений.
- Не считайте память Redis долговечной. Критичные события доставляйте через Outbox; Celery задачи идемпотентны, delivery at-least-once.
- Локальный volume для файлов на одном VPS не пригоден для нескольких независимых API-нод без общего хранилища.
- Nginx/Compose из примера не предоставляют автоматический HA, секрет-хранилище, PITR или disaster recovery.
