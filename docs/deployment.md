# Развёртывание PrimaryKit-проекта

PrimaryKit — шаблон. Деплоится **сгенерированный самостоятельный репозиторий**, не конструктор целиком.

## Локальный запуск

См. [пошаговый quickstart](getting-started.md). Основной путь: `cp .env.example .env`, `docker compose up -d db`, `uv sync --locked`, `makemigrations` (один раз в свежем клиентском проекте), `migrate`, `runserver`.

## Production checklist

1. Сгенерируйте проект, создайте миграции локально, проверьте и закоммитьте их. На production никогда не выполняйте `makemigrations`.
2. Настройте **PostgreSQL** с собственными пользователем/паролем, регулярными резервными копиями и проверкой восстановления.
3. Задайте сильный `DJANGO_SECRET_KEY`, реальные `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `DJANGO_TIME_ZONE`, настройки email/registration и S3 при использовании Storage. Не используйте тестовые секреты в `.env.example`.
4. Отключите `DEBUG`, используйте `config.settings.production`, проверьте `python manage.py check --deploy`.
5. Соберите production Docker image (`docker build --target production -f docker/Dockerfile .`) либо используйте Compose production override. Контейнер Django доступен Nginx только по локальному/внутреннему адресу.
6. Проведите TLS/HTTPS через nginx/Caddy/доверенный reverse proxy. Только если прокси очищает входящий `X-Forwarded-Proto`, включайте `DJANGO_TRUST_PROXY_SSL_HEADER=true`.
7. `python manage.py migrate` и `collectstatic` выполняйте контролируемым deploy job. Учтите зависимости пользовательской модели и порядок миграций.
8. Добавьте мониторинг `/health/live/`, `/health/ready/`, ошибки приложений и БД; ограничение входящего трафика и brute-force логинов.
9. Для S3/SeaweedFS: приватный bucket, доступ только из backend, ротация ключей, backups и периодическое тестирование upload/download.
10. Для платежей нужен **отдельный проверенный провайдер** с подписанными webhook-уведомлениями и реальной сверкой. Реализованный `payments` — только каркас PaymentIntent и ручная сверка суперпользователем; он не предназначен для реального приёма денег.

## Команды

```bash
# Сборка production-образа:
docker build --target production -t primarykit-app:latest -f docker/Dockerfile .

# Пример для отдельного клиентского деплоя после подготовки .env:
docker compose -f compose.prod.yaml run --rm api python manage.py migrate
docker compose -f compose.prod.yaml run --rm api python manage.py collectstatic --noinput
docker compose -f compose.prod.yaml up -d
```

Конкретные имена services и конфигурация proxy должны соответствовать Compose-файлу **вашего** сгенерированного проекта. Проверьте `docker compose ... config` перед запуском.

## Миграции и переносимость

- Исходный каталог PrimaryKit хранит варианты приложений, но **не готовые универсальные migrations** всех режимов.
- Свежий клиент создаёт/коммитит миграции один раз, затем версионирует их. Не пересоздавайте initial migrations после доставки в production.
- Catalog и Inventory имеют несовместимые `standalone`/`tenant` схемы. Смена режима требует отдельного migration design.
- Добавление нового модуля после деплоя требует ревью, проверки зависимостей, миграции, резервной копии и мониторинга.

Подробнее: [Storage](storage-architecture.md), [Organizations](organizations-architecture.md), [Users security](users-architecture.md).
