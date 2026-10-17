import pytest

from apps.csv_exchange.services import CsvValidationError, export_csv, validate_csv


def test_export_escapes_formula_cells_in_headers_and_values():
    rows = [{"name": '=HYPERLINK("x")', "amount": -12}, {"name": "safe", "amount": "+12"}]
    data = "".join(export_csv(rows, columns=("name", "amount")))
    assert "'=HYPERLINK" in data
    assert "'-12" in data
    assert "'+12" in data
    assert validate_csv(data.encode(), columns=("name", "amount"))[0]["name"].startswith("'=")


def test_csv_bom_reordered_header_and_caller_validator():
    rows = validate_csv(
        b"\xef\xbb\xbfage,name\r\n17,alice\r\n",
        columns=("name", "age"),
        validate_row=lambda row: {"name": row["name"], "age": int(row["age"])},
    )
    assert rows == [{"name": "alice", "age": 17}]


@pytest.mark.parametrize(
    "content",
    [
        b"name,name\nfirst,second\n",
        b"name,extra\na,b\n",
        b"name\n\xff\n",
        b"name\nhello\x00world\n",
        b'name\n"unterminated\n',
        b"name\na,b\n",
    ],
)
def test_invalid_input_is_rejected(content):
    with pytest.raises(CsvValidationError):
        validate_csv(content, columns=("name",))


def test_import_limits_and_transaction_free_validation():
    with pytest.raises(CsvValidationError, match="row limit"):
        validate_csv(b"name\na\nb\n", columns=("name",), max_rows=1)
    with pytest.raises(CsvValidationError, match="size limit"):
        validate_csv(b"name\n" + b"x" * 20, columns=("name",), max_bytes=10)
    with pytest.raises(CsvValidationError, match="failed validation"):
        validate_csv(
            b"name\nwrong\n",
            columns=("name",),
            validate_row=lambda _row: int("not-int"),
        )
    with pytest.raises(CsvValidationError, match="cell size"):
        validate_csv(b"name\n" + b"x" * 32769, columns=("name",))


def test_export_never_serializes_fields_outside_allowlist():
    result = "".join(export_csv([{"name": "public", "password": "private"}], columns=("name",)))
    assert "password" not in result and "private" not in result


def test_export_row_budget_stops_stream():
    with pytest.raises(CsvValidationError, match="row limit"):
        list(export_csv([{"name": "one"}, {"name": "two"}], columns=("name",), max_rows=1))
