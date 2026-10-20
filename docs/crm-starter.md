# CRM Starter — независимые модули

```bash
uv run python scripts/new_project.py ../my-crm --name my-crm --preset crm
cd ../my-crm
uv run python manage.py makemigrations users audit storage organizations tasks kanban leads contacts deals
uv run python manage.py migrate
```

Шаблон собирает **четыре независимых модуля**: Kanban, Leads, Contacts,
Deals. Прямых зависимостей и связей моделей между ними нет. Каждый можно
установить отдельно через `--apps` вместе с обязательным базовым Users.

Все API требуют JWT и ограничивают данные владельцем. Organizations/RBAC не
включают командные права для этих модулей автоматически.

- `/api/v1/kanban/boards/`, `columns/`, `cards/` — доски, колонки, карточки
- `POST /api/v1/kanban/cards/{id}/move/` — `target_column_id`,
  `expected_version`, необязательный `position` (от нуля)
- `/api/v1/leads/` — лиды, фильтры `?status=new&source=website`, `/{id}/transition/`
- `/api/v1/contacts/` — независимые контакты, фильтр `?company=Acme`
- `/api/v1/deals/` — сделки и `/{id}/transition/` для смены стадии

У лида есть необязательное `assigned_to`. Без Organizations назначить можно\nтолько себя; с Organizations — также активного участника общей активной\nорганизации. **Назначение не выдаёт прав чтения или редактирования:**\nвладельцем данных остаётся создатель. При подключённом Audit изменения\nлида записываются в журнал.\n\nДля редактирования применяется `PATCH` с `expected_version`;
конфликт возвращает HTTP 409. У сделок суммы хранятся в целых минимальных
денежных единицах: это не платёжный процессинг.

Это backend starter, а не законченный Bitrix24. Нет фронтенда,
совместных досок, автоматической связи сделок и лидов, командных прав,
удаления персональных данных, аналитики воронки и платёжных операций.
Такие правила и интеграции реализуются внутри сгенерированного проекта.
Миграции генерируются и коммитятся клиентом.
