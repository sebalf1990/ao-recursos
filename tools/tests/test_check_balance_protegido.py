"""
Tests for the Balance.dat protected-section guard.

The case that matters is the NEGATIVE one: a sync that replaces Balance.dat with the public
upstream copy silently drops [ElementalMatrixForNpcs] (upstream does not publish it). The server
then hits a subscript error while loading the matrix and leaves it at 0, so every elemental hit
against a creature deals 0 damage with a single log line as the only warning (plan 17.001, D8).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_balance_protegido as guard

VALID = "\r\n".join([
    "[EXTRA]",
    "HomeTimer=100",
    "",
    "[ElementalMatrixForNpcs]",
    "' " + guard.PROTECTION_MARKER + " (plan 17.001 D8)",
    "Row1=0.5 0.5 2 1",
    "Row2=2 0.5 1 0.5",
    "Row3=0.5 1 0.5 2",
    "Row4=1 2 0.5 0.5",
    "",
    "[BACKSTAB]",
    "Chance=1",
    "",
])


def problems(text: str) -> list[str]:
    return guard.check(text)


class ValidFile(unittest.TestCase):
    def test_valid_matrix_has_no_problems(self):
        self.assertEqual(problems(VALID), [])

    def test_header_is_case_insensitive(self):
        self.assertEqual(problems(VALID.replace("[ElementalMatrixForNpcs]", "[ELEMENTALMATRIXFORNPCS]")), [])

    def test_inline_comment_after_values_is_ignored(self):
        self.assertEqual(problems(VALID.replace("Row1=0.5 0.5 2 1", "Row1=0.5 0.5 2 1 ' fire row")), [])


class BrokenFile(unittest.TestCase):
    def assertFlags(self, text: str, fragment: str):
        found = problems(text)
        self.assertTrue(any(fragment in p for p in found), "expected a problem mentioning %r, got %r" % (fragment, found))

    def test_missing_section_is_flagged(self):
        start = VALID.index("[ElementalMatrixForNpcs]")
        end = VALID.index("[BACKSTAB]")
        self.assertFlags(VALID[:start] + VALID[end:], "falta la seccion")

    def test_duplicated_section_is_flagged(self):
        self.assertFlags(VALID + "[ElementalMatrixForNpcs]\r\nRow1=1 1 1 1\r\n", "duplicada")

    def test_missing_row_is_flagged(self):
        self.assertFlags(VALID.replace("Row3=0.5 1 0.5 2\r\n", ""), "Row3")

    def test_short_row_is_flagged(self):
        self.assertFlags(VALID.replace("Row2=2 0.5 1 0.5", "Row2=2 0.5 1"), "Row2")

    def test_non_numeric_value_is_flagged(self):
        self.assertFlags(VALID.replace("Row4=1 2 0.5 0.5", "Row4=1 x 0.5 0.5"), "Row4")

    def test_zero_multiplier_is_flagged(self):
        self.assertFlags(VALID.replace("Row1=0.5 0.5 2 1", "Row1=0.5 0 2 1"), "Row1")

    def test_commented_out_row_counts_as_missing(self):
        self.assertFlags(VALID.replace("Row1=0.5 0.5 2 1", "'Row1=0.5 0.5 2 1"), "Row1")

    def test_missing_protection_note_is_flagged(self):
        self.assertFlags(VALID.replace("' " + guard.PROTECTION_MARKER + " (plan 17.001 D8)\r\n", ""), "nota")

    def test_note_in_another_section_does_not_count(self):
        moved = VALID.replace("' " + guard.PROTECTION_MARKER + " (plan 17.001 D8)\r\n", "")
        moved = moved.replace("HomeTimer=100", "HomeTimer=100\r\n' " + guard.PROTECTION_MARKER)
        self.assertFlags(moved, "nota")


class FileLevel(unittest.TestCase):
    def run_on(self, data: bytes) -> tuple[int, list[str]]:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Balance.dat"
            path.write_bytes(data)
            return guard.check_file(path)

    def test_valid_file_passes(self):
        code, found = self.run_on(VALID.encode("cp1252"))
        self.assertEqual((code, found), (0, []))

    def test_lone_lf_is_flagged(self):
        code, found = self.run_on(VALID.replace("\r\n", "\n").encode("cp1252"))
        self.assertEqual(code, 1)
        self.assertTrue(any("CRLF" in p for p in found), found)

    def test_doubled_cr_is_flagged(self):
        code, found = self.run_on(VALID.replace("\r\n", "\r\r\n").encode("cp1252"))
        self.assertEqual(code, 1)
        self.assertTrue(any("CRLF" in p for p in found), found)

    def test_utf8_bytes_are_flagged(self):
        code, found = self.run_on(VALID.replace("HomeTimer", "Da\u00f1oTimer").encode("utf-8"))
        self.assertEqual(code, 1)
        self.assertTrue(any("UTF-8" in p for p in found), found)

    def test_missing_file_is_flagged(self):
        code, found = guard.check_file(Path("Z:/does/not/exist/Balance.dat"))
        self.assertEqual(code, 1)
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
