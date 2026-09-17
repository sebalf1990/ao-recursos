"""
Guard for the protected sections of Dat/Balance.dat.

Run it after ANY change that touches Balance.dat, and always after a sync from upstream:

    python tools/check_balance_protegido.py            # checks Dat/Balance.dat of this repo
    python tools/check_balance_protegido.py <path>     # checks another copy (a VM dump, a backup)

Exit code 0 = fine, 1 = at least one problem (each one is printed).

Why it exists (plan 17.001, D8): [ElementalMatrixForNpcs] belongs to AO20's elemental engine and
is NOT in the Balance.dat of the public upstream repo. A sync that replaces the file drops it. The
server then reads the default "1" for each row, splits it into a single value and raises a
subscript error on the second column (dev/server/Codigo/FileIO.bas, "ElementalMatrixForNpcs"
block), leaving the matrix at 0: every elemental hit against a creature is multiplied by 0.

The file is cp1252 + CRLF. This tool only reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Must match MAX_ELEMENT_TAGS in dev/server/Codigo/Declares.bas.
MATRIX_SIZE = 4
MATRIX_SECTION = "ElementalMatrixForNpcs"
# A comment line carrying this text must live INSIDE the section, so whoever edits the file sees it.
PROTECTION_MARKER = "SECCION PROTEGIDA"

COMMENT_PREFIXES = ("'", "#", ";")


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split into (upper-cased section name, body lines), in file order. Duplicates are kept."""
    found: list[tuple[str, list[str]]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            found.append((stripped[1:stripped.index("]")].strip().upper(), []))
        elif found:
            found[-1][1].append(line)
    return found


def _check_matrix(text: str) -> list[str]:
    bodies = [body for name, body in _sections(text) if name == MATRIX_SECTION.upper()]
    if not bodies:
        return ["falta la seccion [%s]: el dano elemental contra criaturas quedaria en 0" % MATRIX_SECTION]
    if len(bodies) > 1:
        return ["la seccion [%s] esta duplicada (%d veces): el server lee solo una" % (MATRIX_SECTION, len(bodies))]

    problems: list[str] = []
    body = bodies[0]
    if not any(l.strip().startswith(COMMENT_PREFIXES) and PROTECTION_MARKER in l for l in body):
        problems.append("falta la nota '%s' dentro de [%s]" % (PROTECTION_MARKER, MATRIX_SECTION))

    rows: dict[str, str] = {}
    for line in body:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith(COMMENT_PREFIXES):
            key, value = stripped.split("=", 1)
            rows.setdefault(key.strip().upper(), value.split("'")[0].strip())

    for index in range(1, MATRIX_SIZE + 1):
        key = "Row%d" % index
        raw = rows.get(key.upper())
        if raw is None:
            problems.append("%s: falta la fila" % key)
            continue
        values = raw.split()
        if len(values) != MATRIX_SIZE:
            problems.append("%s: tiene %d valores, deben ser %d (%r)" % (key, len(values), MATRIX_SIZE, raw))
            continue
        for value in values:
            try:
                number = float(value)
            except ValueError:
                problems.append("%s: %r no es un numero" % (key, value))
                continue
            if number <= 0:
                problems.append("%s: multiplicador %r <= 0 anula el dano de ese par de elementos" % (key, value))
    return problems


def check(text: str) -> list[str]:
    """Return the list of problems found in an already-decoded Balance.dat. Empty list = fine."""
    return _check_matrix(text)


def check_file(path: Path) -> tuple[int, list[str]]:
    """Check encoding, line endings and protected sections of one file. Returns (exit code, problems)."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return 1, ["no se pudo leer %s: %s" % (path, exc)]

    problems: list[str] = []
    if b"\r\r\n" in data or data.count(b"\n") != data.count(b"\r\n"):
        problems.append("CRLF roto: %d CRLF, %d LF, %d \\r\\r\\n" % (data.count(b"\r\n"), data.count(b"\n"), data.count(b"\r\r\n")))
    try:
        data.decode("utf-8")
        looks_utf8 = any(byte >= 0x80 for byte in data)
    except UnicodeDecodeError:
        looks_utf8 = False
    if looks_utf8:
        problems.append("el archivo parece UTF-8 y debe ser cp1252 (hay bytes altos que decodifican como UTF-8)")

    problems.extend(check(data.decode("cp1252")))
    return (1 if problems else 0), problems


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "Dat" / "Balance.dat"
    code, problems = check_file(path)
    for problem in problems:
        print("PROBLEMA:", problem)
    print("%s -> %s" % (path, "OK" if code == 0 else "%d problema(s)" % len(problems)))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
