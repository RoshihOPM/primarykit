# Offline Project Doctor

Этот инструмент расположен внутри копируемого `apps/core/doctor.py`. Он запускается после создания отдельного Django backend без исходного репозитория PrimaryKit, без настройки Django и без доступа к БД.

```bash
python -m apps.core.doctor
python -m apps.core.doctor --strict
python -m apps.core.doctor --json
python -m apps.core.doctor --root /path/to/client
```

**Exit code:** 0 — ошибок нет (с `--strict` также нет предупреждений); 1 — найдена проблема.

## Что проверяется

| Код | Тип | Причина |
| --- | --- | --- |
| `apps_missing`, `baseline_missing` | error | Отсутствуют базовые папки |
| `module_structure`, `invalid_manifest` | error | Нарушен контракт папки/manifest.py |
| `dependency_missing`, `dependency_cycle` | error | Обязательная зависимость отсутствует или цикл |
| `tenant_dependency_missing` | error | Tenant schema требует Organizations / Catalog |
| `schema_mode_unknown` | warning | Режим Catalog/Inventory нельзя статически определить |
| `kit_import`, `kit_dependency` | error | Runtime код/pyproject зависит от исходного конструктора |
| `settings_missing`, `pyproject_missing`, `invalid_pyproject` | error | Нарушена базовая структура проекта |
| `origin_invalid`, `origin_stale` | warning | Необязательные метаданные происхождения устарели |

Проверяются **только статические исходники**, никаких импортов бизнес-модулей, выполнения manifest, сетевых вызовов или автоматических исправлений. Каталог source kits можно проверить тем же способом.

## Что не проверяется

Отсутствие коллизий внутри Django URL patterns, реальное состояние миграций, доступность и схема БД, безопасность API, корректность функционала, разброс версий третьесторонних пакетов, TLS, внешние очереди и S3. Для этого нужны Django checks, миграционные тесты, PostgreSQL CI, review и production checklist.

Изменения бизнес-логики принадлежат клиентскому проекту; `doctor` не скачивает и не обновляет модули.
