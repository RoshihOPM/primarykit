import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from apps.core.module_registry import (
    dependency_closure,
    discover_modules,
    migration_apps,
)
from scripts.new_project import OPTIONAL_APPS, SOURCE_ROOT, create_project, project_plan
from scripts.presets import PRESETS


@pytest.mark.parametrize(
    "apps",
    [
        set(),
        {"audit"},
        {"storage"},
        {"orders"},
        {"sales"},
        {"payments"},
        {"tasks"},
        {"privacy"},
        {"listings"},
        {"favorites"},
        {"observability"},
        {"feature_flags"},
        {"search"},
        {"csv_exchange"},
        {"api_keys"},
        {"idempotency"},
        {"http_integrations"},
        {"outbox"},
        {"workflows"},
        {"webhooks"},
        {"cache"},
        {"rate_limit"},
        {"celery_tasks"},
        {"realtime"},
        {"chat"},
        {"chat", "realtime"},
        {"chat", "organizations", "storage", "realtime"},
        {"cache", "celery_tasks"},
        {"orders", "sales", "payments"},
        {"statistics", "orders", "sales", "payments"},
        {"statistics"},
        {"statistics", "catalog"},
        {"statistics", "inventory"},
        {"statistics", "organizations"},
        {"rbac"},
        {"catalog"},
        {"inventory"},
        {"organizations"},
        {"organizations", "audit"},
        {"inventory", "audit"},
        {"catalog", "storage"},
        {"audit", "storage", "rbac", "catalog", "inventory", "organizations"},
    ],
)
def test_project_generator_scopes_apps_and_urls(tmp_path, apps):
    target = create_project(tmp_path / "demo-api", name="demo-api", optional_apps=apps)
    assert target.is_dir()
    assert (target / "apps" / "core").exists()
    assert (target / "apps" / "users").exists()
    assert (target / "apps" / "notifications").exists()
    selected = dependency_closure(
        discover_modules(), {"core", "users", "notifications"} | set(apps)
    )
    for app in (
        "rbac",
        "audit",
        "storage",
        "catalog",
        "inventory",
        "organizations",
        "orders",
        "sales",
        "payments",
        "tasks",
        "privacy",
        "listings",
        "favorites",
        "observability",
        "feature_flags",
        "search",
        "csv_exchange",
        "api_keys",
        "idempotency",
        "http_integrations",
        "outbox",
        "workflows",
        "webhooks",
        "cache",
        "rate_limit",
        "celery_tasks",
        "chat",
        "realtime",
    ):
        assert (target / "apps" / app).exists() == (app in selected)

    settings = (target / "config/settings/base.py").read_text()
    urls = (target / "config/urls.py").read_text()
    assert ('CATALOG_MODE = "tenant"' in settings) == (
        "catalog" in selected and "organizations" in selected
    )
    assert ('INVENTORY_MODE = "tenant"' in settings) == (
        {"inventory", "catalog", "organizations"} <= selected
    )
    assert "*installed_module_apps()" in settings
    assert "module_routes()" in urls
    for name in selected:
        assert (target / "apps" / name / "manifest.py").is_file()
    for name in set(discover_modules()) - selected:
        assert not (target / "apps" / name).exists()

    assert 'name = "demo-api"' in (target / "pyproject.toml").read_text()
    assert 'name = "demo-api"' in (target / "uv.lock").read_text()
    assert '"TITLE": "demo-api API"' in settings
    assert not (target / "scripts").exists()
    assert not (target / "apps/core/tests/test_project_generator.py").exists()
    assert not (target / "apps/core/tests/test_doctor.py").exists()
    assert (target / "apps/core/doctor.py").is_file()
    assert not (target / ".git").exists()
    assert not (target / ".env").exists()
    assert (target / ".env.example").exists()
    assert (target / "compose.seaweedfs.yaml").exists() == ("storage" in apps)
    assert (target / "compose.redis.yaml").exists() == bool(
        {"cache", "celery_tasks", "rate_limit"} & apps
    )
    assert (target / "compose.celery.yaml").exists() == ("celery_tasks" in apps)
    assert (target / "compose.celery.prod.yaml").exists() == ("celery_tasks" in apps)
    if "cache" in apps:
        assert "REDIS_CACHE_KEY_PREFIX=demo-api-dev" in (target / ".env.example").read_text()
    readme = (target / "README.md").read_text()
    assert ("uv add 'redis>=8,<9'" in readme) == (
        "cache" in selected and "celery_tasks" not in selected
    )
    assert ("'redis>=6.2,<6.5'" in readme) == (
        {"cache", "celery_tasks"} <= apps or "celery_tasks" in apps
    )
    assert ("uv add 'celery>=5.6,<6'" in readme) == ("celery_tasks" in apps and "cache" not in apps)

    metadata = json.loads((target / "primarykit-origin.json").read_text())
    assert set(metadata["included_apps"]) == selected
    assert set(metadata["module_fingerprints"]) == selected
    for name in selected:
        assert metadata["module_fingerprints"][name]["manifest.py"]
    source_project = tomllib.loads((SOURCE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["source_version"] == source_project["project"]["version"]
    assert ("Feature flags: configure FEATURE_FLAGS" in readme) == ("feature_flags" in apps)
    # The client workflow is one dedicated file, identical for every selection.
    assert (target / ".github/workflows/ci.yaml").read_bytes() == (
        SOURCE_ROOT / "scripts/templates/client-ci.yaml"
    ).read_bytes()
    assert [p.name for p in (target / ".github").rglob("*") if p.is_file()] == ["ci.yaml"]
    assert not (target / "README.ru.md").exists()
    assert project_plan(requested_apps=set(apps))["migrations"] == [
        name for name in migration_apps() if name in selected
    ]
    if "storage" in selected:
        assert (target / "apps/storage/tests/test_personal_storage.py").exists()
        assert (target / "apps/storage/tests/test_storage.py").exists()
    if "listings" in selected:
        assert 'STORAGES["listings_private"]' in settings
        assert (target / "apps/listings/tests/test_media.py").exists()
    if "chat" in selected:
        assert (target / "apps/chat/tests/test_chat.py").exists()
    if "realtime" in selected:
        assert (target / "apps/realtime/asgi.py").exists()
    if "favorites" in selected:
        assert (target / "apps/listings").is_dir()
        assert (target / "apps/favorites/tests/test_favorites.py").exists()


def _settings_job_handlers(project):
    code = (
        "import json, django; django.setup();"
        "from django.conf import settings;"
        "from apps.tasks.services import _handlers;"
        "print(json.dumps([settings.BACKGROUND_JOB_HANDLERS, _handlers()]))"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    run = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project,
        env={**env, "DJANGO_SETTINGS_MODULE": "config.settings.test"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.splitlines()[-1])


def test_generated_project_registers_module_owned_job_handlers(tmp_path):
    target = create_project(
        tmp_path / "jobs-api", name="jobs-api", optional_apps={"outbox", "privacy"}
    )
    base = target / "config/settings/base.py"
    settings = base.read_text()
    assert "BACKGROUND_JOB_HANDLERS = module_job_handlers()" in settings
    assert '"apps.outbox" in INSTALLED_APPS' not in settings
    assert '"apps.privacy" in INSTALLED_APPS' not in settings
    expected = {
        "outbox.dispatch": "apps.outbox.services.dispatch",
        "privacy.execute": "apps.privacy.services.process_retention_job",
    }
    assert _settings_job_handlers(target) == [expected, expected]

    # A client base.py generated before manifests owned handlers still works
    # with upgraded core and manifests: the duplicated registration is a no-op.
    legacy = (
        "BACKGROUND_JOB_HANDLERS = {}\n"
        'if "apps.outbox" in INSTALLED_APPS:\n'
        '    BACKGROUND_JOB_HANDLERS["outbox.dispatch"] = "apps.outbox.services.dispatch"\n'
        'if "apps.privacy" in INSTALLED_APPS:\n'
        "    PRIVACY_RETENTION_POLICIES = {}\n"
        "    PRIVACY_AUTO_EXECUTION_ENABLED = False\n"
        '    BACKGROUND_JOB_HANDLERS["privacy.execute"] = (\n'
        '        "apps.privacy.services.process_retention_job"\n'
        "    )"
    )
    base.write_text(
        settings.replace("BACKGROUND_JOB_HANDLERS = module_job_handlers()", legacy).replace(
            "    module_job_handlers,\n", ""
        )
    )
    assert "module_job_handlers" not in base.read_text()
    assert _settings_job_handlers(target) == [expected, expected]

    bare = create_project(tmp_path / "bare-api", name="bare-api", optional_apps={"tasks"})
    assert _settings_job_handlers(bare) == [{}, {}]


def test_generator_rejects_existing_directory_and_invalid_input(tmp_path):
    target = tmp_path / "backend"
    target.mkdir()
    with pytest.raises(FileExistsError):
        create_project(target, name="good-backend")
    with pytest.raises(ValueError):
        create_project(tmp_path / "not-created", name="../bad project")
    with pytest.raises(ValueError):
        create_project(tmp_path / "not-created", name="good-backend", optional_apps={"unknown"})


def test_generator_does_not_keep_secret_env_or_git_folders(tmp_path):
    dest = create_project(tmp_path / "client-backend", name="client-backend")
    assert not (dest / ".git").exists()
    assert not (dest / ".env").exists()
    assert not (dest / ".venv").exists()
    assert not (dest / "media").exists()
    assert not (dest / "privatefiles").exists()


@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_generator_preset_portability_and_modes(tmp_path, preset):
    plan = project_plan(requested_apps=set(), preset=preset)
    assert set(plan["included_apps"]) >= {"core", "users", "notifications"}
    target = create_project(tmp_path / preset, name="preset-backend", preset=preset)
    metadata = json.loads((target / "primarykit-origin.json").read_text())
    assert metadata["preset"] == preset
    assert metadata["included_apps"] == plan["included_apps"]
    for name in set(discover_modules()) - set(plan["included_apps"]):
        assert not (target / "apps" / name).exists()


def test_dry_run_and_presets_do_not_write_files(tmp_path, capsys, monkeypatch):
    from scripts.new_project import main

    target = tmp_path / "does-not-exist"
    monkeypatch.setattr(
        "sys.argv",
        ["new_project.py", str(target), "--name", "dry-api", "--preset", "crm", "--dry-run"],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["preset"] == "crm"
    assert "organizations" in result["included_apps"]
    assert not target.exists()


def test_generated_client_keeps_license_not_upstream_governance(tmp_path):
    target = create_project(tmp_path / "client-api", name="client-api")
    source_license = (SOURCE_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert source_license.startswith("MIT License")
    assert (target / "LICENSE").read_text(encoding="utf-8") == source_license
    assert "preserve the included LICENSE" in (target / "README.md").read_text(encoding="utf-8")
    for source_only in (
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "README.ru.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/workflows/quality-tools.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE",
        "docs/maintainer-playbook.md",
        "CHANGELOG.md",
    ):
        assert not (target / source_only).exists(), source_only


def test_bundled_migration_folders_preserved_only_when_declared(monkeypatch):
    from apps.core.module_registry import Module
    from scripts import new_project

    monkeypatch.setitem(
        new_project.AVAILABLE_MODULES,
        "fake_versioned",
        Module("fake_versioned", migration_policy="bundled"),
    )
    assert "migrations" not in new_project._ignore_excluded(
        "/root/apps/fake_versioned", ["migrations"]
    )
    assert "migrations" in new_project._ignore_excluded(
        "/root/apps/fake_unversioned", ["migrations"]
    )


def test_generator_racing_creator_does_not_delete_unowned_destination(tmp_path, monkeypatch):
    """The destination must be claimed exclusively before cleanup is allowed."""
    destination = tmp_path / "raced-backend"
    original_mkdir = Path.mkdir

    def competing_creator(path, *args, **kwargs):
        if path == destination:
            original_mkdir(path, *args, **kwargs)
            (path / "belongs-to-other-process.txt").write_text("keep me", encoding="utf-8")
            raise FileExistsError("another process claimed the destination")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_creator)
    with pytest.raises(FileExistsError, match="another process"):
        create_project(destination, name="raced-backend")

    assert (destination / "belongs-to-other-process.txt").read_text(encoding="utf-8") == "keep me"


def test_generator_failed_copy_removes_only_claimed_destination(tmp_path, monkeypatch):
    from scripts import new_project

    destination = tmp_path / "failed-backend"
    neighbor = tmp_path / "existing-neighbor"
    neighbor.mkdir()
    (neighbor / "keep.txt").write_text("keep me", encoding="utf-8")

    def fail_partway(_source, target, **kwargs):
        assert kwargs["dirs_exist_ok"] is True
        assert target.is_dir()
        (target / "partial.txt").write_text("incomplete", encoding="utf-8")
        raise OSError("simulated partial copy failure")

    monkeypatch.setattr(new_project.shutil, "copytree", fail_partway)
    with pytest.raises(OSError, match="partial copy"):
        create_project(destination, name="failed-backend")

    assert not destination.exists()
    assert (neighbor / "keep.txt").read_text(encoding="utf-8") == "keep me"


def test_generated_project_includes_ub_mode(tmp_path):
    target = create_project(tmp_path / "client-api", name="client-api")
    skill = target / ".agents" / "skills" / "ub-mode" / "SKILL.md"
    assert skill.is_file()
    assert "original PrimaryKit adaptation" in skill.read_text(encoding="utf-8")
    assert ".agents/skills/ub-mode/SKILL.md" in (target / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("ignored_name", [".quality-tools", ".metrics", "target"])
def test_generated_client_excludes_optional_quality_artifacts(tmp_path, ignored_name):
    from scripts import new_project

    assert ignored_name in new_project._ignore_excluded("/path/to/source", [ignored_name])
    project = create_project(tmp_path / "client", name="client-api")
    assert not (project / ignored_name).exists()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_generator_rejects_source_symlinks_before_creating_destination(tmp_path, monkeypatch, kind):
    from scripts import new_project

    source = create_project(tmp_path / "source", name="source-api", optional_apps={"audit"})
    external = tmp_path / "outside"
    external.mkdir()
    if kind == "file":
        secret = external / "private.py"
        secret.write_text("PRIVATE = True\n", encoding="utf-8")
        (source / "apps" / "audit" / "external.py").symlink_to(secret)
    else:
        (source / "apps" / "audit" / "external").symlink_to(external, target_is_directory=True)

    monkeypatch.setattr(new_project, "SOURCE_ROOT", source)
    destination = tmp_path / "client"
    with pytest.raises(ValueError, match="symlinked source path"):
        new_project.create_project(destination, name="client-api", optional_apps={"audit"})
    assert not destination.exists()


def test_generator_refuses_symlink_added_during_copy_and_preserves_external_file(
    tmp_path, monkeypatch
):
    from scripts import new_project

    destination = tmp_path / "client"
    external = tmp_path / "unrelated.py"
    external.write_text("DO_NOT_TOUCH = True\n", encoding="utf-8")
    original_copytree = new_project.shutil.copytree

    def inject_during_copy(source, target, **kwargs):
        assert kwargs["symlinks"] is True
        # Restore stdlib copytree so its recursive calls do not hit this hook.
        monkeypatch.setattr(new_project.shutil, "copytree", original_copytree)
        result = original_copytree(source, target, **kwargs)
        replaced = target / "config" / "settings" / "base.py"
        replaced.unlink()
        replaced.symlink_to(external)
        return result

    monkeypatch.setattr(new_project.shutil, "copytree", inject_during_copy)
    with pytest.raises(ValueError, match="symlinked source path"):
        new_project.create_project(destination, name="client-api")
    assert not destination.exists()
    assert external.read_text(encoding="utf-8") == "DO_NOT_TOUCH = True\n"


def test_generator_excludes_untrusted_symlinks_in_ignored_source_dirs(tmp_path):
    import shutil

    from scripts import new_project

    source = tmp_path / "source"
    source.mkdir()
    (source / "safe.py").write_text("SAFE = True\n", encoding="utf-8")
    external = tmp_path / "outside"
    external.mkdir()
    (source / ".git").symlink_to(external, target_is_directory=True)

    new_project._reject_source_symlinks(source)
    target = shutil.copytree(source, tmp_path / "client", ignore=new_project._ignore_excluded)
    assert (target / "safe.py").read_text(encoding="utf-8") == "SAFE = True\n"
    assert not (target / ".git").exists()


def test_generator_copy_allowlist_rejects_unknown_root_and_maintainer_assets(tmp_path):
    import shutil

    from scripts import new_project

    source = tmp_path / "source"
    shutil.copytree(
        new_project.SOURCE_ROOT,
        source,
        ignore=new_project._selected_copy_ignore(
            new_project.SOURCE_ROOT, set(new_project.AVAILABLE_MODULES)
        ),
    )
    # Files may be accidentally added to an otherwise trusted checkout.
    (source / "database-backup.sql").write_text("PRIVATE CLIENT DATA\n", encoding="utf-8")
    (source / "local-artifacts").mkdir()
    (source / "local-artifacts" / "credentials.txt").write_text(
        "PRIVATE CLIENT DATA\n", encoding="utf-8"
    )
    # .github is not client material, so the copied tree has none of it.
    assert not (source / ".github").exists()
    (source / ".github" / "workflows").mkdir(parents=True)
    (source / ".github" / "workflows" / "maintainer-only.yml").write_text(
        "name: private\n", encoding="utf-8"
    )

    ignored_module = source / "apps" / "audit"
    external = tmp_path / "external"
    external.write_text("PRIVATE CLIENT DATA\n", encoding="utf-8")
    (ignored_module / "private.py").symlink_to(external)

    root_filter = new_project._selected_copy_ignore(source, {"core", "users", "notifications"})
    assert "database-backup.sql" in root_filter(str(source), ["database-backup.sql"])
    assert "audit" in root_filter(str(source / "apps"), ["audit"])
    assert "maintainer-only.yml" in root_filter(
        str(source / ".github" / "workflows"), ["maintainer-only.yml"]
    )

    # An unsafe link in an unselected app must not be read or copied.
    from scripts import new_project as generator

    previous_source = generator.SOURCE_ROOT
    try:
        generator.SOURCE_ROOT = source
        client = generator.create_project(tmp_path / "client", name="client-api")
    finally:
        generator.SOURCE_ROOT = previous_source

    assert not (client / "database-backup.sql").exists()
    assert not (client / "local-artifacts").exists()
    assert not (client / "apps" / "audit").exists()
    assert not (client / ".github" / "workflows" / "maintainer-only.yml").exists()
    assert not (client / ".github" / "workflows" / "history-security-audit.yml").exists()
    assert not (client / "scripts").exists()
    assert (client / ".github" / "workflows" / "ci.yaml").is_file()
    assert (client / "apps" / "core" / "manifest.py").is_file()


CLIENT_CI_CASES = {
    "minimal": {"preset": "minimal"},
    "commerce": {"preset": "commerce"},
    "all": {"optional_apps": set(OPTIONAL_APPS)},
}
_MD_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_MD_FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)


def _workflow_file_references(text: str) -> set[str]:
    """Paths a workflow command needs on disk, including -m modules and settings."""
    found = set(
        re.findall(r"(?<![\w./-])(?:apps|config|docs|deploy|docker|scripts)/[\w./-]+", text)
    )
    found |= set(re.findall(r"(?<![\w./-])[\w.-]+\.(?:py|ya?ml|toml|json|lock|sh)\b", text))
    for dotted in re.findall(r"(?:-m |--settings=|--ds=)((?:apps|config|scripts)(?:\.\w+)+)", text):
        found.add(dotted.replace(".", "/") + ".py")
    return found


def _missing_markdown_targets(project: Path) -> list[str]:
    missing = []
    for document in sorted(project.rglob("*.md")):
        text = _MD_FENCE.sub("", document.read_text(encoding="utf-8"))
        for link in _MD_LINK.findall(re.sub(r"`[^`\n]*`", "", text)):
            path = link.split("#")[0].split("?")[0]
            if not path or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", path):
                continue
            base = project if path.startswith("/") else document.parent
            if not (base / path.lstrip("/")).exists():
                missing.append(f"{document.relative_to(project)} -> {link}")
    return missing


def test_markdown_link_checker_detects_copied_source_only_links(tmp_path):
    """Guard the checker itself: the source tree minus its policies has broken links."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text(
        "[ok](index.md) [gone](../SECURITY.md) `[code](nope.md)`\n\n```\n[x](fenced.md)\n```\n",
        encoding="utf-8",
    )
    assert _missing_markdown_targets(tmp_path) == ["docs/index.md -> ../SECURITY.md"]
    assert _missing_markdown_targets(SOURCE_ROOT / "docs" / "adr") == []


@pytest.mark.parametrize("case", sorted(CLIENT_CI_CASES))
def test_generated_client_workflow_and_docs_are_self_contained(tmp_path, case):
    target = create_project(tmp_path / case, name="client-api", **CLIENT_CI_CASES[case])
    raw = (target / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)

    assert workflow["permissions"] == {"contents": "read"}
    assert ": write" not in raw and "write-all" not in raw
    assert "scripts/" not in raw and "PRIMARYKIT" not in raw
    assert list(workflow["jobs"]) == ["test"]
    job = workflow["jobs"]["test"]
    assert "permissions" not in job
    assert job["services"]["postgres"]["image"] == "postgres:17-alpine"
    assert job["env"]["DATABASE_URL"].startswith("postgresql://")
    assert [step["uses"].split("@")[0] for step in job["steps"] if "uses" in step] == [
        "actions/checkout",
        "astral-sh/setup-uv",
    ]

    commands = "\n".join(step["run"] for step in job["steps"] if "run" in step)
    for expected in (
        "uv sync --locked --all-groups",
        "uv run python -m apps.core.doctor --strict",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "--check --dry-run --settings=config.settings.postgres_test",
        "uv run python manage.py check --settings=config.settings.postgres_test",
        "uv run pytest -q --ds=config.settings.postgres_test",
    ):
        assert expected in commands, expected
    # A client owns its migration history: CI may only verify, never write it.
    for line in commands.splitlines():
        assert "makemigrations" not in line or "--check --dry-run" in line or "echo" in line, line
    assert "migrate" not in commands.replace("makemigrations", "")
    assert "docker" not in commands
    migration_step = next(s for s in job["steps"] if "makemigrations" in s.get("run", ""))
    assert "commit your migrations" in migration_step["name"]
    assert "commit your migrations" in migration_step["run"]

    references = _workflow_file_references(raw)
    assert {"manage.py", "apps/core/doctor.py", "apps/core/migration_plan.py"} <= references
    assert "config/settings/postgres_test.py" in references
    for reference in sorted(references):
        assert (target / reference).exists(), reference
    # Only the always-copied core may be named: every selection gets the same file.
    assert set(re.findall(r"apps[./](\w+)", raw)) == {"core"}
    assert not re.findall(r"compose[\w.-]*\.ya?ml", raw)

    assert _missing_markdown_targets(target) == []
    assert (target / "docs" / "README.md").is_file()
    assert not (target / "docs" / "maintainer-playbook.md").exists()


def test_missing_link_targets_keep_text_and_leave_code_untouched(tmp_path):
    from scripts import new_project

    (tmp_path / "docs").mkdir()
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    document = tmp_path / "docs" / "index.md"
    document.write_text(
        "See [policy](../SECURITY.md), [license](../LICENSE#mit), [web](https://example.test/a.md)"
        " and `[code](../SECURITY.md)`.\n\n```bash\necho [x](../SECURITY.md)\n```\n"
        "![image](missing.png) [anchor](#top)\n",
        encoding="utf-8",
    )
    new_project._unlink_missing_markdown_targets(tmp_path)
    assert document.read_text(encoding="utf-8") == (
        "See policy, [license](../LICENSE#mit), [web](https://example.test/a.md)"
        " and `[code](../SECURITY.md)`.\n\n```bash\necho [x](../SECURITY.md)\n```\n"
        "![image](missing.png) [anchor](#top)\n"
    )


def test_generator_fails_closed_without_client_workflow_template(tmp_path, monkeypatch):
    from scripts import new_project

    monkeypatch.setattr(new_project, "CLIENT_WORKFLOW_TEMPLATE", tmp_path / "absent.yaml")
    with pytest.raises(RuntimeError, match="workflow template missing"):
        new_project.create_project(tmp_path / "client", name="client-api")
    assert not (tmp_path / "client").exists()


def test_source_workflow_has_no_client_subtraction_markers():
    source = (SOURCE_ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    assert "PRIMARYKIT-" not in source
    assert "uv run pytest -q scripts/tests\n" in source
    assert not re.findall(r"scripts/tests/test_\w+\.py", source)
    generator = (SOURCE_ROOT / "scripts/new_project.py").read_text(encoding="utf-8")
    assert "PRIMARYKIT-" not in generator
