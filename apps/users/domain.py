"""Account lifecycle decisions shared by authentication and delivery adapters."""


def may_send_verification(*, active: bool, verified: bool) -> bool:
    return active and not verified


def may_send_password_reset(*, active: bool) -> bool:
    return active


def may_authenticate(*, active: bool, verified: bool) -> bool:
    return active and verified


def may_deactivate(*, actor_id, target_id) -> bool:
    return actor_id != target_id
