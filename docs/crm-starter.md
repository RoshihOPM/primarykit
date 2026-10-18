# CRM Starter

Профиль `--preset crm` собирает независимый backend с модулями Kanban и Leads.

```bash
uv run python scripts/new_project.py ../my-crm --name my-crm --preset crm
cd ../my-crm
uv run python manage.py makemigrations users audit storage organizations tasks kanban leads
uv run python manage.py migrate
```

JWT обязателен, данные ограничены владельцем. Модуль `leads` управляет
статусом лида независимо от доски. Перемещение карточки **не меняет** статус
лида автоматически: синхронизация — бизнес-правило клиентского проекта.

`POST /api/v1/kanban/cards/{id}/move/` принимает `target_column_id`
и `expected_version`. `POST /api/v1/leads/{id}/transition/` принимает
`status` и `expected_version`; устаревшая версия приводит к HTTP 409.

Ограничения: это не полноценная CRM и не Bitrix24. Нет фронтенда,
общекомандного доступа, универсального справочника контактов, сделок,
перетаскивания с переупорядочиванием, автоматизации и отчётов по воронке.
Установка Organizations не делает модули автоматически tenant-aware.
Персональные данные лидов требуют отдельной политики хранения и удаления.
Миграции создаются и коммитятся **в сгенерированном проекте**.
