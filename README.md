# Data-Quality Rules Engine

Requirements contract for the goal:

> Build "Data-quality rules engine" for a 100-row fixture with one
> transformation, one validation rule, and one output.

This document is the complete public requirements contract. A developer can
implement the goal from this document alone. Anything not stated here is an
implementation choice, except where this document explicitly requires
fail-loud behavior.

Scope is fixed: exactly one transformation, exactly one validation rule, and
exactly one output. No additional transformations, rules, outputs, or
features are in scope.

## 1. Input fixture

Path: `data/input.csv`.

- Encoding UTF-8, comma-separated per RFC 4180 quoting rules: the delimiter
  is `,`; a field containing a comma, double quote, CR, or LF must be
  enclosed in double quotes, with each embedded double quote escaped as
  `""`; unquoted fields must not contain a comma, double quote, CR, or LF;
  spaces and tabs are literal data (never added or removed by parsing); the
  header row is unquoted and must be exactly `id,name,score`.
- Line endings LF or CRLF are accepted on read; a single trailing LF/CRLF
  terminator does not create an extra row; an embedded newline is data only
  inside a quoted field.
- The fixture contains exactly 100 data rows below the header. Blank lines
  (empty lines or lines containing only spaces/tabs) are never skipped: each
  blank line counts as a malformed data row and fails the run loudly per
  section 6.
- Row shape: each data row has exactly three fields (`id`, `name`, `score`).
- `id` cell grammar: trim leading/trailing ASCII spaces/tabs, then require
  one or more ASCII digits (`^[0-9]+$`: no sign, no decimal point, no empty
  cell). Leading zeros are allowed and denote the decimal value (`007`
  denotes 7). `+5`, `-3`, `92.5`, empty, and whitespace-only cells are not
  valid `id` literals. The integer value must be in `1..100`, unique across
  the fixture by integer value.
- `name`: arbitrary string content representable under the above CSV dialect
  (may contain leading/trailing whitespace before the transformation is
  applied; commas, quotes, or newlines only via the quoting rule).
- `score`: string cell evaluated by the single validation rule.
- Fixture composition: at least one row passes the validation rule and at
  least one row fails it, so the rule and the output are exercised.

Underspecification decision: CSV is the fixture format (readable, diffable,
editable with standard tooling).

## 2. Transformation T1 (the one transformation): normalize `name`

For every data row, replace the `name` value with itself stripped of leading
and trailing ASCII whitespace (spaces and tabs). Interior characters,
including interior whitespace, are unchanged.

- T1 applies to all 100 rows, including rows that will fail validation.
- T1 never adds, removes, or reorders rows.
- T1 does not touch `id` or `score`.
- A `name` that is empty or whitespace-only becomes the empty string; the row
  is still processed and its validity is decided solely by rule R1.
- Observability: T1 produces no persisted output. Its result is transient
  in-memory state: the effective `name` per row fed forward to R1
  evaluation. `output/report.json` (the exactly-one persisted output)
  intentionally contains no names. Acceptance criterion 2 is therefore
  verified white-box (unit-level inspection of the effective rows or code
  inspection), not via a black-box assertion on O1.

## 3. Validation rule R1 (the one validation rule): `score` in range

A row is valid if and only if its `score` cell satisfies all of the following:

1. Trim leading and trailing ASCII whitespace (spaces and tabs).
2. The trimmed value is a valid base-10 integer literal: an optional leading
   `-` followed by one or more ASCII digits.
3. Its integer value is in the closed range `0..100` inclusive.

Anything else is invalid, including but not limited to: empty string,
non-numeric text (e.g. `abc`), decimals (e.g. `92.5`), values below 0
(e.g. `-3`), and values above 100 (e.g. `101`).

Examples:

| `score` cell | Verdict | Reason |
|---|---|---|
| `95` | valid | in range |
| `  87 ` | valid | surrounding whitespace trimmed, in range |
| `007` | valid | leading zeros accepted, value 7 |
| `0`, `100` | valid | range endpoints inclusive |
| `-3` | invalid | below range |
| `101` | invalid | above range |
| `abc`, `` (empty), `92.5` | invalid | not an integer |

Underspecification decision: the range `0..100` models a 0-100 quality score.
Only `score` determines validity; `name` (including empty-after-trim names)
never affects validity. No second rule exists.

## 4. Output O1 (the one output): quality report

Path: `output/report.json`.

- UTF-8 JSON object with exactly these four keys:
  - `total_rows`: integer, equal to 100 for every successful run (the engine
    succeeds only on exactly 100 data rows; any other row count fails loudly
    per section 6 with no success report).
  - `valid_rows`: integer, count of rows passing R1.
  - `invalid_rows`: integer, count of rows failing R1.
  - `invalid_ids`: JSON array of the integer `id`s of rows failing R1,
    sorted in strictly ascending numeric order with no duplicates.
- Consistency: `valid_rows + invalid_rows == total_rows`, and
  `len(invalid_ids) == invalid_rows`.
- No extra keys, no extra output files, no stdout machine-readable report;
  console output, if any, is human-readable only and not part of the contract.

## 5. Observable behavior and determinism

- The engine reads `data/input.csv`, applies T1 to every row, evaluates R1
  per row, and writes `output/report.json`. The input file is never modified.
- The engine is deterministic: the same input file bytes always yield the
  same parsed JSON report (key set, counts, and `invalid_ids` identical).
  JSON formatting details (indentation, key order) are not part of the
  contract; conformance is judged on the parsed object.
- Order of processing is not observable except through `invalid_ids`, which
  is always ascending regardless of input row order.
- Writing the report creates parent directories as needed and replaces any
  previous report by writing a temporary file in `output/` followed by an
  atomic rename, so a completed run never leaves a partially written JSON
  file observable at `output/report.json`.

## 6. Boundary cases and failure behavior

For the conforming 100-row fixture, behavior is fully defined by sections
1-5. For anything else, the engine must fail loudly rather than produce a
report that parses as success. A "valid report" is a file at
`output/report.json` that parses as a JSON object with exactly the four O1
keys (`total_rows`, `valid_rows`, `invalid_rows`, `invalid_ids`) with
correct types:

- Missing or unreadable input file: the run fails, and afterward either no
  file exists at `output/report.json` or the file there does not parse as a
  valid report as defined above.
- Header not exactly `id,name,score`, a data row without exactly three
  fields, an `id` cell that does not match the section 1 grammar or whose
  value is outside `1..100`, duplicate `id` values, a blank line counted as
  a malformed row, or any data-row count other than 100: the run fails
  loudly instead of guessing, with the same no-valid-report postcondition.
- Failure signal: when invoked as a CLI command the process exits with a
  nonzero status; when imported as a library the call raises an exception.
  A run that fails must satisfy the no-valid-report postcondition: either no
  report is written or any partial file is removed or left in a state that
  does not parse as a valid report.

Out-of-scope inputs (more or fewer than 100 rows, non-CSV content) follow
the same principle: process nothing silently, fail loudly with the same
signal and postcondition.

## 7. Acceptance criteria

1. `data/input.csv` exists with header `id,name,score` and exactly 100 data
   rows, `id`s exactly `1..100` in some order, with at least one R1-valid and
   at least one R1-invalid row.
2. For every row, the effective in-memory `name` fed to R1 equals the raw
   `name` stripped of leading/trailing spaces and tabs (verified white-box
   on the effective rows, not via O1, which contains no names); row count
   and order are otherwise preserved.
3. Each example in the section 3 table yields the stated verdict.
4. `output/report.json` parses as a JSON object with exactly the keys
   `total_rows`, `valid_rows`, `invalid_rows`, `invalid_ids`; counts satisfy
   `valid_rows + invalid_rows == total_rows == 100`; `invalid_ids` is the
   ascending sorted list of exactly the R1-failing row ids.
5. Two consecutive runs on the unchanged fixture produce parsed-identical
   reports.
6. Deleting or corrupting the input (wrong header, short row, bad `id`,
   blank line, or row count other than 100) makes the run fail (nonzero CLI
   exit, or raised exception for library use) and afterward either no file
   exists at `output/report.json` or the file there does not parse as a JSON
   object with exactly the four O1 keys.
7. No production behavior beyond T1, R1, and O1 exists: one transformation,
   one validation rule, one output.

## 8. Non-goals

Streaming or incremental processing, databases, network services, additional
rules or reports, data repair beyond T1 whitespace normalization, and any
output format besides `output/report.json` are explicitly out of scope.
