# Public repository history and rights audit / Аудит публичного репозитория

**Status: NOT COMPLETE / НЕ ЗАВЕРШЕНО (2026-10-21).** The repository is already public. The visibility change does **not** establish that the complete Git history is free from secrets or that all source redistribution rights were verified. This is an urgent **retrospective audit**, tracked in [#68](https://github.com/RoshihOPM/primarykit/issues/68). Do not report it as completed without independent maintainer sign-off.

## Existing evidence and limits

- A previously successful [Full History Secrets Audit](https://github.com/RoshihOPM/primarykit/actions/runs/39574237988) scanned available branch, tag and PR refs at an older commit. It is not a scan of every later commit.
- Previous manual checks of the visible trees and documents did not identify real credentials or private customer files **in the inspected subset**; see the redacted [#68 progress note](https://github.com/RoshihOPM/primarykit/issues/68). This does not establish the safety of unreachable historical objects or author/license provenance.
- Earlier GitHub Actions runs were blocked before job execution by account billing/spending limits ([#99](https://github.com/RoshihOPM/primarykit/issues/99)). Public visibility alone does not demonstrate the restriction is lifted.

## Owner checklist (retain private evidence)

- [ ] Obtain a trusted full non-shallow clone; fetch all branch, tag and accessible GitHub PR refs. Enumerate refs and investigate any relevant unreachable/orphaned objects; record coverage and exclusions.
- [ ] Run `bash scripts/audit_git_history.sh` with a reviewed Gitleaks version. The narrow `.gitleaks.toml` allowance covers only a confirmed synthetic idempotency test fixture; do not add broad suppressions. Inspect potential findings **privately**.
- [ ] Rerun the GitHub [Full History Secrets Audit](https://github.com/RoshihOPM/primarykit/actions/workflows/history-security-audit.yml) on the **current** `main` and confirm real job steps executed and ended successfully.
- [ ] Review historical environment files, fixtures, uploaded files, archives, screenshots, external URLs and commit metadata for customer data, production hostnames and credentials.
- [ ] If a real secret is found, **revoke/rotate it immediately at the provider**, investigate its use and assess coordinated history cleanup. Public Git clones and forks may retain old objects even after a force rewrite.
- [ ] Verify original authorship, third-party licenses and redistribution permissions for every copied or vendored component. MIT at the repository root does not override others' licenses.
- [ ] In GitHub Settings confirm Dependabot alerts, secret scanning (where supported) and **private vulnerability reporting**. Test that an outside reporter can open a confidential report.
- [ ] Verify `main` protection is **Active** and effective (see [#67](https://github.com/RoshihOPM/primarykit/issues/67)).
- [ ] Complete the private dated audit record: refs, scanner version, results, excluded objects, reviewer and maintainer authorization. Close #68 only when its actual acceptance criteria are met.

Never put findings containing secrets, personal data or internal access information in public Issues, PRs or Actions logs.

## По-русски

Репозиторий **уже публичный**, однако [задача #68](https://github.com/RoshihOPM/primarykit/issues/68) по полной проверке истории и прав распространения **не завершена**. Успешная проверка одного старого коммита не охватывает изменения после него.

Владелец должен проверить полный локальный Git-клон и все доступные refs, вручную просмотреть возможные закрытые данные и права на сторонний код, повторно выполнить Gitleaks и GitHub Actions для актуального `main`. Реальные ключи необходимо сразу отозвать и перевыпустить у провайдера. Затем проверить настройки Dependabot, приватные сообщения об уязвимостях и активную защиту `main`. Подтверждения хранить **в приватном аудиторском отчёте**, не публикуя найденные секреты.
