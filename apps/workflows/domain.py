"""Framework-independent workflow definitions and deterministic transition decisions."""

import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SCOPE = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_VERSION = 2**31 - 1


class WorkflowError(ValueError):
    """Base class for rejected workflow commands."""


class InvalidTransition(WorkflowError):
    """No valid transition is defined for the current state and action."""


class WorkflowPermissionDenied(WorkflowError):
    """The caller or the rule's permission policy does not allow the transition."""


class GuardRejected(WorkflowError):
    """A business guard rejected the transition."""


class StaleTransition(WorkflowError):
    """The command was based on an outdated aggregate version."""


@dataclass(frozen=True, slots=True)
class TransitionContext:
    actor: Any
    aggregate: Any
    source: str
    target: str
    action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


Policy = Callable[[TransitionContext], bool]


@dataclass(frozen=True, slots=True)
class TransitionRule:
    source: str
    action: str
    target: str
    guard: Policy | None = None
    permission: Policy | None = None


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    states: frozenset[str]
    initial: str
    terminal: frozenset[str]
    transitions: tuple[TransitionRule, ...]

    def __post_init__(self):
        states = frozenset(self.states)
        terminal = frozenset(self.terminal)
        transitions = tuple(self.transitions)
        if not states or any(not isinstance(s, str) or not _CODE.fullmatch(s) for s in states):
            raise ValueError("Workflow states must be nonempty lowercase codes")
        if self.initial not in states or not terminal <= states:
            raise ValueError("Initial and terminal states must belong to states")
        pairs = set()
        for rule in transitions:
            if not isinstance(rule, TransitionRule):
                raise TypeError("Transitions must be TransitionRule instances")
            if (
                rule.source not in states
                or rule.target not in states
                or not isinstance(rule.action, str)
                or not _CODE.fullmatch(rule.action)
            ):
                raise ValueError("Transition references invalid states or action")
            if rule.source in terminal or rule.source == rule.target:
                raise ValueError("Terminal and self transitions are forbidden")
            if (rule.source, rule.action) in pairs:
                raise ValueError("Duplicate action for the same source state")
            if rule.guard is not None and not callable(rule.guard):
                raise TypeError("guard must be callable")
            if rule.permission is not None and not callable(rule.permission):
                raise TypeError("permission must be callable")
            pairs.add((rule.source, rule.action))
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "terminal", terminal)
        object.__setattr__(self, "transitions", transitions)


@dataclass(frozen=True, slots=True)
class TransitionEvent:
    event_id: uuid.UUID
    scope: str
    aggregate_id: str
    version: int
    action: str
    from_state: str
    to_state: str


def decide(
    definition: WorkflowDefinition,
    *,
    scope: str,
    aggregate_id: str,
    state: str,
    version: int,
    action: str,
    actor: Any,
    aggregate: Any,
    metadata: Mapping[str, Any] | None = None,
) -> TransitionEvent:
    """Resolve one transition without I/O, time, randomness or implicit privileges.

    The event identity is stable for a given aggregate and next version. Persistence
    is intentionally outside this pure function.
    """
    if not isinstance(scope, str) or not _SCOPE.fullmatch(scope):
        raise ValueError("Invalid workflow scope")
    if not isinstance(aggregate_id, str) or not _ID.fullmatch(aggregate_id):
        raise ValueError("Invalid aggregate identifier")
    if type(version) is not int or not 0 <= version < _MAX_VERSION:
        raise ValueError("Invalid workflow version")
    if state not in definition.states:
        raise InvalidTransition("Unknown current state")
    if state in definition.terminal:
        raise InvalidTransition("Terminal state cannot transition")
    if not isinstance(action, str) or not _CODE.fullmatch(action):
        raise InvalidTransition("Invalid action")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    rule = next(
        (rule for rule in definition.transitions if rule.source == state and rule.action == action),
        None,
    )
    if rule is None:
        raise InvalidTransition("No transition for state and action")
    context = TransitionContext(
        actor=actor,
        aggregate=aggregate,
        source=state,
        target=rule.target,
        action=action,
        metadata=metadata,
    )
    if rule.permission is not None and rule.permission(context) is not True:
        raise WorkflowPermissionDenied("Transition permission denied")
    if rule.guard is not None and rule.guard(context) is not True:
        raise GuardRejected("Transition guard rejected")
    identity = json.dumps([scope, aggregate_id, version + 1], separators=(",", ":"))
    return TransitionEvent(
        event_id=uuid.uuid5(uuid.NAMESPACE_URL, identity),
        scope=scope,
        aggregate_id=aggregate_id,
        version=version + 1,
        action=action,
        from_state=state,
        to_state=rule.target,
    )
