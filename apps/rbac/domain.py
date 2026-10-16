"""Pure RBAC domain validation. Permission assignment is allowlist-only."""


def parse_permission_code(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or value.count(".") != 1:
        return None
    app, code = value.split(".")
    if not app or not code:
        return None
    return app, code


def unique_identifiers(values) -> bool:
    return len(values) == len(set(values))


def can_remove_role(*, assigned_user_count: int) -> bool:
    return assigned_user_count == 0
