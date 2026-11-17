"""Release baseline registry and upgrade-scenario guards without a live database."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts.ci_release_upgrade import REGISTRY, ROOT, load_baselines, run_baseline
from scripts.new_project import OPTIONAL_APPS


def _registry(tmp_path, **overrides) -> Path:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data.update(overrides)
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_registry_pins_three_distinct_full_commits_and_known_apps():
    apps, baselines = load_baselines()
    assert len(baselines) >= 3
    assert len(set(baselines.values())) == len(baselines)
    assert all(re.fullmatch(r"[0-9a-f]{40}", commit) for commit in baselines.values())
    assert set(apps) <= OPTIONAL_APPS


def test_ci_matrix_runs_every_registered_baseline():
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text(encoding="utf-8")
    listed = re.search(r"baseline: \[([^\]]+)\]", workflow)
    assert listed is not None
    assert {item.strip() for item in listed.group(1).split(",")} == set(load_baselines()[1])


def test_registered_baselines_are_ancestors_when_history_is_available():
    shallow = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shallow.returncode != 0 or shallow.stdout.strip() != "false":
        pytest.skip("Full Git history is required to verify baseline ancestry")
    for commit in load_baselines()[1].values():
        present = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"], check=False
        )
        if present.returncode != 0:
            pytest.skip("Baseline commit is not fetched into this clone")
        assert (
            subprocess.run(
                ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
                check=False,
            ).returncode
            == 0
        )


@pytest.mark.parametrize(
    "baselines",
    [
        [],
        [{"id": "one", "commit": "a" * 40}, {"id": "two", "commit": "b" * 40}],
        [
            {"id": "one", "commit": "a" * 40},
            {"id": "two", "commit": "b" * 40},
            {"id": "tag", "commit": "v0.1.0"},
        ],
        [
            {"id": "one", "commit": "a" * 40},
            {"id": "two", "commit": "b" * 40},
            {"id": "short", "commit": "abc1234"},
        ],
        [
            {"id": "one", "commit": "a" * 40},
            {"id": "one", "commit": "b" * 40},
            {"id": "three", "commit": "c" * 40},
        ],
        [
            {"id": "one", "commit": "a" * 40},
            {"id": "two", "commit": "a" * 40},
            {"id": "three", "commit": "c" * 40},
        ],
    ],
)
def test_registry_rejects_movable_duplicate_or_too_few_baselines(tmp_path, baselines):
    with pytest.raises(ValueError):
        load_baselines(_registry(tmp_path, baselines=baselines))


def test_registry_rejects_invalid_app_list(tmp_path):
    with pytest.raises(ValueError):
        load_baselines(_registry(tmp_path, apps=["../escape"]))


def test_unknown_baseline_and_missing_postgresql_fail_before_any_work(monkeypatch):
    with pytest.raises(ValueError, match="Unknown release baseline"):
        run_baseline("missing")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        run_baseline(next(iter(load_baselines()[1])))
