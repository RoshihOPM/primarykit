"""Payment state invariants; no externally-supplied 'is_paid' flag."""

import re


class PaymentRuleViolation(ValueError):
    pass


def validate_money(currency, amount_minor):
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise PaymentRuleViolation("Currency must be an uppercase ISO 4217 code.")
    if type(amount_minor) is not int or not 1 <= amount_minor <= 9_000_000_000_000_000:
        raise PaymentRuleViolation("Amount must be a positive integer in minor units.")


def can_cancel(status):
    return status == "pending"


def can_reconcile(status, outcome):
    return status == "pending" and outcome in {"succeeded", "failed"}
