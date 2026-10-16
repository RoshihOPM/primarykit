"""Pure organization membership rules; no ORM, DRF or HTTP concerns."""


class OrganizationRuleViolation(ValueError):
    """A role or ownership mutation violates organization invariants."""


OWNER = "owner"
ADMIN = "admin"
MANAGER = "manager"
MEMBER = "member"
PRIVILEGED = frozenset({OWNER, ADMIN})


def may_manage_role(actor_role: str, target_role: str, new_role: str | None = None) -> bool:
    if actor_role == OWNER:
        return True
    if actor_role != ADMIN:
        return False
    return target_role not in PRIVILEGED and new_role not in PRIVILEGED


def preserves_active_owner(
    *,
    member_role: str,
    member_active: bool,
    next_role: str | None,
    deactivate: bool,
    active_owner_count: int,
) -> bool:
    if member_role != OWNER or not member_active:
        return True
    if not deactivate and next_role == OWNER:
        return True
    return active_owner_count > 1


def may_assign_explicit_branches(member_role: str) -> bool:
    return member_role not in PRIVILEGED


def can_invite(*, role: str, is_active: bool, verified: bool) -> bool:
    return role != OWNER and is_active and verified
