# Changelog / История изменений

All notable PrimaryKit source changes are described here. Generated clients have independent release histories. See [maintainer playbook](docs/maintainer-playbook.md).

## [Unreleased]

### Added
- Reviewed acceptance for module upgrades (#89): `scripts/module_upgrade.py --apply-three-way --accept-reviewed MODULE... [--merged-path MODULE/PATH]... [--keep-client-migrations MODULE...]`. Contract files are still never written by the tool; a human places them in a client branch and the tool records the decision in `primarykit-origin.json`. Behaviour without the flags is unchanged.
- Migration history decision at acceptance (#88): a differing `bundled` history is refused unless the client keeps its applied history explicitly (`--keep-client-migrations` or an earlier `client` pin). `scripts/migration_adoption.py` reports `client_owned_history` for such a module.
- `scripts/release_baselines.json` and `scripts/ci_release_upgrade.py --baseline ID`: PostgreSQL upgrade scenario from three commit-pinned historical baselines, plus a `release-upgrades` CI matrix job. Scripted reviewer, six modules, no schema-changing upgrade; #88 and #89 remain open.
- Manifest `job_handlers`: modules declare their own background job handlers.

### Fixed
- Module upgrade apply modes verify source module bytes against the committed `HEAD` blobs: git-ignored or end-of-line-filtered files in the source checkout are refused instead of being copied and fingerprinted.

### Changed
- Django 6.1.3 (security fixes), pytest 9.2.0, ruff 0.17.5.

- Initial measured 75% aggregate commerce-test coverage gate (Orders, Sales, Payments), locked production dependency audit and focused Ruff security checks.
- Updated RU/EN project status and maintainer runbook with verified `main` ruleset and CI runs (2026-10-22); historical rights review remains open.
- MIT license, bilingual security, contribution and conduct policies.
- GitHub issue/PR templates, CODEOWNERS and weekly Dependabot configuration.
- Maintainer guidance for branch protection, full-history security review and prerelease gates.
- Generator guards against copying upstream maintainer identity/community templates into independent client repositories, while keeping MIT LICENSE.

### Notes
- Source project version remains `0.1.0`; this is **not** a published GitHub release.
- `main` ruleset is active (GitHub configuration); repository vulnerability-reporting settings and full history/IP audit still need independent verification.

## [Не выпущено]

- Принятие проверенных контрактных изменений при обновлении модулей (#89): `--apply-three-way --accept-reviewed`, `--merged-path`, `--keep-client-migrations`. Контрактные файлы инструмент по-прежнему не записывает; без флагов поведение прежнее.
- Решение об истории миграций при принятии (#88); статус `client_owned_history` в `scripts/migration_adoption.py`.
- `scripts/release_baselines.json` и `scripts/ci_release_upgrade.py`: сценарий обновления PostgreSQL-клиентов от трёх исторических коммитов и CI-задание `release-upgrades`. «Ревьюер» — скрипт, шесть модулей, обновлений с изменением схемы нет; #88 и #89 остаются открытыми.
- Поле manifest `job_handlers`: модуль сам объявляет обработчики фоновых заданий.
- Исправлено: режимы применения обновлений сверяют байты исходных модулей с закоммиченными объектами `HEAD`; игнорируемые Git файлы и файлы с изменёнными переводами строк отклоняются.
- Django 6.1.3 (исправления безопасности), pytest 9.2.0, ruff 0.17.5.
- Лицензия MIT, двуязычные SECURITY/CONTRIBUTING/Code of Conduct.
- GitHub-шаблоны, CODEOWNERS и Dependabot.
- Инструкция по защите main и аудиту Git-истории.
- Сгенерированные проекты получают текст MIT, но не настройки владельца исходной репы.

Релизы сгенерированных клиентов, их миграции и безопасность развёртывания остаются отдельной ответственностью.
