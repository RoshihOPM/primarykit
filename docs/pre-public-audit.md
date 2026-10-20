# Pre-publication audit checklist / Аудит перед открытием репозитория

**NOT COMPLETED / НЕ ЗАВЕРШЕНО.** Merging the history-scanning workflow does
not authorize publication or mean that the repository has no leaked credentials.

## Maintainer verification — private

1. From a trusted full clone, fetch all branch refs, tags and GitHub PR refs
   (including old closed PR refs where GitHub still exposes them). Verify no
   shallow history. Review unreachable objects separately if available.
2. Run `bash scripts/audit_git_history.sh` with reviewed Gitleaks v8.30.1 or newer.
   The CI job `Full History Secrets Audit` also scans fetched refs using a
   checksum-verified Gitleaks binary. Review any results **privately**.
3. Manually inspect historical environment files, binary archives, uploads,
   screenshots, URLs, fixtures and commit metadata for customer data and secrets.
4. For every real credential discovered: revoke/rotate at the provider, review
   access logs, and assess history rewriting before external publication.
5. Verify authorship, licenses, redistributability and notices for **every**
   copied or vendor asset; MIT does not confer rights over third-party code.
6. Verify Dependabot alerts and GitHub private vulnerability reporting
   availability. Check external URLs and README contents.
7. Record scan date, tool version, scanned refs and evidence of reviewer
   sign-off in a **private** audit record. Never paste keys or scanner raw
   findings into GitHub Issues, PRs or public logs.
8. Only after audit completion, owner approval and actual protection of
   `main`, consider changing repository visibility.

## По-русски

Публикация **запрещена до завершения** полной проверки истории Git и PR refs,
ручной проверки авторских прав/данных клиентов, отзыва всех найденных ключей,
подтверждения правил защиты `main` и решения владельца. Автоматический
Gitleaks не заменяет ручное ревью и не проверяет недоступные orphaned objects.
