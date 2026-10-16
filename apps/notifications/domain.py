"""Notification intent is a value object; delivery is an external effect."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailIntent:
    recipient: str
    subject: str
    template: str
    context: Mapping[str, object]

    def __post_init__(self):
        if not self.recipient or not self.subject or not self.template:
            raise ValueError("A notification requires recipient, subject and template.")
