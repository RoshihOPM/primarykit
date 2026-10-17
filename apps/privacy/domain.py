"""Pure rules for explicit, client-owned privacy policies and dry-run plans."""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

CODE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
SCOPE = re.compile(r"^[a-z][a-z0-9_.:-]{1,79}$")
ACTIONS = frozenset({"redact", "anonymize", "delete"})
HOLD_REASONS = frozenset({"legal", "regulatory", "dispute"})


@dataclass(frozen=True)
class Policy:
    code: str
    kind: str
    actions: frozenset[str]
    grace_days: int
    handler: str
    fingerprint: str


def load_policy(code: str, config: dict) -> Policy:
    """Only deployment-owned settings select the handler and allowed operations."""
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError("Invalid policy code")
    if not isinstance(config, dict) or set(config) != {"kind", "actions", "grace_days", "handler"}:
        raise ValueError("Invalid retention policy definition")
    kind, actions = config["kind"], config["actions"]
    days, handler = config["grace_days"], config["handler"]
    if not isinstance(kind, str) or not CODE.fullmatch(kind):
        raise ValueError("Invalid subject kind")
    if not isinstance(actions, (list, tuple, frozenset)) or not actions:
        raise ValueError("Policy actions must be a non-empty sequence")
    if any(type(action) is not str or action not in ACTIONS for action in actions):
        raise ValueError("Unsupported privacy action")
    if type(days) is not int or not 0 <= days <= 3650:
        raise ValueError("grace_days must be between 0 and 3650")
    if (
        not isinstance(handler, str)
        or len(handler) > 255
        or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+", handler)
    ):
        raise ValueError("Policy handler must be a trusted dotted import path")
    normalized = {
        "code": code,
        "kind": kind,
        "actions": sorted(set(actions)),
        "grace_days": days,
        "handler": handler,
    }
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    return Policy(code, kind, frozenset(actions), days, handler, fingerprint)


def validate_reference(scope, kind, subject_id, request_key=None):
    """Identifiers are opaque UUIDs; never persist emails, names or tokens here."""
    if not isinstance(scope, str) or not SCOPE.fullmatch(scope):
        raise ValueError("Invalid scope")
    if not isinstance(kind, str) or not CODE.fullmatch(kind):
        raise ValueError("Invalid subject kind")
    try:
        subject_id = uuid.UUID(str(subject_id))
        key = uuid.UUID(str(request_key)) if request_key is not None else None
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Subject and request key must be UUIDs") from exc
    return subject_id, key


def planned_execution(now, policy: Policy):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now + timedelta(days=policy.grace_days)
