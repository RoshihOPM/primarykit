"""Pure recorded sale rules; recording is not a payment or stock movement."""

import re
from dataclasses import dataclass


class SalesRuleViolation(ValueError):
    pass


@dataclass(frozen=True)
class SaleLine:
    sku: str
    title: str
    quantity: int
    unit_price_minor: int

    @property
    def total_minor(self):
        return self.quantity * self.unit_price_minor


def normalize_sale_lines(currency, lines):
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise SalesRuleViolation("Currency must be an uppercase ISO 4217 code.")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise SalesRuleViolation("Sale requires 1-100 lines.")
    result = []
    for row in lines:
        if not isinstance(row, dict) or set(row) != {
            "sku",
            "title",
            "quantity",
            "unit_price_minor",
        }:
            raise SalesRuleViolation(
                "Each line requires sku, title, quantity and unit_price_minor."
            )
        sku, title, qty, price = (
            row["sku"],
            row["title"],
            row["quantity"],
            row["unit_price_minor"],
        )
        if (
            not isinstance(sku, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", sku) is None
        ):
            raise SalesRuleViolation("Invalid SKU.")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise SalesRuleViolation("Invalid title.")
        if type(qty) is not int or not 1 <= qty <= 1_000_000:
            raise SalesRuleViolation("Invalid quantity.")
        if type(price) is not int or not 0 <= price <= 1_000_000_000_000:
            raise SalesRuleViolation("Invalid price in minor units.")
        result.append(SaleLine(sku.upper(), title.strip(), qty, price))
    if sum(line.total_minor for line in result) > 9_000_000_000_000_000:
        raise SalesRuleViolation("Sale amount exceeds supported limit.")
    return tuple(result), sum(line.total_minor for line in result)
