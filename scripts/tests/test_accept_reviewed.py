"""``accept_reviewed`` / ``merged_paths`` only advance provenance, and fail closed."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import apply_module_upgrade
from scripts.apply_module_upgrade import apply_three_way_updates
from scripts.module_upgrade import compare_modules
from scripts.new_project import create_project
from scripts.tests.test_three_way_apply import commit, fixtures, git


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_origin(client: Path) -> dict:
    return json.loads((client / "primarykit-origin.json").read_text())


def write_origin(client: Path, metadata: dict) -> None:
    (client / "primarykit-origin.json").write_text(json.dumps(metadata))


def snapshot(client: Path) -> dict[str, bytes]:
    """Every tracked client file, so "nothing written" is checked byte-for-byte."""
    return {name: (client / name).read_bytes() for name in git(client, "ls-files").splitlines()}


def assert_untouched(client: Path, before: dict[str, bytes]) -> None:
    assert snapshot(client) == before
    assert git(client, "status", "--porcelain") == ""
    assert not list(client.glob(".primarykit-apply-*"))


def change_contract(source: Path, module: str = "audit", marker: str = "# changed contract\n"):
    contract = source / "apps" / module / "services.py"
    contract.write_text(contract.read_text() + "\n" + marker)
    return contract


def tasks_fixtures(tmp_path):
    """Like ``fixtures`` but with the bundled-migration ``tasks`` module."""
    source = create_project(tmp_path / "source", name="source-api", optional_apps={"tasks"})
    client = create_project(tmp_path / "client", name="client-api", optional_apps={"tasks"})
    git(source, "init", "-q")
    commit(source, "baseline")
    metadata = read_origin(client)
    metadata["module_source_refs"]["tasks"] = git(source, "rev-parse", "HEAD")
    write_origin(client, metadata)
    git(client, "init", "-q")
    commit(client, "baseline")
    git(client, "checkout", "-b", "feat/upgrade")
    # Upstream contract change that the reviewer copies into the client.
    contract = change_contract(source, "tasks")
    commit(source, "upstream tasks contract")
    (client / "apps" / "tasks" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed tasks contract")
    return source, client


# 1. Converged contract + unrelated helper change.


def test_accept_reviewed_records_converged_contract_and_applies_helper(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# unrelated upstream helper\n")
    contract = change_contract(source)
    pyproject = source / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "9.9.9"', 1))
    commit(source, "upstream helper and contract changed")
    client_contract = client / "apps" / "audit" / "services.py"
    client_contract.write_bytes(contract.read_bytes())
    commit(client, "manually copied reviewed contract")
    before = read_origin(client)

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert result["applied"] is True
    assert result["accepted"] == ["audit"]
    assert result["updated"] == ["audit/helper.py"]
    assert result["reviewed_paths"] == ["audit/services.py"]
    assert result["requires_client_pr"] is True
    assert (client / "apps" / "audit" / "helper.py").read_bytes() == helper.read_bytes()
    assert client_contract.read_bytes() == contract.read_bytes()
    after = read_origin(client)
    assert after["module_fingerprints"]["audit"]["services.py"] == sha(contract)
    assert after["module_fingerprints"]["audit"]["helper.py"] == sha(helper)
    assert after["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
    assert after["module_versions"]["audit"] == "9.9.9"
    # Audit's source policy is client-owned; other modules are not advanced.
    assert after["module_migration_policies"]["audit"] == "client"
    assert result["migration_policies"] == {"audit": "client"}
    for module in set(before["module_source_refs"]) - {"audit"}:
        assert after["module_source_refs"][module] == before["module_source_refs"][module]
        assert after["module_versions"][module] == before["module_versions"][module]
        assert after["module_fingerprints"][module] == before["module_fingerprints"][module]
    # Only the helper and the provenance file are modified in the worktree.
    assert sorted(git(client, "status", "--porcelain").split()[1::2]) == [
        "apps/audit/helper.py",
        "primarykit-origin.json",
    ]
    commit(client, "reviewed upgrade")
    assert apply_three_way_updates(source=source, project=client)["applied"] is False


def test_accept_reviewed_contract_only_writes_no_module_code(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=["audit"])

    assert result["updated"] == []
    assert result["accepted"] == ["audit"]
    assert git(client, "status", "--porcelain").split() == ["M", "primarykit-origin.json"]
    assert read_origin(client)["module_fingerprints"]["audit"]["services.py"] == sha(contract)


def test_accept_reviewed_refuses_source_migrations_without_bundled_policy(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    migrations = source / "apps" / "audit" / "migrations"
    migrations.mkdir()
    (migrations / "__init__.py").write_text("")
    (migrations / "0001_initial.py").write_text("# Schema requires review\n")
    commit(source, "contract and schema migration")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit: source ships migrations without a bundled"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)
    assert not (client / "apps" / "audit" / "migrations").exists()


# 2. Reviewed change was never placed in the client.


def test_accept_reviewed_refuses_contract_not_placed_in_client(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# unrelated upstream helper\n")
    change_contract(source)
    commit(source, "upstream helper and contract changed")
    before = snapshot(client)

    with pytest.raises(ValueError, match="place the reviewed source change in the client"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accept_reviewed_refuses_new_upstream_contract_file_missing_in_client(tmp_path):
    source, client = fixtures(tmp_path)
    (source / "apps" / "audit" / "permissions.py").write_text("# new sensitive rule\n")
    commit(source, "new contract file")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit/permissions.py: place the reviewed"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)
    assert not (client / "apps" / "audit" / "permissions.py").exists()


# 3. Two-sided contract change.


def test_two_sided_contract_change_needs_explicit_merged_path(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source, marker="# upstream contract\n")
    commit(source, "upstream contract")
    client_contract = client / "apps" / "audit" / "services.py"
    client_contract.write_text(
        "# client hand-merge\n" + client_contract.read_text() + "\n# upstream contract (merged)\n"
    )
    commit(client, "hand-merged contract")
    before = snapshot(client)
    merged_bytes = client_contract.read_bytes()

    with pytest.raises(ValueError, match="contract/deletion review required"):
        apply_three_way_updates(source=source, project=client)
    assert_untouched(client, before)
    with pytest.raises(ValueError, match="--merged-path"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    assert_untouched(client, before)

    result = apply_three_way_updates(
        source=source,
        project=client,
        accept_reviewed=("audit",),
        merged_paths=("audit/services.py",),
    )

    assert result["applied"] is True
    assert result["updated"] == []
    assert result["accepted"] == ["audit"]
    assert result["reviewed_paths"] == ["audit/services.py"]
    assert client_contract.read_bytes() == merged_bytes
    metadata = read_origin(client)
    assert metadata["module_fingerprints"]["audit"]["services.py"] == sha(contract)
    assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
    commit(client, "recorded reviewed merge")

    changes = compare_modules(source=source, project=client)["modules"]["audit"]["changes"]
    assert [(c["path"], c["change"]) for c in changes] == [("services.py", "client_modified")]
    again = apply_three_way_updates(source=source, project=client)
    assert again == {"applied": False, "updated": [], "accepted": [], "branch": "feat/upgrade"}
    assert client_contract.read_bytes() == merged_bytes


# 4. Invalid ``merged_paths``.


@pytest.mark.parametrize(
    ("merged", "message"),
    [
        ("users/permissions.py", "needs an accepted module/path"),
        ("audit", "needs an accepted module/path"),
        ("audit/", "needs an accepted module/path"),
        ("audit/helper.py", "audit/helper.py: --merged-path does not match"),
        ("audit/services.py", "audit/services.py: --merged-path does not match"),
        ("audit/../users/permissions.py", "--merged-path does not match"),
        ("audit/missing.py", "--merged-path does not match"),
    ],
)
def test_merged_path_must_name_a_real_two_sided_change_of_an_accepted_module(
    tmp_path, merged, message
):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# unrelated upstream helper\n")
    contract = change_contract(source)
    users = source / "apps" / "users" / "permissions.py"
    users.write_text(users.read_text() + "\n# upstream users contract\n")
    commit(source, "upstream changes")
    # Converged contract and a one-sided helper: valid to accept, nothing two-sided.
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    local_users = client / "apps" / "users" / "permissions.py"
    local_users.write_text(local_users.read_text() + "\n# client users contract\n")
    commit(client, "reviewed contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match=message):
        apply_three_way_updates(
            source=source, project=client, accept_reviewed=("audit",), merged_paths=(merged,)
        )

    assert_untouched(client, before)


def test_merged_path_without_any_accepted_module_is_refused(tmp_path):
    source, client = fixtures(tmp_path)
    change_contract(source, marker="# upstream\n")
    commit(source, "upstream contract")
    local = client / "apps" / "audit" / "services.py"
    local.write_text(local.read_text() + "\n# client\n")
    commit(client, "client contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match="needs an accepted module/path"):
        apply_three_way_updates(source=source, project=client, merged_paths=("audit/services.py",))

    assert_untouched(client, before)


# 5. Unknown modules.


@pytest.mark.parametrize("module", ["nope", "tasks", "../audit", ""])
def test_accepting_unknown_or_not_installed_module_is_refused(tmp_path, module):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match="not installed"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit", module))

    assert_untouched(client, before)


def test_accepting_module_without_recorded_baseline_is_refused(tmp_path):
    source, client = fixtures(tmp_path)
    metadata = read_origin(client)
    metadata["module_fingerprints"].pop("audit")
    write_origin(client, metadata)
    commit(client, "legacy provenance without snapshot")
    before = snapshot(client)

    with pytest.raises(ValueError, match="unknown baseline cannot be accepted"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


# 6. Forged provenance.


def test_accept_reviewed_rejects_forged_fingerprint_of_converged_contract(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    metadata = read_origin(client)
    metadata["module_fingerprints"]["audit"]["services.py"] = "0" * 64
    write_origin(client, metadata)
    commit(client, "reviewed contract with forged provenance")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit/services.py: converged baseline mismatch"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accept_reviewed_rejects_omitted_fingerprint_of_historical_contract(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    metadata = read_origin(client)
    metadata["module_fingerprints"]["audit"].pop("services.py")
    write_origin(client, metadata)
    commit(client, "reviewed contract with omitted provenance")
    before = snapshot(client)

    # Reported under the converged wording; the cause is the omitted fingerprint.
    with pytest.raises(ValueError, match="audit/services.py: converged baseline mismatch"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accept_reviewed_rejects_forged_fingerprint_of_hand_merged_contract(tmp_path):
    source, client = fixtures(tmp_path)
    change_contract(source, marker="# upstream\n")
    commit(source, "upstream contract")
    local = client / "apps" / "audit" / "services.py"
    local.write_text(local.read_text() + "\n# client\n")
    metadata = read_origin(client)
    metadata["module_fingerprints"]["audit"]["services.py"] = "0" * 64
    write_origin(client, metadata)
    commit(client, "hand merge with forged provenance")
    before = snapshot(client)

    with pytest.raises(ValueError, match="historical baseline does not match"):
        apply_three_way_updates(
            source=source,
            project=client,
            accept_reviewed=("audit",),
            merged_paths=("audit/services.py",),
        )

    assert_untouched(client, before)


@pytest.mark.parametrize(
    ("forged", "message"),
    [
        ("client-head", "source ancestry is not available"),
        ("f" * 40, "source ancestry is not available"),
        ("HEAD", "missing immutable source ancestry"),
        (None, "missing immutable source ancestry"),
        ("absent", "missing immutable source ancestry"),
    ],
)
def test_accept_reviewed_rejects_forged_or_missing_source_ref(tmp_path, forged, message):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    metadata = read_origin(client)
    if forged == "absent":
        metadata["module_source_refs"].pop("audit")
    elif forged == "client-head":
        metadata["module_source_refs"]["audit"] = git(client, "rev-parse", "HEAD")
    else:
        metadata["module_source_refs"]["audit"] = forged
    write_origin(client, metadata)
    commit(client, "reviewed contract with forged ancestry")
    before = snapshot(client)

    with pytest.raises(ValueError, match=message):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accept_reviewed_rejects_forged_ref_even_when_nothing_changed(tmp_path):
    """Acceptance must not launder an unrelated SHA into trusted ancestry."""
    source, client = fixtures(tmp_path)
    metadata = read_origin(client)
    metadata["module_source_refs"]["audit"] = git(client, "rev-parse", "HEAD")
    write_origin(client, metadata)
    commit(client, "forged ancestry, no module change")
    before = snapshot(client)

    with pytest.raises(ValueError, match="source ancestry is not available"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accept_reviewed_rejects_dirty_source_modules(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)  # Deliberately left uncommitted.
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match="immutable checkout"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


# 7. Upstream deletions.


def test_upstream_deletion_refused_while_client_still_has_the_file(tmp_path):
    source, client = fixtures(tmp_path)
    (source / "apps" / "audit" / "statistics.py").unlink()
    commit(source, "upstream removes statistics provider")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit/statistics.py: contract/deletion review required"):
        apply_three_way_updates(source=source, project=client)
    assert_untouched(client, before)
    with pytest.raises(ValueError, match="audit/statistics.py: place the reviewed source change"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    assert_untouched(client, before)
    assert (client / "apps" / "audit" / "statistics.py").is_file()


def test_upstream_deletion_recorded_once_client_deleted_and_module_accepted(tmp_path):
    source, client = fixtures(tmp_path)
    (source / "apps" / "audit" / "statistics.py").unlink()
    commit(source, "upstream removes statistics provider")
    (client / "apps" / "audit" / "statistics.py").unlink()
    commit(client, "reviewed removal")
    assert "statistics.py" in read_origin(client)["module_fingerprints"]["audit"]

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert result["updated"] == []
    assert result["reviewed_paths"] == ["audit/statistics.py"]
    metadata = read_origin(client)
    assert "statistics.py" not in metadata["module_fingerprints"]["audit"]
    assert metadata["module_source_refs"]["audit"] == git(source, "rev-parse", "HEAD")
    assert not (client / "apps" / "audit" / "statistics.py").exists()
    commit(client, "recorded removal")
    assert compare_modules(source=source, project=client)["modules"]["audit"]["changes"] == []


def test_converged_deletion_with_forged_fingerprint_is_refused(tmp_path):
    source, client = fixtures(tmp_path)
    (source / "apps" / "audit" / "statistics.py").unlink()
    commit(source, "upstream removes statistics provider")
    (client / "apps" / "audit" / "statistics.py").unlink()
    metadata = read_origin(client)
    metadata["module_fingerprints"]["audit"]["statistics.py"] = "0" * 64
    write_origin(client, metadata)
    commit(client, "reviewed removal with forged provenance")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit/statistics.py: converged baseline mismatch"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


# 8. Migration pin.


def test_migration_pin_bundled_for_byte_identical_history(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    migration = client / "apps" / "tasks" / "migrations" / "0001_initial.py"
    migration_bytes = migration.read_bytes()
    assert migration_bytes == (source / "apps/tasks/migrations/0001_initial.py").read_bytes()

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert result["accepted"] == ["tasks"]
    assert result["migration_policies"] == {"tasks": "bundled"}
    metadata = read_origin(client)
    assert metadata["module_migration_policies"]["tasks"] == "bundled"
    assert metadata["module_source_refs"]["tasks"] == git(source, "rev-parse", "HEAD")
    assert metadata["module_fingerprints"]["tasks"]["services.py"] == sha(
        source / "apps" / "tasks" / "services.py"
    )
    assert migration.read_bytes() == migration_bytes
    assert git(client, "status", "--porcelain").split() == ["M", "primarykit-origin.json"]


def own_tasks_history(client: Path, previous) -> Path:
    """Client-generated 0001 that differs from the bundled one; set the previous pin."""
    migration = client / "apps" / "tasks" / "migrations" / "0001_initial.py"
    migration.write_bytes(migration.read_bytes() + b"\n# client-generated history\n")
    metadata = read_origin(client)
    if previous is None:
        metadata["module_migration_policies"].pop("tasks")
    else:
        metadata["module_migration_policies"]["tasks"] = previous
    write_origin(client, metadata)
    commit(client, "client-owned tasks migration history")
    return migration


@pytest.mark.parametrize(
    ("previous", "keep"),
    [(None, ("tasks",)), ("client", ()), ("client", ("tasks",))],
)
def test_migration_pin_client_only_when_pinned_before_or_explicitly_kept(tmp_path, previous, keep):
    source, client = tasks_fixtures(tmp_path)
    migration = own_tasks_history(client, previous)
    migration_bytes = migration.read_bytes()

    result = apply_three_way_updates(
        source=source, project=client, accept_reviewed=("tasks",), keep_client_migrations=keep
    )

    assert result["migration_policies"] == {"tasks": "client"}
    assert read_origin(client)["module_migration_policies"]["tasks"] == "client"
    assert migration.read_bytes() == migration_bytes
    assert sorted(p.name for p in migration.parent.glob("*.py")) == [
        "0001_initial.py",
        "__init__.py",
    ]


def test_migration_pin_never_infers_client_for_differing_unpinned_history(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    own_tasks_history(client, None)
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: migration history differs.*--keep-client-migr"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)


def test_migration_pin_keep_cannot_override_previous_bundled_pin(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    own_tasks_history(client, "bundled")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: bundled migration history differs"):
        apply_three_way_updates(
            source=source,
            project=client,
            accept_reviewed=("tasks",),
            keep_client_migrations=("tasks",),
        )

    assert_untouched(client, before)


@pytest.mark.parametrize(
    ("previous", "keep", "expected"),
    [
        (None, (), "bundled"),
        (None, ("tasks",), "bundled"),
        ("bundled", ("tasks",), "bundled"),
        ("client", (), "client"),
    ],
)
def test_migration_pin_for_identical_history_keeps_previous_client_pin(
    tmp_path, previous, keep, expected
):
    source, client = tasks_fixtures(tmp_path)
    metadata = read_origin(client)
    if previous is None:
        metadata["module_migration_policies"].pop("tasks")
    else:
        metadata["module_migration_policies"]["tasks"] = previous
    if previous != "bundled":  # The generator already pins tasks as bundled.
        write_origin(client, metadata)
        commit(client, "previous pin")

    result = apply_three_way_updates(
        source=source, project=client, accept_reviewed=("tasks",), keep_client_migrations=keep
    )

    assert result["migration_policies"] == {"tasks": expected}
    assert read_origin(client)["module_migration_policies"]["tasks"] == expected


@pytest.mark.parametrize("previous", ["weird", "", 5, ["bundled"], True])
def test_migration_pin_refuses_invalid_previous_pin(tmp_path, previous):
    source, client = tasks_fixtures(tmp_path)
    metadata = read_origin(client)
    metadata["module_migration_policies"]["tasks"] = previous
    write_origin(client, metadata)
    commit(client, "invalid pin")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: client provenance has an invalid pinned"):
        apply_three_way_updates(
            source=source,
            project=client,
            accept_reviewed=("tasks",),
            keep_client_migrations=("tasks",),
        )

    assert_untouched(client, before)


@pytest.mark.parametrize("policy", ['"weird"', '""', "5", "None", '("bundled",)'])
def test_migration_pin_refuses_invalid_source_policy(tmp_path, policy):
    source, client = tasks_fixtures(tmp_path)
    manifest = source / "apps" / "tasks" / "manifest.py"
    manifest.write_text(
        manifest.read_text().replace('migration_policy="bundled"', f"migration_policy={policy}")
    )
    commit(source, "invalid source policy")
    (client / "apps" / "tasks" / "manifest.py").write_bytes(manifest.read_bytes())
    commit(client, "reviewed manifest")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: source manifest has an invalid migration policy"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)


def test_migration_pin_refuses_bundled_pin_when_source_policy_is_not_bundled(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    metadata = read_origin(client)
    metadata["module_migration_policies"]["audit"] = "bundled"
    write_origin(client, metadata)
    commit(client, "reviewed contract, stale bundled pin")
    before = snapshot(client)

    with pytest.raises(ValueError, match="audit: pinned bundled history no longer matches"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


@pytest.mark.parametrize("keep", [("audit",), ("tasks", "nope")])
def test_keep_client_migrations_must_be_subset_of_accepted(tmp_path, keep):
    source, client = tasks_fixtures(tmp_path)
    own_tasks_history(client, None)
    before = snapshot(client)

    with pytest.raises(ValueError, match="--keep-client-migrations needs an accepted module"):
        apply_three_way_updates(
            source=source, project=client, accept_reviewed=("tasks",), keep_client_migrations=keep
        )
    with pytest.raises(ValueError, match="--keep-client-migrations needs an accepted module"):
        apply_three_way_updates(source=source, project=client, keep_client_migrations=("tasks",))

    assert_untouched(client, before)


def test_migration_pin_refuses_differing_history_pinned_as_bundled(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    assert read_origin(client)["module_migration_policies"]["tasks"] == "bundled"
    migration = client / "apps" / "tasks" / "migrations" / "0001_initial.py"
    migration.write_bytes(migration.read_bytes() + b"\n# drifted\n")
    commit(client, "drifted bundled migration")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: bundled migration history differs"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)


def test_migration_pin_refuses_new_upstream_migration_not_copied_by_bundled_client(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    (source / "apps" / "tasks" / "migrations" / "0002_more.py").write_text("# upstream schema\n")
    commit(source, "upstream adds a migration")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: bundled migration history differs"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)
    assert not (client / "apps" / "tasks" / "migrations" / "0002_more.py").exists()


@pytest.mark.parametrize("previous", ["bundled", None])
@pytest.mark.parametrize("remove_folder", [False, True])
def test_migration_pin_refuses_client_without_migration_history(tmp_path, previous, remove_folder):
    source, client = tasks_fixtures(tmp_path)
    folder = client / "apps" / "tasks" / "migrations"
    (folder / "0001_initial.py").unlink()
    if remove_folder:
        (folder / "__init__.py").unlink()
        folder.rmdir()
    metadata = read_origin(client)
    if previous is None:
        metadata["module_migration_policies"].pop("tasks")
    write_origin(client, metadata)
    commit(client, "tasks without migrations")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: client has no committed migration history"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)


def test_migration_pin_refuses_unreviewed_artifact_in_client_migrations(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    (client / "apps" / "tasks" / "migrations" / "notes.txt").write_text("stray\n")
    commit(client, "stray migration artifact")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: Unreviewed artifact in migration folder"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))

    assert_untouched(client, before)


def test_bundled_module_without_acceptance_still_requires_schema_adoption(tmp_path):
    source, client = tasks_fixtures(tmp_path)
    scheduler = source / "apps" / "tasks" / "scheduler.py"
    scheduler.write_text(scheduler.read_text() + "\n# upstream non-contract change\n")
    commit(source, "upstream scheduler")
    before = snapshot(client)

    with pytest.raises(ValueError, match="tasks: reviewed schema adoption required"):
        apply_three_way_updates(source=source, project=client)

    assert_untouched(client, before)


# 9. Preconditions.


def test_accept_reviewed_still_requires_clean_feature_branch(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    origin = (client / "primarykit-origin.json").read_bytes()

    for branch in ("main", "master", "dev", "develop"):
        git(client, "checkout", "-q", "-B", branch)
        with pytest.raises(ValueError, match="feature branch"):
            apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    git(client, "checkout", "-q", "--detach")
    with pytest.raises(ValueError, match="feature branch"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    git(client, "checkout", "-q", "feat/upgrade")

    (client / "README.md").write_text("modified")
    with pytest.raises(ValueError, match="uncommitted"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    git(client, "checkout", "--", "README.md")
    (client / "untracked.txt").write_text("new")
    with pytest.raises(ValueError, match="uncommitted"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    (client / "untracked.txt").unlink()
    # An uncommitted (unreviewed-in-Git) contract placement is not accepted either.
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes() + b"# wip\n")
    with pytest.raises(ValueError, match="uncommitted"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    git(client, "checkout", "--", "apps/audit/services.py")
    assert (client / "primarykit-origin.json").read_bytes() == origin

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    assert result["accepted"] == ["audit"]
    assert result["branch"] == "feat/upgrade"


# 10. Rollback.


def test_accept_reviewed_restores_files_if_provenance_write_fails(tmp_path, monkeypatch):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# unrelated upstream helper\n")
    (source / "apps" / "audit" / "extras").mkdir()
    (source / "apps" / "audit" / "extras" / "new_helper.py").write_text("NEW = True\n")
    contract = change_contract(source)
    commit(source, "upstream helper, new nested helper and contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    before = snapshot(client)
    origin = client / "primarykit-origin.json"
    replace = apply_module_upgrade.os.replace
    replaced = []

    def fail_commit(src, dst):
        if Path(dst) == origin and Path(src).name == "primarykit-origin.json":
            raise OSError("simulated provenance failure")
        replaced.append(Path(dst).name)
        return replace(src, dst)

    monkeypatch.setattr(apply_module_upgrade.os, "replace", fail_commit)
    with pytest.raises(OSError, match="simulated provenance failure"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert {"helper.py", "new_helper.py"} <= set(replaced)  # Files really were written first.
    assert_untouched(client, before)
    assert not (client / "apps" / "audit" / "extras").exists()

    monkeypatch.undo()
    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    assert sorted(result["updated"]) == ["audit/extras/new_helper.py", "audit/helper.py"]


@pytest.mark.parametrize("keep", [(), ("tasks",)])
def test_migration_pin_unpinned_client_missing_new_bundled_migration(tmp_path, keep):
    """Reviewer scenario: identical 0001, no pin, upstream adds 0002."""
    source, client = tasks_fixtures(tmp_path)
    (source / "apps" / "tasks" / "migrations" / "0002_more.py").write_text("# upstream schema\n")
    commit(source, "upstream adds a migration")
    metadata = read_origin(client)
    metadata["module_migration_policies"].pop("tasks")  # Legacy origin without pins.
    write_origin(client, metadata)
    commit(client, "legacy provenance")
    before = snapshot(client)

    if not keep:
        with pytest.raises(ValueError, match="tasks: migration history differs from the bundled"):
            apply_three_way_updates(source=source, project=client, accept_reviewed=("tasks",))
        assert_untouched(client, before)
        return
    # Only the explicit, human-supplied flag may declare the history client-owned.
    result = apply_three_way_updates(
        source=source, project=client, accept_reviewed=("tasks",), keep_client_migrations=keep
    )
    assert result["migration_policies"] == {"tasks": "client"}
    assert not (client / "apps" / "tasks" / "migrations" / "0002_more.py").exists()


# Versions, no-op acceptance and provenance file safety.


def test_recorded_version_comes_from_committed_source_pyproject(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    pyproject = source / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "2.0.0"', 1))
    commit(source, "release 2.0.0")
    pyproject.write_text(pyproject.read_text().replace('version = "2.0.0"', 'version = "66.6"', 1))
    assert git(source, "status", "--porcelain").split() == ["M", "pyproject.toml"]
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")

    apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert read_origin(client)["module_versions"]["audit"] == "2.0.0"


def test_plain_three_way_update_also_records_committed_version(tmp_path):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# upstream helper\n")
    pyproject = source / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "2.0.0"', 1))
    commit(source, "release 2.0.0")
    pyproject.write_text(pyproject.read_text().replace('version = "2.0.0"', 'version = "66.6"', 1))

    assert apply_three_way_updates(source=source, project=client)["updated"] == ["audit/helper.py"]

    versions = read_origin(client)["module_versions"]
    assert versions["audit"] == "2.0.0"
    assert versions["users"] == "0.1.0"


@pytest.mark.parametrize("broken", ["missing-version", "invalid-toml", "empty-version", "deleted"])
def test_acceptance_refused_when_source_version_is_unreadable(tmp_path, broken):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    pyproject = source / "pyproject.toml"
    if broken == "missing-version":
        pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"\n', "", 1))
    elif broken == "empty-version":
        pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = ""', 1))
    elif broken == "invalid-toml":
        pyproject.write_text("[project\n")
    else:
        pyproject.unlink()
    commit(source, "unreadable version")
    # A readable working-tree file must not stand in for the immutable commit.
    pyproject.write_text('[project]\nname = "x"\nversion = "3.0.0"\n')
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    before = snapshot(client)

    with pytest.raises(ValueError, match="version is unreadable; cannot record acceptance"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


@pytest.mark.parametrize("versions", ["absent", None, ["0.1.0"], "0.1.0"])
def test_acceptance_refused_when_client_module_versions_are_unreadable(tmp_path, versions):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    metadata = read_origin(client)
    if versions == "absent":
        metadata.pop("module_versions")
    else:
        metadata["module_versions"] = versions
    write_origin(client, metadata)
    commit(client, "reviewed contract, broken versions")
    before = snapshot(client)

    with pytest.raises(ValueError, match="version is unreadable; cannot record acceptance"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert_untouched(client, before)


def test_accepting_already_current_module_is_a_byte_identical_noop(tmp_path):
    source, client = fixtures(tmp_path)
    before = snapshot(client)

    result = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert result == {"applied": False, "updated": [], "accepted": [], "branch": "feat/upgrade"}
    assert_untouched(client, before)


def test_repeating_an_acceptance_is_a_byte_identical_noop(tmp_path):
    source, client = fixtures(tmp_path)
    contract = change_contract(source)
    commit(source, "upstream contract")
    (client / "apps" / "audit" / "services.py").write_bytes(contract.read_bytes())
    commit(client, "reviewed contract")
    first = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))
    assert first["applied"] is True
    commit(client, "recorded acceptance")
    before = snapshot(client)

    again = apply_three_way_updates(source=source, project=client, accept_reviewed=("audit",))

    assert again["applied"] is False
    assert again["accepted"] == []
    assert_untouched(client, before)


@pytest.mark.parametrize("accept", [(), ("audit",)])
def test_symlinked_provenance_file_is_refused(tmp_path, accept):
    source, client = fixtures(tmp_path)
    helper = source / "apps" / "audit" / "helper.py"
    helper.write_text(helper.read_text() + "# upstream helper\n")
    commit(source, "upstream helper")
    origin = client / "primarykit-origin.json"
    real = client / "real-origin.json"
    origin.rename(real)
    origin.symlink_to("real-origin.json")
    commit(client, "symlinked provenance")
    real_bytes = real.read_bytes()
    client_helper = (client / "apps" / "audit" / "helper.py").read_bytes()

    with pytest.raises(ValueError, match="Symlinked client provenance is unsafe"):
        apply_three_way_updates(source=source, project=client, accept_reviewed=accept)

    assert origin.is_symlink()
    assert real.read_bytes() == real_bytes
    assert (client / "apps" / "audit" / "helper.py").read_bytes() == client_helper
    assert git(client, "status", "--porcelain") == ""


# CLI wiring.


def test_cli_accept_options_require_three_way_mode(tmp_path, capsys):
    from scripts.module_upgrade import main

    for extra in (["--accept-reviewed", "audit"], ["--merged-path", "audit/services.py"]):
        with pytest.raises(SystemExit) as error:
            main(["--source", str(tmp_path), "--project", str(tmp_path), *extra])
        assert error.value.code == 2
    assert "require --apply-three-way" in capsys.readouterr().err


def test_cli_records_reviewed_hand_merge(tmp_path, capsys):
    from scripts.module_upgrade import main

    source, client = fixtures(tmp_path)
    contract = change_contract(source, marker="# upstream\n")
    commit(source, "upstream contract")
    local = client / "apps" / "audit" / "services.py"
    local.write_text(local.read_text() + "\n# client\n")
    commit(client, "hand merge")
    merged_bytes = local.read_bytes()
    arguments = ["--source", str(source), "--project", str(client), "--apply-three-way", "--json"]

    with pytest.raises(ValueError, match="--merged-path"):
        main([*arguments, "--accept-reviewed", "audit"])
    code = main([*arguments, "--accept-reviewed", "audit", "--merged-path", "audit/services.py"])

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["accepted"] == ["audit"]
    assert result["reviewed_paths"] == ["audit/services.py"]
    assert local.read_bytes() == merged_bytes
    assert read_origin(client)["module_fingerprints"]["audit"]["services.py"] == sha(contract)


def test_cli_keep_client_migrations(tmp_path, capsys):
    from scripts.module_upgrade import main

    source, client = tasks_fixtures(tmp_path)
    own_tasks_history(client, None)
    arguments = ["--source", str(source), "--project", str(client)]
    with pytest.raises(SystemExit) as error:
        main([*arguments, "--keep-client-migrations", "tasks"])
    assert error.value.code == 2
    capsys.readouterr()
    arguments += ["--apply-three-way", "--json", "--accept-reviewed", "tasks"]
    with pytest.raises(ValueError, match="--keep-client-migrations"):
        main(arguments)

    assert main([*arguments, "--keep-client-migrations", "tasks"]) == 0

    assert json.loads(capsys.readouterr().out)["migration_policies"] == {"tasks": "client"}
    assert read_origin(client)["module_migration_policies"]["tasks"] == "client"
