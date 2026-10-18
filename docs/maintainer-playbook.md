# Maintainer and release playbook / Правила сопровождения и релизов

[English](#english) · [Русский](#русский)

## English

### 1. GitHub branch protection (owner action required)

**Current repository is private.** In the verified state, the GitHub API returned **403** for reading branch protection with the installed integration and **403 "Upgrade to GitHub Pro or make this repository public to enable this feature"** for rulesets. The connector does not expose a branch-protection write action. **This file alone does not protect the branch.**

For an eligible account/repository, open **Settings → Rules → Rulesets → New branch ruleset** (or **Settings → Branches → Add branch protection rule** where supported). Configure:

| Setting | Recommended |
| --- | --- |
| Target branch | `main` only |
| Enforcement | **Active**, not Evaluate/Disabled |
| Require pull request before merging | **On** |
| Required successful status check | **`test`** from **Core CI**; verify the exact check name in Actions |
| Keep branches up to date before merging | **On**, if CI capacity allows |
| Require conversation resolution | **On** |
| Dismiss stale approvals on new commits | **On** if approvals enabled |
| Required approving reviewers | **1 only when a separate trusted reviewer has write access**; otherwise don't deadlock a single-maintainer repo |
| Require Code Owners review | Enable only with an independent eligible code owner/reviewer |
| Force pushes and branch deletion | **Disallowed** |
| Bypass for administrators | **Disallowed** / enforce rules for administrators if the plan permits |
| Required signed commits / linear history | Optional; first verify merge strategy and contributor tooling |

Avoid **Lock branch**: it also prevents normal reviewed merges. Do not rely on `CODEOWNERS` or CI documentation as enforcement without a GitHub branch protection rule.

**If unavailable on a private GitHub Free repository:** upgrade to GitHub Pro (for this personal repo), or **after** a full-history secret/IP audit, make the repo public and use the Free public ruleset. Do **not** change visibility just to unlock protection without owner approval. [Official requirements](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

### 2. Pre-publication security and licensing gate

1. Identify every source contributor/copyright holder and verify redistribution rights. MIT in the root cannot relicense third-party files.
2. Scan **all refs and full Git history** offline with a reputable secrets scanner (e.g. `gitleaks git --log-opts="--all" .` on a trusted fully fetched clone, using its maintained usage syntax) plus a manual pass over configuration, private keys, archives and fixtures. CI secret scans cannot retroactively erase history.
3. Treat every confirmed historical credential as compromised: revoke/rotate in its real service and review accesses before publishing. Removing it from the tip is insufficient. Rewrite history only with careful coordination when necessary, then recheck all refs and forks.
4. Verify dependency alerts and public README/assets contain no client information or unlicensed imagery. Review external references and vendored code.
5. Enable GitHub private vulnerability reporting **after** publication (Security → Advisories → enable private vulnerability reporting), subscribe to notifications, and test that reporters can use the channel without public disclosure.
6. Verify branch protection is **actually active** via the GitHub UI/API. Test with a non-production PR; do not claim protected just because documentation exists.

### 3. PR merge gate

Every PR needs green `test` CI, review of changed files and dependency risks, security checks for sensitive code, docs consistency and tested generated-client migration policy. Dependabot update PRs follow the **same** gate. Never auto-merge security-sensitive dependency changes solely on a semver range.

### 4. Releases

- Select a reviewed commit in protected `main`.
- Run locked install, Ruff, Django checks, pytest and detached project smoke. For DB-dependent features, run PostgreSQL concurrency/integration tests.
- Confirm module changes, migration guidance, API breaking changes, known limitations and security advisories.
- Update version/changelog, create a tag and GitHub prerelease (e.g. `v0.1.0-beta.1`), with explicit limitations. **This repository is not ready to be described as production-certified.**
- Do not deploy or apply migrations to any customer environment as part of tagging this source catalog.

## Русский

### Защита `main`

В приватном репозитории GitHub API вернул **403** при чтении branch protection и **403** с требованием GitHub Pro либо публичного репозитория для rulesets; подключённый инструмент не предоставляет операцию изменения защиты ветки. **Наличие этого файла, CODEOWNERS или успешного CI само по себе не защищает `main`.**

При доступном тарифе откройте **Settings → Rules → Rulesets → New branch ruleset** (или **Settings → Branches → Add branch protection rule**): target `main`, Enforcement **Active**, обязательный PR, проверка **`test`** из **Core CI**, актуальность ветки, разрешение дискуссий, запрет force push/delete, запрет bypass администраторам. Требуйте 1 независимого reviewer только при наличии другого участника с доступом — иначе владелец не сможет смержить PR. **Lock branch** не включайте.

Если функция недоступна приватному GitHub Free, нужен GitHub Pro либо переход в Public **после** полноценного аудита и отдельного решения владельца. Не меняйте видимость без разрешения.

### Перед Public

Проверить авторство и лицензии всех файлов, всю историю и refs на секреты/данные клиентов, отозвать и перевыпустить выявленные ключи, проверить CI, GitHub Secret Scanning/Dependabot и реально действующее правило ветки. Git-история требует отдельного инструмента и ручного анализа; тестовый прогон CI не является подтверждением отсутствия утечек.

### PR и релизы

Перед merge: зелёный `test`, ревью, негативные проверки IDOR/тенантов, PostgreSQL races по необходимости, совместимость миграций сгенерированных проектов, обновление RU/EN документации. Для релиза: фиксированная версия и коммит, changelog, теги/prerelease с известными ограничениями, smoke и интеграционные тесты. Теги PrimaryKit **не** мигрируют и не деплоят клиентские приложения.
