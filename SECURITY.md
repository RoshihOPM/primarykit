# Security policy / Политика безопасности

[English](#english) · [Русский](#русский)

## English

PrimaryKit is a **source-copy project generator**, not a managed security service. Security of a generated application, its secrets, integrations and deployments remains the responsibility of the team operating that application.

**Reporting suspected vulnerabilities:** please **do not create a public GitHub issue or pull request** containing a working exploit, secrets, private client data or unreleased vulnerability details. Contact the repository maintainer through a private, verified channel or use GitHub's private vulnerability reporting **if and only if** the repository owner enables that feature. There is currently no published dedicated security email or promised response SLA.

A useful report includes the affected module and commit, a minimal reproduction with dummy data, the access-control or consistency impact, and mitigation ideas. Never test systems without permission.

This is an actively developed `0.1.0` source snapshot. Passing CI is not a guarantee of fitness for a production deployment. Before publishing this repository, the owner must independently review **full Git history** for secrets and rights to redistribute material.

## Русский

PrimaryKit — **генератор с копированием исходного кода**, а не сервис управляемой безопасности. За безопасность сгенерированного backend, его секретов, интеграций и окружения отвечает команда клиента.

**Сообщения об уязвимостях:** не создавайте публичные Issues/PR с эксплойтами, токенами, клиентскими данными или подробностями ещё не исправленной уязвимости. Используйте закрытый проверенный канал связи с владельцем репозитория либо приватные security-репорты GitHub, **если владелец активировал эту возможность**. Публичный адрес для security-обращений и SLA пока не установлены.

Укажите модуль, коммит, воспроизведение на тестовых данных, риск доступа/целостности и возможное исправление. Не проводите тесты чужих систем без разрешения.

Версия исходников `0.1.0` находится в разработке. Успешный CI не заменяет аудит конкретного production. Перед публикацией нужен отдельный аудит **всей истории Git** на секреты и права распространения.
