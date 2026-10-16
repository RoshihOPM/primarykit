# Архитектурные рецепты для разных backend

Это **стартовые наборы исходников**, не обязательные шаблоны предметной области. Генерируется отдельная копия Django. Дальше каждый бизнес разрабатывает и версионирует собственные apps, модели, миграции, HTTP-контракты и deployment.

## 1. Персональный CRM / заявки

```bash
uv run python scripts/new_project.py ../crm-api --name crm-api --apps audit storage statistics
```

- Собственный контекст `leads`: заявка, pipeline, ответственный менеджер и ACL.
- Users — аутентификация; Audit — техническое журналирование; Storage — вложения.
- Не включайте Orders/Inventory без подтверждённых бизнес-требований.

## 2. Автомаркет / classifieds

```bash
uv run python scripts/new_project.py ../automarket-api --name automarket-api --apps audit storage statistics
```

- Создайте `listings`, `moderation`, `chats`, `promotions` как отдельные контексты.
- `listings` — не `catalog.Product` по умолчанию: другая модель владения, модерации и публикации.
- Для внутренней валюты нужен отдельный финансовый ledger, идемпотентность и транзакционные проверки; существующие Payments не являются TrustCredits/кошельком.

## 3. Корпоративный склад / B2B

```bash
uv run python scripts/new_project.py ../warehouse-api --name warehouse-api --apps organizations catalog inventory audit statistics
```

- Схема Catalog/Inventory закрепляется в `tenant` режиме **до первой миграции**.
- Организация и филиал являются границами доступа; свои бизнесовые заказы реализуются отдельно.
- Orders/Sales/Payments из каталога всё ещё личные; добавление Organizations не делает их корпоративными.

## 4. Небольшой API или сервис интеграции

```bash
uv run python scripts/new_project.py ../integration-api --name integration-api
```

- Только Core, Users, Notifications. Если нужна маленькая внутренняя очередь — выберите опциональный `tasks` и запустите worker; для высокого потока подбирайте очередь **по нагрузке и гарантиям доставки**. См. [Tasks](tasks-architecture.md).
- Не создавайте обязательный RabbitMQ, Redis, Celery или Kubernetes без требований к объёму/отказоустойчивости.

## После генерации

```bash
cd ../crm-api  # или каталог выбранного продукта
python -m apps.core.doctor --strict
uv sync --locked
uv run python manage.py makemigrations users
uv run python manage.py migrate
```

Список labels для миграций зависит от выбранных моделей. Команда в последнем примере указана только для минимального базового набора: при наличии Audit/Storage/Organizations и др. включите соответствующие labels. **Миграции должны храниться в клиентском Git**.

Никогда не передавайте «типовой» контекст за завершённую предметную бизнес-логику. См. [независимость](independent-projects.md), [доктор](doctor.md), [модульный контракт](module-development.md).
