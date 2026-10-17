"""Pure chat invariants; deliberately independent of Django and other contexts."""

MAX_MESSAGE_CHARS = 4000


def normalize_message_body(body: str, *, has_attachment: bool = False) -> str:
    if not isinstance(body, str):
        raise ValueError("Message body must be a string.")
    result = body.strip()
    if len(result) > MAX_MESSAGE_CHARS:
        raise ValueError("Message exceeds 4000 characters.")
    if not result and not has_attachment:
        raise ValueError("A message needs text or an attachment.")
    return result


def canonical_pair(first_id, second_id):
    first, second = sorted((str(first_id), str(second_id)))
    if first == second:
        raise ValueError("Cannot create a dialogue with yourself.")
    return first, second
