"""Immutable priced order line decisions independent of Django and other contexts."""

from dataclasses import dataclass
import re

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_TOTAL = 9_000_000_000_000_000


class OrderRuleViolation(ValueError):
    pass


@dataclass(frozen=True)
class OrderLine:
    sku: str
    title: str
    quantity: int
    unit_price_minor: int

    @property
    def total_minor(self):
        return self.quantity * self.unit_price_minor


def normalize_order_lines(currency, values):
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise OrderRuleViolation("Currency must be an uppercase ISO 4217 code.")
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise OrderRuleViolation("An order requires 1-100 lines.")
    results = []
    for row in values:
        if not isinstance(row, dict) or set(row) != {
            "sku", "title", "quantity", "unit_price_minor"
        }:
            raise OrderRuleViolation("Each line requires sku, title, quantity and unit_price_minor.")
        sku, title = row["sku"], row["title"]
        qty, price = row["quantity"], row["unit_price_minor"]
        if not isinstance(sku, str) or not SKU_RE.fullmatch(sku):
            raise OrderRuleViolation("Invalid SKU.")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise OrderRuleViolation("Invalid line title.")
        if type(qty) is not int or not 1 <= qty <= 1_000_000:
            raise OrderRuleViolation("Quantity must be 1-1000000.")
        if type(price) is not int or not 0 <= price <= 1_000_000_000_000:
            raise OrderRuleViolation("Unit price must be a nonnegative integer in minor units.")
        results.append(OrderLine(sku.upper(), title.strip(), qty, price))
    total = sum(line.total_minor for line in results)
    if total > MAX_TOTAL:
        raise OrderRuleViolation("Order total exceeds supported amount.")
    return tuple(results), total


def may_cancel_order(status):
    return status == "placed"
