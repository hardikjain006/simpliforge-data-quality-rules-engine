"""Repository-native tests for dq_engine.py (standard library only)."""

import csv
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "dq_engine.py"
FIXTURE = ROOT / "data" / "input.csv"
HEADER = ["id", "name", "email", "age"]
HEADER_LINE = "id,name,email,age\n"


def run_engine(*args):
    return subprocess.run(
        [sys.executable, str(ENGINE), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def reference_valid(email):
    """Independent re-derivation of the R4.1 email rule."""
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


def reference_output_rows(input_text):
    """Independent re-derivation of expected output rows for valid inputs."""
    reader = csv.reader(io.StringIO(input_text))
    header = next(reader)
    assert header == HEADER, header
    out = []
    for row in reader:
        if len(row) != 4:
            raise AssertionError("bad test input row: %r" % (row,))
        stripped = [field.strip(" \t") for field in row]
        if reference_valid(stripped[2]):
            out.append(stripped)
    return out


class EngineTest(unittest.TestCase):
    def test_fixture_has_100_data_rows(self):
        with open(FIXTURE, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(len(rows) - 1, 100)

    def test_fixture_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            proc = run_engine(str(FIXTURE), out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as handle:
                first = handle.read()
            with open(out, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
        self.assertTrue(first.startswith(b"id,name,email,age\n"))
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual(rows[0], HEADER)
        with open(FIXTURE, "r", encoding="utf-8", newline="") as handle:
            expected = reference_output_rows(handle.read())
        self.assertEqual(rows[1:], expected)
        self.assertGreater(len(rows) - 1, 0)
        for row in rows[1:]:
            self.assertTrue(reference_valid(row[2]), row)
            for field in row:
                self.assertEqual(field, field.strip(" \t"), row)
        # Deterministic: same input bytes -> same output bytes.
        with tempfile.TemporaryDirectory() as tmp:
            out2 = os.path.join(tmp, "out2.csv")
            proc = run_engine(str(FIXTURE), out2)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out2, "rb") as handle:
                second = handle.read()
        self.assertEqual(first, second)

    def test_output_uses_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            proc = run_engine(str(FIXTURE), out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as handle:
                raw = handle.read()
        self.assertNotIn(b"\r", raw)

    def test_valid_emails_accepted(self):
        for email in (
            "a@b.co",
            "first.last@sub.example.co.uk",
            "user+tag@example.com",
            "first_last@mail-example.com",
            "x@y.z",
        ):
            with self.subTest(email=email):
                with tempfile.TemporaryDirectory() as tmp:
                    src = os.path.join(tmp, "in.csv")
                    out = os.path.join(tmp, "out.csv")
                    with open(src, "w", encoding="utf-8", newline="") as h:
                        h.write(HEADER_LINE + "1,N,%s,30\n" % email)
                    proc = run_engine(src, out)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    with open(out, "r", encoding="utf-8", newline="") as h:
                        rows = list(csv.reader(h))
                self.assertEqual(rows, [HEADER, ["1", "N", email, "30"]])

    def test_invalid_emails_dropped(self):
        for email in (
            "no-at-example.com",
            "a@b@c.com",
            "@example.com",
            "user@",
            "user@example",
            "user@.example.com",
            "user@example.com.",
            "user @example.com",
            "user@exam ple.com",
            "user\t@example.com",
            "",
            "   ",
            "\t",
        ):
            with self.subTest(email=email):
                with tempfile.TemporaryDirectory() as tmp:
                    src = os.path.join(tmp, "in.csv")
                    out = os.path.join(tmp, "out.csv")
                    with open(src, "w", encoding="utf-8", newline="") as h:
                        h.write(HEADER_LINE + "1,Name,%s,30\n" % email)
                    proc = run_engine(src, out)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    with open(out, "r", encoding="utf-8", newline="") as h:
                        rows = list(csv.reader(h))
                self.assertEqual(rows, [HEADER])

    def test_whitespace_stripping_transformation(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    HEADER_LINE
                    + "  7 ,\t Padded Name \t,  pad@example.com\t,  27 \n"
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(
            rows, [HEADER, ["7", "Padded Name", "pad@example.com", "27"]]
        )

    def test_no_case_folding_reorder_or_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    HEADER_LINE
                    + "9,ZED UPPER,Zed@Example.COM,50\n"
                    + "9,ZED UPPER,Zed@Example.COM,50\n"
                    + "3,aaa,a@example.com,21\n"
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(
            rows,
            [
                HEADER,
                ["9", "ZED UPPER", "Zed@Example.COM", "50"],
                ["9", "ZED UPPER", "Zed@Example.COM", "50"],
                ["3", "aaa", "a@example.com", "21"],
            ],
        )

    def test_blank_lines_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    HEADER_LINE
                    + "1,A,a@example.com,20\n"
                    + "\n"
                    + "   \n"
                    + "\t \t\n"
                    + "2,B,b@example.com,21\n"
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(
            rows,
            [
                HEADER,
                ["1", "A", "a@example.com", "20"],
                ["2", "B", "b@example.com", "21"],
            ],
        )

    def test_delimiter_only_line_is_data_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE + "1,A,a@example.com,20\n,,,\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(rows, [HEADER, ["1", "A", "a@example.com", "20"]])

    def test_leading_blank_line_fails_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write("\n" + HEADER_LINE + "1,A,a@example.com,20\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.strip())
            self.assertFalse(os.path.exists(out))

    def test_wrong_field_count_fails(self):
        for body in ("1,A,a@example.com\n", "1,A,a@example.com,20,EXTRA\n"):
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as tmp:
                    src = os.path.join(tmp, "in.csv")
                    out = os.path.join(tmp, "out.csv")
                    with open(src, "w", encoding="utf-8", newline="") as h:
                        h.write(HEADER_LINE + body)
                    proc = run_engine(src, out)
                    self.assertEqual(proc.returncode, 1, body)
                    self.assertTrue(proc.stderr.strip())
                    self.assertFalse(os.path.exists(out))

    def test_bad_headers_fail(self):
        bodies = [
            "ide,name,email,age\n",  # renamed
            "id,name,age,email\n",  # reordered
            "id,name,email\n",  # missing
            "id,name,email,age,extra\n",  # extra
            "id, name,email,age\n",  # padded
            "id,name,email,age \n",  # trailing space
            "\ufeffid,name,email,age\n",  # BOM not tolerated
            "",  # empty file
        ]
        for body in bodies:
            with self.subTest(body=repr(body)):
                with tempfile.TemporaryDirectory() as tmp:
                    src = os.path.join(tmp, "in.csv")
                    out = os.path.join(tmp, "out.csv")
                    with open(src, "w", encoding="utf-8", newline="") as h:
                        h.write(body + "1,A,a@example.com,20\n" if body else "")
                    proc = run_engine(src, out)
                    self.assertEqual(proc.returncode, 1, repr(body))
                    self.assertTrue(proc.stderr.strip())
                    self.assertFalse(os.path.exists(out))

    def test_quoted_header_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    '"id","name","email","age"\n1,A,a@example.com,20\n'
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(rows, [HEADER, ["1", "A", "a@example.com", "20"]])

    def test_quoted_fields_and_embedded_commas(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    HEADER_LINE
                    + '1,"Doe, Jane",jane@example.com,33\n'
                    + '2,"  Spaced, Name  ",spaced@example.com,34\n'
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as h:
                raw = h.read()
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertIn(b'"Doe, Jane"', raw)
        self.assertEqual(
            rows,
            [
                HEADER,
                ["1", "Doe, Jane", "jane@example.com", "33"],
                ["2", "Spaced, Name", "spaced@example.com", "34"],
            ],
        )

    def test_missing_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            proc = run_engine(os.path.join(tmp, "nope.csv"), out)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.strip())
            self.assertFalse(os.path.exists(out))

    def test_wrong_argument_count_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            for argv in ([], [str(FIXTURE)], [str(FIXTURE), out, "extra"]):
                with self.subTest(argv=argv):
                    if os.path.exists(out):
                        os.remove(out)
                    proc = run_engine(*argv)
                    self.assertEqual(proc.returncode, 2, argv)
                    self.assertTrue(proc.stderr.strip())
                    self.assertFalse(os.path.exists(out))

    def test_header_only_input_writes_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE)
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as h:
                self.assertEqual(h.read(), b"id,name,email,age\n")

    def test_all_invalid_writes_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE + "1,A,not-an-email,20\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as h:
                self.assertEqual(h.read(), b"id,name,email,age\n")

    def test_output_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE + "1,A,a@example.com,20\n")
            with open(out, "w", encoding="utf-8") as h:
                h.write("stale content\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(rows, [HEADER, ["1", "A", "a@example.com", "20"]])

    def test_missing_parent_dir_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE + "1,A,a@example.com,20\n")
            out = os.path.join(tmp, "no-such-dir", "out.csv")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.strip())

    def test_failed_run_leaves_existing_output_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write("bad,header\n1,2\n")
            with open(out, "w", encoding="utf-8") as h:
                h.write("keep me\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 1)
            with open(out, "r", encoding="utf-8") as h:
                self.assertEqual(h.read(), "keep me\n")

    def test_unparseable_csv_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(HEADER_LINE + '1,"unclosed quote,a@example.com,20\n')
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.strip())
            self.assertFalse(os.path.exists(out))

    def test_non_utf8_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "wb") as h:
                h.write(b"id,name,email,age\n1,Caf\xe9,a@example.com,20\n")
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(proc.stderr.strip())
            self.assertFalse(os.path.exists(out))

    def test_directory_as_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            proc = run_engine(tmp, out)
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(os.path.exists(out))

    def test_r42_passthrough_empty_and_arbitrary_non_email_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                h.write(
                    HEADER_LINE
                    + ",Name,a@example.com,30\n"
                    + "1,,a@example.com,30\n"
                    + "1,Name,a@example.com,\n"
                    + "1,Name,a@example.com,not-a-number\n"
                    + "1,   ,a@example.com,30\n"
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(
            rows,
            [
                HEADER,
                ["", "Name", "a@example.com", "30"],
                ["1", "", "a@example.com", "30"],
                ["1", "Name", "a@example.com", ""],
                ["1", "Name", "a@example.com", "not-a-number"],
                ["1", "", "a@example.com", "30"],
            ],
        )

    def test_embedded_double_quote_escaping_rfc4180(self):
        plain = 'He said "hi"'
        with_comma = 'He said "hi", friend'
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                writer = csv.writer(h, lineterminator="\n")
                writer.writerow(HEADER)
                writer.writerow(["1", plain, "a@example.com", "30"])
                writer.writerow(["2", with_comma, "b@example.com", "31"])
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "rb") as h:
                raw = h.read()
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertIn(b'He said ""hi""', raw)
        self.assertEqual(
            rows,
            [
                HEADER,
                ["1", plain, "a@example.com", "30"],
                ["2", with_comma, "b@example.com", "31"],
            ],
        )

    def test_whitespace_set_is_space_and_tab_only(self):
        # R3.1/R4.1 treat only U+0020 and U+0009 as whitespace. U+00A0
        # is neither stripped nor email-invalidating, so it separates
        # the exact-set implementation from parameterless-strip or
        # generic-whitespace variants while staying on one CSV line.
        nbsp = " "
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.csv")
            out = os.path.join(tmp, "out.csv")
            with open(src, "w", encoding="utf-8", newline="") as h:
                writer = csv.writer(h, lineterminator="\n")
                writer.writerow(HEADER)
                writer.writerow(
                    ["1", nbsp + "Pad" + nbsp, "a@example.com", "30"]
                )
                writer.writerow(
                    ["2", "Name", "a" + nbsp + "b@example.com", "30"]
                )
            proc = run_engine(src, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, "r", encoding="utf-8", newline="") as h:
                rows = list(csv.reader(h))
        self.assertEqual(
            rows,
            [
                HEADER,
                ["1", nbsp + "Pad" + nbsp, "a@example.com", "30"],
                ["2", "Name", "a" + nbsp + "b@example.com", "30"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
