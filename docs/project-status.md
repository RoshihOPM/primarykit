# Состояние проекта PrimaryKit

**Язык:** Русский · [English](en/project-status.md) · [Документация](README.md)

**Проверено 22 октября 2026 г., `main` = `df8282a`:** репозиторий [публичный](https://github.com/RoshihOPM/primarykit), версия исходников `0.1.0`. Каталог `apps/` содержит **38 приложений** с `manifest.py`: 3 базовых и 35 выбираемых. PrimaryKit — copy-based генератор Django/DRF backend-проектов, а не production-сертифицированный framework.

## Реализовано

Генератор независимых проектов, наборы модулей, диагностика `doctor`, миграционное планирование, ограниченный opt-in upgrade неконтрактных файлов, проверка API-контрактов; переносимые модули пользователей, прав, задач, outbox, CRM и бизнес-примеры. Сгенерированный клиент владеет своим кодом, схемой БД, секретами и релизами. Полной автоматической миграции работающих клиентских схем нет: [#88](https://github.com/RoshihOPM/primarykit/issues/88) и [#89](https://github.com/RoshihOPM/primarykit/issues/89) остаются открыты.

## Проверки GitHub

- [Core CI, успешен](https://github.com/RoshihOPM/primarykit/actions/runs/39726369491) на `df8282a`, 22.10.2026: реальные GitHub-hosted jobs исполняются, включая PostgreSQL matrix. Ранее заблокированный CI ([#99](https://github.com/RoshihOPM/primarykit/issues/99)) восстановлен.
- [Full History Secrets Audit, успешен](https://github.com/RoshihOPM/primarykit/actions/runs/39726369481) на том же коммите. Gitleaks на доступных fetched refs **не равен** ручному аудиту всех объектов Git и авторских прав.
- [Ruleset main](https://github.com/RoshihOPM/primarykit/rules/25549376) **Active**, target `refs/heads/main`: обязательный PR (squash), разрешение обсуждений, строгие обязательные проверки `test` и `scan-history`, запрет удаления и force push, bypass отсутствует. [#67](https://github.com/RoshihOPM/primarykit/issues/67) закрыт.
- Дополняем quality gates: измерение покрытия Orders/Sales/Payments (начальный минимум 40%, не показатель полного покрытия), аудит production-зависимостей по `uv.lock` и высокосигнальные правила Ruff S.

## Незакрытые ограничения

- [#68](https://github.com/RoshihOPM/primarykit/issues/68): **открыт**; полный trusted-clone анализ достижимых и осиротевших объектов, ручная проверка конфигураций/фикстур/PII и прав на сторонний код ещё **не подписаны**.
- [#88](https://github.com/RoshihOPM/primarykit/issues/88): история миграций исходных модулей/совместимость клиентов требует дополнительной проверки.
- [#89](https://github.com/RoshihOPM/primarykit/issues/89): upgrade с версионированным three-way merge не завершён.
- Независимое code/security review, версия релиза и нагрузочное/отказоустойчивое тестирование не подтверждены.

Подробнее: [плейбук сопровождающего](maintainer-playbook.md), [чек-лист аудита](pre-public-audit.md), [политика безопасности](../SECURITY.md). Успешный CI не означает, что весь код готов к production.

Этот снимок отражает **main до новых PR**. Фактический статус последующих изменений нужно сверять с их CI.
