"""Pure Storage ownership rule, independent of Users and Organizations ORM."""


def may_manage_file(*, actor_id, owner_id, elevated_in_scope: bool) -> bool:
    """Elevated access must already have been scoped to the file's organization."""
    return elevated_in_scope or actor_id == owner_id
