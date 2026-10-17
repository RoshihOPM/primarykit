"""Bounded CSV parsing and Excel-injection-safe serialization.

No ORM writes, external storage, transport, implicit tenant selection or role checks.
The caller must authorize the dataset and commit validated rows transactionally.
"""

import csv
import io
from collections.abc import Callable, Iterable, Iterator, Mapping

_MAX_BYTES = 2 * 1024 * 1024
_MAX_ROWS = 1000
_MAX_CELL_CHARS = 32768


class CsvValidationError(ValueError):
    """Bad input with a safe, non-PII diagnostic."""


def _columns(columns: tuple[str, ...]) -> None:
    if (
        not isinstance(columns, tuple)
        or not columns
        or len(columns) > 64
        or any(not isinstance(x, str) or not x or len(x) > 128 for x in columns)
        or len(set(columns)) != len(columns)
    ):
        raise CsvValidationError("Provide 1-64 unique named columns")


def _formula_safe(value: object) -> str:
    text = "" if value is None else str(value)
    # Excel can treat leading spaces and control characters as formula prefixes.
    # Force text for untrusted cells; client must accept that negative numbers
    # will also be serialized as explicit text.
    stripped = text.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_csv(
    rows: Iterable[Mapping[str, object]],
    *,
    columns: tuple[str, ...],
    max_rows: int = _MAX_ROWS,
) -> Iterator[str]:
    """Yield one CSV row at a time with a closed, explicit field allowlist."""
    _columns(columns)
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 100000:
        raise ValueError("max_rows must be between 1 and 100000")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")

    def emit(items):
        writer.writerow(items)
        result = output.getvalue()
        output.seek(0)
        output.truncate(0)
        return result

    yield emit(_formula_safe(c) for c in columns)
    for i, row in enumerate(rows):
        if i >= max_rows:
            raise CsvValidationError("Export row limit exceeded")
        if not isinstance(row, Mapping) or any(c not in row for c in columns):
            raise CsvValidationError("Row is missing an allowed column")
        yield emit(_formula_safe(row[c]) for c in columns)


def validate_csv[T](
    content: bytes,
    *,
    columns: tuple[str, ...],
    validate_row: Callable[[dict[str, str]], T] | None = None,
    max_bytes: int = _MAX_BYTES,
    max_rows: int = _MAX_ROWS,
) -> list[T] | list[dict[str, str]]:
    """Validate a bounded UTF-8 CSV in memory; NEVER persist rows automatically."""
    _columns(columns)
    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or not 1 <= max_bytes <= _MAX_BYTES
    ):
        raise ValueError("Invalid max_bytes")
    if (
        not isinstance(max_rows, int)
        or isinstance(max_rows, bool)
        or not 1 <= max_rows <= _MAX_ROWS
    ):
        raise ValueError("Invalid max_rows")
    if not isinstance(content, bytes) or len(content) > max_bytes:
        raise CsvValidationError("CSV must be bytes within the upload size limit")
    try:
        decoded = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8") from exc
    if "\x00" in decoded:
        raise CsvValidationError("NUL characters are forbidden")

    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise CsvValidationError("CSV must have a valid header") from exc
    if (
        len(header) != len(columns)
        or len(set(header)) != len(header)
        or set(header) != set(columns)
    ):
        raise CsvValidationError("CSV header does not match the allowed columns")

    results = []
    try:
        for index, fields in enumerate(reader, start=1):
            if index > max_rows:
                raise CsvValidationError("CSV import row limit exceeded")
            if len(fields) != len(header):
                raise CsvValidationError(f"CSV row {index} has an invalid field count")
            if any(len(cell) > _MAX_CELL_CHARS for cell in fields):
                raise CsvValidationError(f"CSV row {index} exceeds the cell size limit")
            row = dict(zip(header, fields, strict=True))
            try:
                results.append(validate_row(row) if validate_row else row)
            except (ValueError, TypeError) as exc:
                # Validation callbacks must not disclose the actual cell content.
                raise CsvValidationError(f"CSV row {index} failed validation") from exc
    except csv.Error as exc:
        raise CsvValidationError("Malformed CSV quoting") from exc
    return results
