"""PostgreSQL full-text search over a caller-authorized, explicitly scoped queryset."""

from collections.abc import Mapping
from functools import reduce

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import NotSupportedError, connections
from django.db.models import CharField, QuerySet, TextField


def search_queryset(
    queryset: QuerySet,
    *,
    scope_filters: Mapping[str, object],
    text: str,
    fields: tuple[str, ...],
    limit: int = 25,
) -> QuerySet:
    """Search within an already authorized queryset and a mandatory server-side scope.

    The caller MUST check that the authenticated actor can access scope_filters.
    Never accept scope_filters or queryset directly from untrusted query parameters.
    No unscoped fallback and no ORM field lookups supplied by an HTTP client.
    """
    if not isinstance(queryset, QuerySet):
        raise TypeError("queryset must be an authorized Django QuerySet")
    if not isinstance(scope_filters, Mapping) or not scope_filters:
        raise ValueError("A nonempty server-authorized scope_filters mapping is required")
    if any(not isinstance(key, str) or not key for key in scope_filters):
        raise ValueError("Invalid server scope filter")
    if not isinstance(text, str) or not (1 <= len(text.strip()) <= 200):
        raise ValueError("Search text must be 1-200 characters")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Result limit must be between 1 and 100")
    if (
        not isinstance(fields, tuple)
        or not 1 <= len(fields) <= 8
        or len(set(fields)) != len(fields)
    ):
        raise ValueError("Supply 1-8 unique, model-local text fields")

    for name in fields:
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("Only local text columns may be indexed for search")
        try:
            field = queryset.model._meta.get_field(name)
        except FieldDoesNotExist as exc:
            raise ValueError(f"Unknown searchable field: {name}") from exc
        if field.is_relation or not isinstance(field, (CharField, TextField)):
            raise ValueError(f"Search field must be a local CharField/TextField: {name}")

    if connections[queryset.db].vendor != "postgresql":
        raise NotSupportedError("PrimaryKit search requires PostgreSQL")
    try:
        scoped = queryset.filter(**scope_filters)
    except (FieldError, TypeError, ValueError) as exc:
        raise ValueError("Invalid server scope filter") from exc

    vector = reduce(lambda a, b: a + b, (SearchVector(name, config="simple") for name in fields))
    query = SearchQuery(text.strip(), config="simple", search_type="websearch")
    return (
        scoped.annotate(_primarykit_rank=SearchRank(vector, query))
        .filter(_primarykit_rank__gt=0)
        .order_by("-_primarykit_rank", "pk")[:limit]
    )
