# Состояние проекта PrimaryKit

**Язык:** Русский · [English](en/project-status.md) · [Документация](README.md)

**Проверено 2 ноября 2026 г., `main` = `39f743f`:** репозиторий [публичный](https://github.com/RoshihOPM/primarykit), версия исходников `0.1.0`. Каталог `apps/` содержит **38 приложений** с `manifest.py`: 3 базовых и 35 выбираемых. PrimaryKit — copy-based генератор Django/DRF backend-проектов, а не production-сертифицированный framework.

## Реализовано

Генератор независимых проектов, наборы модулей, диагностика `doctor`, миграционное планирование, ограниченный opt-in three-way upgrade неконтрактных Python-файлов, проверка API-контрактов; переносимые модули пользователей, прав, задач, outbox, CRM и бизнес-примеры. Сгенерированный клиент владеет своим кодом, схемой БД, секретами и релизами. Полной автоматической миграции работающих клиентских схем нет: [#88](https://github.com/RoshihOPM/primarykit/issues/88) и [#89](https://github.com/RoshihOPM/primarykit/issues/89) остаются открыты.

## Проверки GitHub

- [Core CI, успешен](https://github.com/RoshihOPM/primarykit/actions/runs/40822782027) на `39f743f`, 29.10.2026: Django, Docker и матрица из девяти PostgreSQL-проектов прошли на GitHub Actions. Ранее заблокированный CI ([#99](https://github.com/RoshihOPM/primarykit/issues/99)) восстановлен.
- [Full History Secrets Audit, успешен](https://github.com/RoshihOPM/primarykit/actions/runs/40822782197) на том же коммите. Gitleaks на доступных fetched refs **не равен** ручному аудиту всех объектов Git и авторских прав.
- [Ruleset main](https://github.com/RoshihOPM/primarykit/rules/25549376) **Active**, target `refs/heads/main`: обязательный PR (squash), разрешение обсуждений, строгие обязательные проверки `test` и `scan-history`, запрет удаления и force push, bypass отсутствует. [#67](https://github.com/RoshihOPM/primarykit/issues/67) закрыт.
- Проверки качества: порог покрытия Orders/Sales/Payments 75% (не всего репозитория), аудит production-зависимостей, Ruff S и необязательный запуск закреплённых инструментов анализа кода. Истории `dev` и `main` согласованы, содержимое совпадает.

## Незакрытые ограничения

- [#68](https://github.com/RoshihOPM/primarykit/issues/68): **открыт**; полный trusted-clone анализ достижимых и осиротевших объектов, ручная проверка конфигураций/фикстур/PII и прав на сторонний код ещё **не подписаны**.
- [#88](https://github.com/RoshihOPM/primarykit/issues/88): история миграций исходных модулей/совместимость клиентов требует дополнительной проверки.
- [#89](https://github.com/RoshihOPM/primarykit/issues/89): ограниченный three-way merge реализован, но обновления между опубликованными версиями и сохранность данных старых PostgreSQL-клиентов ещё не подтверждены.
- Независимое code/security review, версия релиза и нагрузочное/отказоустойчивое тестирование не подтверждены.

Подробнее: [плейбук сопровождающего](maintainer-playbook.md), [чек-лист аудита](pre-public-audit.md), [политика безопасности](../SECURITY.md). Успешный CI не означает, что весь код готов к production.

## Невлитая ветка, 17 ноября 2026 г.

Не входит в снимок `main` выше; на GitHub Actions **не запускалось**.

- Принятие проверенных контрактных изменений: `--apply-three-way --accept-reviewed` ([#89](https://github.com/RoshihOPM/primarykit/issues/89)). Контрактные файлы инструмент по-прежнему не записывает; человек размещает их в ветке клиента, инструмент фиксирует решение в `primarykit-origin.json`.
- Решение об истории миграций при принятии, `--keep-client-migrations` ([#88](https://github.com/RoshihOPM/primarykit/issues/88)); статус `client_owned_history` в `scripts/migration_adoption.py`.
- `scripts/ci_release_upgrade.py` и `scripts/release_baselines.json`: обновление PostgreSQL-клиентов с данными от трёх исторических коммитов `main` до текущего каталога. Все три сценария прошли **локально** на PostgreSQL 16; CI-задание `release-upgrades` (PostgreSQL 17) добавляется в этой ветке и ещё не выполнялось.
- Зависимости: Django 6.1.3 (исправления безопасности), pytest 9.2.0, ruff 0.17.5.

Ограничения: «ревьюер» в сценарии — скрипт; базовые точки — коммиты, а не опубликованные релизы; модули `tasks`, `kanban`, `deals`, `inventory` (standalone), `orders`, `payments`; обновлений, меняющих схему, в истории нет. #88 и #89 остаются открытыми: нужны опубликованные версии с тегами, обновления реальных клиентов человеком, обновления с миграцией данных, другие `bundled`-модули, tenant-графы и проверка отката. #68 не затронут. Подробнее: [обновление модулей](module-updates.md).

Этот снимок описывает проверенный `main`; новые PR требуют самостоятельной проверки CI.
