"""Data-quality rules engine.

Applies one transformation (ASCII whitespace stripping) and one
validation rule (email check) to an input CSV, then writes the valid
rows to a single output CSV.

Usage:
    python3 dq_engine.py INPUT OUTPUT
"""

import csv
import io
import re
import sys

EXPECTED_HEADER = ["id", "name", "email", "age"]

_BLANK_LINE_RE = re.compile(r"^[ \t]*$")

_STRIP_CHARS = " \t"


def _fail(message, code):
    print("dq_engine.py: error: {}".format(message), file=sys.stderr)
    return code


def _is_valid_email(email):
    """Return True iff email satisfies the R4.1 validation rule."""
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    if not local or not domain:
        return False
    if " " in local or "\t" in local:
        return False
    if " " in domain or "\t" in domain:
        return False
    if "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def _read_input(path):
    """Read and structurally validate INPUT. Returns (rows, error)."""
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            content = handle.read()
    except FileNotFoundError:
        return None, "input file not found: {}".format(path)
    except (IsADirectoryError, PermissionError, OSError) as exc:
        return None, "cannot read input file {}: {}".format(path, exc)
    except UnicodeDecodeError:
        return None, "input file is not valid UTF-8: {}".format(path)

    lines = content.splitlines()
    if not lines:
        return None, "input file is empty, missing header: {}".format(path)

    try:
        header = next(csv.reader([lines[0]], strict=True))
    except csv.Error as exc:
        return None, "cannot parse header row: {}".format(exc)
    if header != EXPECTED_HEADER:
        return None, (
            "invalid header {!r}, expected {}".format(lines[0], EXPECTED_HEADER)
        )

    data_lines = [ln for ln in lines[1:] if not _BLANK_LINE_RE.match(ln)]
    try:
        rows = list(csv.reader(io.StringIO("\n".join(data_lines)), strict=True))
    except csv.Error as exc:
        return None, "cannot parse input CSV data: {}".format(exc)

    for row in rows:
        if len(row) != 4:
            return None, (
                "data row has {} fields, expected 4: {!r}".format(len(row), row)
            )
    return rows, None


def _transform(rows):
    return [[field.strip(_STRIP_CHARS) for field in row] for row in rows]


def _write_output(path, rows):
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(EXPECTED_HEADER)
            writer.writerows(rows)
    except (FileNotFoundError, IsADirectoryError, PermissionError,
            OSError) as exc:
        return "cannot write output file {}: {}".format(path, exc)
    return None


def main(argv):
    if len(argv) != 3:
        return _fail("expected exactly 2 arguments: INPUT OUTPUT", 2)
    input_path, output_path = argv[1], argv[2]

    rows, error = _read_input(input_path)
    if error is not None:
        return _fail(error, 1)

    valid_rows = [row for row in _transform(rows) if _is_valid_email(row[2])]

    error = _write_output(output_path, valid_rows)
    if error is not None:
        return _fail(error, 1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
