"""Validate repo-local Agent Skills structure with no extra runtime tooling."""

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[3] / ".agents" / "skills"
SKILLS = [
    "system-architect",
    "database-architect",
    "feature-delivery",
    "security-review",
]


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter_and_content(name):
    filename = SKILLS_DIR / name / "SKILL.md"
    text = filename.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---", 2)
    metadata = {
        key: value.strip()
        for key, value in re.findall(r"^([a-z][a-z-]*):\s*(.*)$", frontmatter, re.MULTILINE)
    }
    assert metadata["name"] == name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
    assert 1 <= len(name) <= 64
    assert 10 <= len(metadata["description"]) <= 1024
    assert len(body.strip()) >= 100
