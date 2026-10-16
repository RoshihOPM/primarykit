"""Outgoing mail port: applications depend on this contract, not SMTP."""

from typing import Protocol


class EmailGateway(Protocol):
    def send(self, *, recipient: str, subject: str, body: str, sender: str) -> int: ...
