# Data-quality rules engine — Requirements

Public, testable requirements contract for the goal:

> Build a “Data-quality rules engine” for a 100-row fixture with one
> transformation, one validation rule, and one output, exposed as
> `python3 dq_engine.py INPUT OUTPUT`.

No implementation or tests exist yet. A developer must be able to implement
the goal from this document alone.

## 1. Command and runtime

- R1.1: The engine is invoked as `python3 dq_engine.py INPUT OUTPUT`, where
  `INPUT` is an existing input file path and `OUTPUT` is the output file path.
  Both arguments are required positional arguments in this order.
- R1.2: The program runs on Python 3 using only the standard library.
- R1.3: On success the process exits with code `0`. On any failure defined
  below it exits with a nonzero code (`2` for command-line usage errors,
  `1` for input/output and data-shape errors) and writes a human-readable
  error message to stderr. It must not create or truncate `OUTPUT` when it
  exits nonzero.
- R1.4: Execution is deterministic: the same `INPUT` byte content always
  produces the same `OUTPUT` byte content on the same machine.

## 2. Input format

- R2.1: `INPUT` is a UTF-8 encoded CSV file with a header row followed by
  data rows. The reference fixture carries 100 data rows, but the engine
  must not assume or enforce any row count; it processes any number of data
  rows (including zero) the same way.
- R2.2: The header is the first physical line of `INPUT` and must be
  exactly `id,name,email,age` in this order. Validation parses that first
  line as one CSV record (Python's `csv` module defaults, excel dialect,
  as in R6.3) and compares the resulting fields exactly, with no
  stripping and no byte-order-mark tolerance: the fields must equal
  `id`, `name`, `email`, `age`. A quoted variant such as
  `"id","name","email","age"` parses to the same four fields and is
  accepted, while any whitespace-padded variant (for example
  `id, name,email,age` or a trailing space) or a leading byte-order mark
  fails the comparison. Any missing, extra, renamed, reordered, or
  otherwise altered column is a data-shape error (exit `1`, no `OUTPUT`
  created).
- R2.3: Each data row has four fields: `id`, `name`, `email`, `age`, all
  read as text. Empty files (no header) and undecodable/unparseable CSV
  content are data-shape errors (exit `1`, no `OUTPUT` created). Any data
  row (after ignoring fully blank lines per R2.4) whose parsed field count
  is not exactly four is a data-shape error (exit `1`, no `OUTPUT` created).
- R2.4: Fully blank lines in the input are ignored and do not count as rows.
  A fully blank line is a physical line that is empty after removing the
  line terminator and ASCII spaces/tabs (i.e. it matches `^[ \t]*$`),
  evaluated before CSV parsing. A delimiter-only line such as `,,,` is a
  data row, not a blank line.
  Blank-line ignoring applies only after the header: the header is always
  the first physical line of the file, so leading blank lines are not
  skipped and a file beginning with a blank line fails header validation
  (exit `1`, no `OUTPUT` created).
- R2.5: A missing or unreadable `INPUT` file is an error (exit `1`).

## 3. The one transformation

- R3.1: Before validation and output, the engine applies exactly one
  transformation: strip leading and trailing ASCII whitespace (spaces,
  tabs) from every field of every data row.
- R3.2: No other transformation is applied: no case folding, no
  reformatting, no deduplication, no sorting or reordering, no type
  coercion beyond the stripping in R3.1.

## 4. The one validation rule

- R4.1: After the R3.1 transformation, a row is **valid** if and only if its
  `email` field satisfies all of the following:
  - contains exactly one `@`;
  - has a non-empty local part before the `@` with no whitespace;
  - has a non-empty domain part after the `@` that contains at least one
    `.`, does not start or end with `.`, and contains no whitespace.
  For R4.1, "whitespace" means ASCII space (U+0020) and horizontal tab
  (U+0009) only, the same set stripped in R3.1.
- R4.2: All other fields are carried through without validation. In
  particular there is no range, format, uniqueness, or non-emptiness rule on
  `id`, `name`, or `age` beyond the whitespace stripping in R3.1.
- R4.3: Rows failing the R4.1 rule are dropped. They appear in no output
  file. No other rows are dropped.

## 5. The one output

- R5.1: On success the engine writes exactly one output file to `OUTPUT`:
  a UTF-8 encoded CSV with the same header `id,name,email,age`, containing
  only the valid rows (R4.1) with transformed values (R3.1), in original
  input order.
- R5.2: An input with a valid header and zero valid rows succeeds and
  writes an output file containing only the header row.
- R5.3: The engine overwrites `OUTPUT` if it already exists. The parent
  directory of `OUTPUT` must already exist; a missing parent directory or
  an unwritable `OUTPUT` path is an error (exit `1`).
- R5.4: The output is written with Python's `csv` module defaults (excel
  dialect, `QUOTE_MINIMAL`, embedded quotes escaped by doubling) with
  `lineterminator="\n"`; every row including the last is terminated by `\n`.
  There are no additional output files,
  report files, or required stdout/stderr content on success; any
  informational stdout text is permitted but is not part of this contract
  and must not be required by tests.

## 6. Boundary cases (normative)

- R6.1: A field containing only whitespace becomes the empty string after
  R3.1 (and therefore fails R4.1 if it is the `email` field).
- R6.2: Duplicate `id` values are allowed and preserved in input order when
  their rows are valid.
- R6.3: Quoted CSV fields, embedded commas, and surrounding whitespace are
  handled per standard CSV parsing (Python's `csv` module defaults, excel
  dialect) before R3.1 stripping applies.
- R6.4: The engine streams rows and must handle at least the 100-row
  reference fixture size with no row-count-dependent behavior.

## 7. Non-goals

- No configuration files, no second output or report file, no network
  access, no database, and no additional transformations or validation
  rules beyond R3.1 and R4.1.

## 8. Acceptance checklist

- `python3 dq_engine.py INPUT OUTPUT` with the 100-row fixture exits `0`
  and writes one CSV at `OUTPUT` with header `id,name,email,age`.
- Every output row passes R4.1, carries stripped values (R3.1), and appears
  in input order; every valid input row appears in the output.
- Wrong argument count exits `2`; missing input, bad header, or
  unparseable CSV exits `1` with no `OUTPUT` created; an empty (header-only)
  input writes a header-only output and exits `0`.
