"""Inventory domain invariants: pure arithmetic and command shapes.

Database locks, idempotency records and ledger writes live in application services.
"""

from dataclasses import dataclass


class StockRuleViolation(ValueError):
    """An inventory transition violates a stock invariant."""


@dataclass(frozen=True)
class StockPosition:
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    def apply(self, *, physical: int = 0, held: int = 0) -> "StockPosition":
        if not isinstance(physical, int) or not isinstance(held, int):
            raise StockRuleViolation("Stock deltas must be integers.")
        new_hand = self.on_hand + physical
        new_reserved = self.reserved + held
        if new_hand < 0 or new_reserved < 0 or new_reserved > new_hand:
            raise StockRuleViolation("Insufficient available or reserved quantity.")
        return StockPosition(on_hand=new_hand, reserved=new_reserved)


COMMAND_KINDS = ("receive", "issue", "transfer", "reserve", "release", "consume")
CLOSE_KINDS = frozenset({"release", "consume"})
ENTRY_KINDS = frozenset(COMMAND_KINDS) - CLOSE_KINDS


def command_fields(kind: str) -> tuple[frozenset[str], frozenset[str]]:
    """Required and forbidden business fields for one stock command."""
    if kind not in COMMAND_KINDS:
        raise StockRuleViolation("Unknown inventory operation.")
    if kind in CLOSE_KINDS:
        return frozenset({"reservation"}), frozenset(
            {"warehouse", "destination", "item", "quantity"}
        )
    required = {"warehouse", "item", "quantity"}
    forbidden = {"reservation"}
    if kind == "transfer":
        required.add("destination")
    else:
        forbidden.add("destination")
    return frozenset(required), frozenset(forbidden)


def validate_command_shape(kind: str, provided_fields) -> None:
    required, forbidden = command_fields(kind)
    fields = frozenset(provided_fields)
    if required - fields or forbidden & fields:
        raise StockRuleViolation("Invalid fields for this stock operation.")


def validate_command_quantity(kind: str, payload) -> None:
    """Never trust DRF serializer bounds: commands are also called internally."""
    if kind in ENTRY_KINDS:
        quantity = payload.get("quantity")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or not 1 <= quantity <= 10**12
        ):
            raise StockRuleViolation("Quantity must be a positive bounded integer.")


def require_open_reservation(status: str) -> None:
    if status != "active":
        raise StockRuleViolation("Reservation is already closed.")
