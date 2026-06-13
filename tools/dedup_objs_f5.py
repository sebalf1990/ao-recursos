# -*- coding: utf-8 -*-
"""F5: deduplica los 5 OBJs con secciones repetidas (preexistentes).

Riesgo que cierra: con 2 secciones [OBJn], el cliente (localindex, last-wins)
y el server (clsIniManager) pueden quedarse con copias DISTINTAS → desync de
nombre/grh. Se conserva la copia que coincide con el nombre OFICIAL (ley);
si ninguna coincide (custom sin oficial), se conserva la PRIMERA. Las demás
se eliminan.
"""
import re
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from diff_fase2 import OURS_DAT
import os

DUPS = [2395, 2465, 2513, 2851, 3418]


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def main():
    path = os.path.join(OURS_DAT, "obj.dat")
    dat = open(path, "rb").read().decode("cp1252")
    ley = open(r"c:\AO20\dev\oficial\recursos_20260610\init\sp_localindex.dat",
               "rb").read().decode("cp1252")

    def ley_name(n):
        m = re.search(r"(?ms)^\[OBJ%d\][^\n]*\n(.*?)(?=^\[|\Z)" % n, ley)
        if not m:
            return None
        g = re.search(r"(?im)^Name=([^\r\n]+)", m.group(1))
        return g.group(1).strip() if g else None

    removed = []
    for n in DUPS:
        # ubica todas las secciones activas [OBJn] (header + cuerpo hasta proximo header)
        pat = re.compile(r"(?ms)^\[OBJ%d\][^\n]*\r\n.*?(?=^'?\s*\[OBJ\d+\]|\Z)" % n)
        blocks = list(pat.finditer(dat))
        if len(blocks) < 2:
            continue
        official = norm(ley_name(n))
        # elegir indice a conservar
        keep = 0
        for i, b in enumerate(blocks):
            g = re.search(r"(?im)^Name=([^\r\n]+)", b.group(0))
            if g and official and norm(g.group(1)) == official:
                keep = i
                break
        # eliminar los demas (de atras hacia adelante para no correr offsets)
        for i in reversed(range(len(blocks))):
            if i == keep:
                continue
            b = blocks[i]
            nm = re.search(r"(?im)^Name=([^\r\n]+)", b.group(0))
            removed.append((n, nm.group(1).strip() if nm else "?"))
            dat = dat[:b.start()] + dat[b.end():]

    dat = re.sub(r"(\r\n){3,}", "\r\n\r\n", dat)
    open(path, "w", encoding="cp1252", newline="").write(dat)
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"

    hdrs = [int(x) for q, x in re.findall(r"(?m)^('*)\s*\[OBJ(\d+)\]", dat) if not q]
    dups_left = sorted({x for x in hdrs if hdrs.count(x) > 1})
    print(f"copias eliminadas: {len(removed)}")
    for n, nm in removed:
        print(f"   OBJ{n}: quitada copia {nm!r}")
    print(f"duplicados restantes: {dups_left or 'ninguno'} | OBJ unicos: {len(set(hdrs))}")
    for n in DUPS:
        m = re.search(r"(?ms)^\[OBJ%d\][^\n]*\n(.*?)(?=^.?\s*\[|\Z)" % n, dat)
        g = re.search(r"(?im)^Name=([^\r\n]+)", m.group(1))
        print(f"   OBJ{n} queda: {g.group(1).strip()!r} (oficial: {ley_name(n)!r})")


if __name__ == "__main__":
    main()
