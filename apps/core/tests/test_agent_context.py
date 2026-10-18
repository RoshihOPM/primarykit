import json
from pathlib import Path

import pytest

from apps.core.agent_context import build_context, main, render_markdown


def test_agent_context_uses_current_modules_without_django_setup(capsys):
    root = Path(__file__).resolve().parents[3]
    brief = build_context(root)
    assert {"core", "users", "notifications"} <= set(brief["modules"])
    assert brief["project_owns_migrations"] is True
    assert brief["has_upstream_runtime_dependency"] is False
    assert "SECRET_KEY" not in render_markdown(brief)
    assert main(["--root", str(root), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["modules"] == brief["modules"]


def test_agent_context_fails_closed_on_invalid_project(tmp_path):
    with pytest.raises(ValueError, match="doctor failed"):
        build_context(tmp_path)
