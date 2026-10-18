# Security Policy / Политика безопасности

[English](#english) · [Русский](#русский)

## English

### Supported versions and scope

PrimaryKit currently has an actively developed **0.1.x** source line; it has not been declared a production-certified framework. Security fixes are considered for the current default branch, not for every historical snapshot or independent generated client repository. We do not promise a response or patch deadline.

In scope: security issues in PrimaryKit source code, its generator and provided apps, including cross-account/tenant access, JWT authorization, unsafe file access, SSRF, unsafe deserialization, secrets and concurrency vulnerabilities. A vulnerability in **client-specific** application logic or deployment configuration must also be assessed by that client's maintainers.

### Private vulnerability reporting

**Do not disclose an unpatched vulnerability in a public Issue, PR, Discussion, screenshot or log.**

1. After this repository becomes **public**, check [GitHub Security Advisories](https://github.com/RoshihOPM/primarykit/security/advisories). Use **Report a vulnerability** **only if private vulnerability reporting is enabled** by maintainers.
2. If that private reporting feature is unavailable, open a public issue with **only** the title "Request private security contact" and a request to establish a confidential channel. **Do not** include affected endpoints, exploit steps, tokens, PII or a vulnerability description in the issue.
3. Until a private channel is agreed, do not transmit sensitive details or run intrusive tests. GitHub itself provides a platform abuse-reporting mechanism for misconduct; it is not a substitute for disclosure to the maintainer.

There is **no dedicated public security email address** at present, and a GitHub profile is not automatically a secure private messaging channel.

### What to include after a private channel is established

- Affected commit/tag, module, environment and prerequisite configuration.
- Minimal reproduction against a **local disposable environment** using synthetic data; expected/actual behavior.
- Plausible confidentiality, integrity or availability impact; attacker's role and trust boundary.
- Suggested mitigation, if known. Remove passwords, real tokens, customer data and private infrastructure addresses.

Please allow maintainers to validate and fix issues privately before public disclosure. We may coordinate publication of a fix and advisory, but do not promise a CVE, support SLA, embargo length or bounty.

### Safe testing and deployment limitations

Do not scan or exploit third-party systems, real clients or production infrastructure without authorization. Do not submit sensitive data as test fixtures. Security-sensitive PRs require appropriate negative IDOR/BOLA tests, service-layer authorization, PostgreSQL concurrency checks and independent generated-client validation.

Using the source code under [MIT](LICENSE) does **not** transfer responsibility for hardening production clients. Each deployment still requires TLS, secure secrets, trusted proxies, backups/test-restores, logging policies, rate limiting and provider-specific verification. Scan **full Git history** for secrets and redistribution rights before switching visibility to public; scanning only the checkout is insufficient.

## Русский

### Поддерживаемые версии

PrimaryKit развивается в линии **0.1.x** и не позиционируется как готовый сертифицированный production framework. Исправления безопасности рассматриваются для актуальной основной ветки. Мы не гарантируем SLA, сроки выпуска патчей и поддержку старых версий либо независимых клиентских копий.

В области рассмотрения: уязвимости исходников/генератора PrimaryKit — IDOR/BOLA, межтенантный доступ, JWT, файлы, SSRF, секреты, гонки и небезопасная обработка данных. За безопасность собственной бизнес-логики и инфраструктуры отвечает команда сгенерированного проекта.

### Как сообщить конфиденциально

**Не публикуйте подробности неисправленной уязвимости в открытых Issues, PR и Discussions.**

1. После перехода репозитория в **Public** откройте [GitHub Security Advisories](https://github.com/RoshihOPM/primarykit/security/advisories) и выберите **Report a vulnerability**, **только если** владелец включил private vulnerability reporting.
2. Если такой функции нет, создайте публичный Issue **без технических подробностей** с темой "Request private security contact", запросив закрытый канал связи. Не отправляйте туда токены, данные клиентов, PoC или адреса уязвимых endpoint.
3. До согласования приватного канала не передавайте секреты и не проводите активные проверки посторонних систем.

Выделенного публичного security email пока нет; GitHub-профиль не является гарантированным приватным каналом.

### Что указать в закрытом сообщении

Коммит, модуль, окружение, минимальный PoC на локальных синтетических данных, ожидаемое/фактическое поведение, роль атакующего, влияние на конфиденциальность/целостность и возможное исправление. Не прикрепляйте реальные персональные данные, пароли и токены.

Поддерживайте согласованное раскрытие после проверки и исправления. CVE, награда и фиксированный срок реакции не гарантируются.

### Границы ответственности

Нельзя сканировать или эксплуатировать чужую инфраструктуру без разрешения. Для исправлений требуются негативные тесты авторизации, проверка границ доступа и PostgreSQL race tests там, где это необходимо.

MIT-лицензия не означает гарантии безопасности production. Клиент самостоятельно обеспечивает HTTPS, управление секретами, резервные копии с проверкой восстановления, ограничения запросов, аудит и проверку сторонних интеграций. Перед публикацией репозитория следует проверить **полную Git-историю** на секреты, приватные данные и права распространения исходников.
