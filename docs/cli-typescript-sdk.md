# PrimaryKit CLI и TypeScript SDK (v1)

**Язык:** Русский · [English](en/cli-typescript-sdk.md)

## Архитектура

CLI — независимый Python-модуль в `apps/core/cli.py`. Он **копируется в созданный backend** и использует уже существующие генератор, installer, doctor и отчёт обновления. Дополнительный сервис, runtime-пакет PrimaryKit, Node или очереди Django не нужны.

Запуск: `python -m apps.core.cli` (или `uv run python -m apps.core.cli`). **Глобальная команда `primarykit` через pip/pipx пока не устанавливается.**

### Создание проекта из каталога

```bash
uv run python -m apps.core.cli new ../crm-api --preset crm --dry-run
uv run python -m apps.core.cli new ../crm-api --preset crm --git-init
```

Команда `new` доступна **только в исходном каталоге**, поскольку генератор не копируется в клиентские репозитории. Имя по умолчанию берётся из директории проекта и проверяется существующим генератором. Миграции не запускаются.

### Команды внутри независимого backend

```bash
cd ../crm-api
python -m apps.core.cli modules list --json
python -m apps.core.cli doctor --strict
python -m apps.core.cli add listings --source ../primarykit --dry-run
python -m apps.core.cli add listings --source ../primarykit
python -m apps.core.cli upgrade --source ../primarykit --dry-run --json
```

`add` требует **доверенного** исходного каталога и вызывает `manage.py install_kit_module` без автоматических миграций. После подключения модуля нужно проверить diff, создать и закоммитить миграции, вручную выполнить rollout. `upgrade` в этом CLI **только показывает изменения**; никаких `--apply-safe` или `--apply-three-way` он не запускает. Созданный клиент не зависит от исходного PrimaryKit в runtime.

## TypeScript SDK из OpenAPI

Для Vue 3, React и другого TS frontend SDK генерируется **из OpenAPI выбранного backend**, а не из всего каталога. Источник — `manage.py spectacular` (DRF Spectacular), альтернатива — локальный файл YAML/JSON через `--schema`.

Генератор создаёт два файла: `schema.d.ts` (типы API) и `client.ts` (`createPrimaryKitClient(baseUrl)` поверх `openapi-fetch`). Для работы Node-инструменты должны быть установлены **в самом frontend** и закреплены в его lockfile:

```bash
cd ../frontend
npm install openapi-fetch
npm install -D openapi-typescript typescript
cd ../crm-api
python -m apps.core.cli sdk typescript --frontend ../frontend --out src/api --dry-run
python -m apps.core.cli sdk typescript --frontend ../frontend --out src/api
```

В frontend:

```typescript
import { createPrimaryKitClient } from "./api/client";

const api = createPrimaryKitClient(import.meta.env.VITE_API_URL);
// Вызывайте типизированный URL, присутствующий в OpenAPI именно вашего backend.
```

**Что остаётся за разработчиком:** стратегия refresh JWT, безопасное хранение токенов, настройка middleware, CORS/CSP, обработка ошибок и retries, TypeScript typecheck (`npx tsc --noEmit`) в CI, проверка breaking changes. SDK — это клиент HTTP, а не готовый Vue-интерфейс.

### Безопасность и ограничения

- `--dry-run` выводит план без записи файлов или запуска Django/Node.
- `--out` обязан находиться внутри указанного frontend. Перезапись `schema.d.ts` и `client.ts` заблокирована без явного `--force`.
- Генерация проходит во временной директории, ошибки экспорта схемы/Node не меняют существующие файлы.
- Python CLI не скачивает npm-пакеты, не использует внешние OpenAPI URL и не устанавливает зависимости. При этом **локальные Node зависимости должны быть доверенными**; для схем с внешними `$ref` нужна отдельная проверка.
- Никаких production-миграций, деплоя, публикации npm-пакета и автоматической синхронизации frontend.

После изменения API повторяйте генерацию, проверяйте diff и компиляцию TypeScript.
