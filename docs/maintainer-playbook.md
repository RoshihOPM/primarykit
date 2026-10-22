# Maintainer and release playbook / Правила сопровождения и релизов

[English](#english) · [Русский](#русский)

## English

### 1. GitHub branch protection (verified 2026-10-22)

[Ruleset 25549376](https://github.com/RoshihOPM/primarykit/rules/25549376) is **Active**, targets only `refs/heads/main`, requires pull requests (squash only), resolved conversations and **strict** successful `test` + `scan-history` checks. Branch deletion and non-fast-forward updates are blocked; no bypass actors are configured. [#67](https://github.com/RoshihOPM/primarykit/issues/67) is closed.

The required approving review count is **zero** to avoid deadlocking a one-maintainer repository. This is not an independent peer review; request a trusted second reviewer for security-sensitive changes and raise the minimum to 1 once they have write access. Re-verify protection after ruleset changes and periodically test enforcement with a safe PR. Never test destructive force pushes or disable required checks to force a merge.

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

### 4. CI evidence, security/coverage and releases

The previous runner-admission problem ([#99](https://github.com/RoshihOPM/primarykit/issues/99)) is resolved: [Core CI](https://github.com/RoshihOPM/primarykit/actions/runs/39726369491) and [Full History Secrets Audit](https://github.com/RoshihOPM/primarykit/actions/runs/39726369481) both completed successfully on `main` `df8282a` on 2026-10-22. Re-evaluate if jobs stop starting or a new PR fails.

The additional quality gates measure a 40% minimum **aggregate** coverage across Orders, Sales and Payments using SQLite tests and use `pip-audit` against exported, locked **production** dependencies. This is an initial regression floor, not a target level or proof of race safety. PostgreSQL integration tests remain mandatory in Core CI, especially for `select_for_update`. Extra Redis/Celery dependencies installed outside `uv.lock` require a separate audit. High-signal Ruff Bandit rules are enabled selectively; expand after reviewing baseline findings rather than suppressing new vulnerabilities.

Release steps:

- Select a reviewed commit in protected `main`; confirm current green checks with actual executed steps.
- Run locked install, Ruff, Django checks, pytest and detached project smoke; test PostgreSQL transaction races for DB-dependent changes.
- Confirm migrations, API breaking changes, third-party rights/history review, dependency advisories and security advisories.
- Update version/changelog, create a tag and GitHub prerelease (e.g. `v0.1.0-alpha.1`) only after risk sign-off. **This source catalog is not production-certified.**
- No releases or migrations should modify a customer environment automatically.

## Русский

### Защита `main`

**Проверено 22.10.2026:** [ruleset 25549376](https://github.com/RoshihOPM/primarykit/rules/25549376) активен только для `main`. Обязательны PR (только squash), разрешение обсуждений, актуальные проверки `test` и `scan-history`; force push, удаление ветки и обход правил запрещены. [#67](https://github.com/RoshihOPM/primarykit/issues/67) закрыт.

Число обязательных approvals — **0**, чтобы единственный сопровождающий мог работать. Это не независимое ревью; при появлении доверенного второго участника следует включить минимум 1 одобрение. После изменения правил перепроверяйте enforcement на безопасном PR.

### После публикации — аудит пока не завершён

[#68](https://github.com/RoshihOPM/primarykit/issues/68) **открыт**: автоматический Gitleaks на доступных refs уже проходит, но полный скан доверенного клона, возможных orphaned объектов, конфигураций, PII, архивов и прав на чужой код **не подписан**. Нужно проверить Dependabot alerts, secret scanning и private vulnerability reporting (где доступны). Подтверждённые секреты немедленно отзывать у провайдера. Не публикуйте значения секретов и личные данные в Issues.

### CI, PR и релизы

На `main` `df8282a` 22.10.2026 реально выполнены [Core CI](https://github.com/RoshihOPM/primarykit/actions/runs/39726369491) и [Full History Secrets Audit](https://github.com/RoshihOPM/primarykit/actions/runs/39726369481): оба успешны. [#99](https://github.com/RoshihOPM/primarykit/issues/99) закрыт.

Для PR: строго зелёные обязательные checks, просмотр diff и миграций, отрицательные тесты IDOR/tenant и PostgreSQL-конкурентности по риску, RU/EN документация. Первичный порог aggregate coverage денежной логики — **40%**, его нужно повышать после замера; SQLite не проверяет транзакционные гонки. `pip-audit` проверяет production lockfile, но не динамически устанавливаемые Redis/Celery пакеты. Выборочные Ruff S-правила не заменяют полноценный security-аудит. Для релиза нужны подтверждённые права на код, версионированные изменения, теги и явные ограничения.