# Maintainer and release playbook / Правила сопровождения и релизов

[English](#english) · [Русский](#русский)

## English

### 1. GitHub branch protection (owner action required)

**Repository status (2026-10-21): Public (verified via GitHub repository metadata).** Public visibility makes free branch-protection features eligible, but **active enforcement has not been verified**. The installed integration cannot read or change protection settings. This guide and `CODEOWNERS` do not enable protection. Issue [#67](https://github.com/RoshihOPM/primarykit/issues/67) remains open until the owner verifies a live ruleset.

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

Now that the repository is public, configure protection directly in GitHub Settings; do not assume the old private-repository 403 still describes the current eligibility. Verify the rule is **Active** and targets only `main`, inspect the protected-branch state and test the rule using a safe non-production PR (do not try a destructive force push). Keep a dated screenshot or owner attestation and close #67 only after verification. [Official requirements](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

### 2. Post-publication security and licensing review (incomplete)

The repository has already been published, but the historical/IP audit is **not signed off** ([#68](https://github.com/RoshihOPM/primarykit/issues/68)). Publication does not constitute audit approval. Prior checks of accessible refs and an older successful automated scan are partial evidence, not confirmation of all Git objects. Complete the following as an urgent retroactive review:

1. Identify every source contributor/copyright holder and verify redistribution rights. MIT in the root cannot relicense third-party files.
2. Scan **all refs and full Git history** offline with a reputable secrets scanner (e.g. `gitleaks git --log-opts="--all" .` on a trusted fully fetched clone, using its maintained usage syntax) plus a manual pass over configuration, private keys, archives and fixtures. CI secret scans cannot retroactively erase history.
3. Treat every confirmed historical credential as compromised: revoke/rotate immediately at its source and review access. Removing it from the tip does not revoke already published history. Evaluate coordinated history rewrite and exposed clones/forks only after containment; then recheck refs.
4. Verify dependency alerts and public README/assets contain no client information or unlicensed imagery. Review external references and vendored code.
5. In **Settings → Security → Code security** verify Dependabot alerts and secret scanning availability. In **Security → Advisories** enable **private vulnerability reporting**, verify that **Report a vulnerability** appears to an external reporter, and subscribe to notifications. These repository settings are not configured by this document.
6. Verify branch protection is **actually active** via the GitHub UI/API. Check [#67](https://github.com/RoshihOPM/primarykit/issues/67). Record private audit evidence and maintainer sign-off; do not paste scanner findings, credentials or personal data into public tickets.

### 3. PR merge gate

Every PR needs green `test` CI, review of changed files and dependency risks, security checks for sensitive code, docs consistency and tested generated-client migration policy. Dependabot update PRs follow the **same** gate. Never auto-merge security-sensitive dependency changes solely on a semver range.

### 4. CI restoration and releases

**Issue [#99](https://github.com/RoshihOPM/primarykit/issues/99):** GitHub reported that Actions jobs were not admitted due to account payment or spending-limit restrictions while the repository was private. Public visibility does not prove the restriction is resolved. Check Actions jobs on a new commit, confirm at least one actual step ran, rerun **Core CI** and **Full History Secrets Audit**, and require green results before declaring recovery. Use the workflow's manual trigger if necessary. Never disable required checks to work around billing.

Release steps:

- Select a reviewed commit in protected `main`.
- Run locked install, Ruff, Django checks, pytest and detached project smoke. For DB-dependent features, run PostgreSQL concurrency/integration tests.
- Confirm module changes, migration guidance, API breaking changes, known limitations and security advisories.
- Update version/changelog, create a tag and GitHub prerelease (e.g. `v0.1.0-beta.1`), with explicit limitations. **This repository is not ready to be described as production-certified.**
- Do not deploy or apply migrations to any customer environment as part of tagging this source catalog.

## Русский

### Защита `main`

По состоянию на **21 октября 2026 года репозиторий публичный** (проверено по GitHub). Но действующий ruleset для `main` **не подтверждён**: подключённый инструмент не позволяет управлять защитой ветки или проверить настройки. **CODEOWNERS, этот документ и CI сами по себе не защищают `main`.** См. [#67](https://github.com/RoshihOPM/primarykit/issues/67).

При доступном тарифе откройте **Settings → Rules → Rulesets → New branch ruleset** (или **Settings → Branches → Add branch protection rule**): target `main`, Enforcement **Active**, обязательный PR, проверка **`test`** из **Core CI**, актуальность ветки, разрешение дискуссий, запрет force push/delete, запрет bypass администраторам. Требуйте 1 независимого reviewer только при наличии другого участника с доступом — иначе владелец не сможет смержить PR. **Lock branch** не включайте.

Поскольку репозиторий уже Public, настройте и включите (`Active`) ruleset в GitHub Settings. Проверьте действительное применение к `main` на безопасном тестовом PR и зафиксируйте результат. Не закрывайте #67 без подтверждения.

### После публикации — аудит пока не завершён

Репозиторий уже публичен, но [#68](https://github.com/RoshihOPM/primarykit/issues/68) остаётся открытым. Требуется полный клон и проверка всех доступных refs, возможных orphaned objects, истории на секреты и данные клиентов, лицензий и прав на код. Подтверждённые ключи нужно немедленно отозвать у провайдера и проверить доступы. Включить и проверить Dependabot alerts, private vulnerability reporting, secret scanning (при доступности); результат и подпись владельца хранить в закрытом аудиторском отчёте, без секретов в публичных Issues.

### CI, PR и релизы

[#99](https://github.com/RoshihOPM/primarykit/issues/99): GitHub ранее не запускал jobs из-за ограничений оплаты/лимитов аккаунта. Публичность сама по себе **не доказывает**, что CI заработал. Необходимо увидеть реальные шаги новых прогонов Core CI и Full History Secrets Audit и зелёные проверки. Не отключать обязательные проверки ради merge.


Перед merge: зелёный `test`, ревью, негативные проверки IDOR/тенантов, PostgreSQL races по необходимости, совместимость миграций сгенерированных проектов, обновление RU/EN документации. Для релиза: фиксированная версия и коммит, changelog, теги/prerelease с известными ограничениями, smoke и интеграционные тесты. Теги PrimaryKit **не** мигрируют и не деплоят клиентские приложения.
