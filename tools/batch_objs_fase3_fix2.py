# -*- coding: utf-8 -*-
"""Fase 3 batch OBJs — fix 2 (plan 10.001): quimeras y reubicacion de customs.

Decision del usuario 2026-06-11: los items custom/test pisados por slots oficiales
se CONSERVAN como ejemplos -> se reubican a la franja protegida.

1. QUIMERAS: 6241/6272/6273/6274 fueron patcheados (mismo ObjType) pero el oficial
   repropuso el slot -> quedaron con nombre oficial y campos nuestros mezclados.
   Se reconstruyen limpios desde la ley (mismo builder del batch).
2. REUBICACION: 22 items custom nuestros (backup pre-batch) -> OBJ9017-9038.
3. Quest que premiaba Huevo de Fenix: RewardObj1 6241 -> 9017.
4. NumOBJs 9016 -> 9038. Lockfile protege 9017-9038.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_objs_fase3 import build_stub, split_blocks, OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
BKP = r"c:\AO20\backups\2026-06-11.fase3-batch-objs\obj.dat"

CHIMERAS = [6241, 6272, 6273, 6274]
RELOC = {  # id viejo (contenido en backup) -> id nuevo protegido
    6241: 9017, 6250: 9018,
    6261: 9019, 6262: 9020, 6263: 9021, 6264: 9022, 6265: 9023, 6266: 9024,
    6267: 9025, 6268: 9026, 6269: 9027, 6270: 9028, 6271: 9029,
    6272: 9030, 6273: 9031, 6274: 9032,
    6275: 9033, 6276: 9034, 6277: 9035, 6278: 9036, 6279: 9037, 6280: 9038,
}


def raw_section(text, n):
    m = re.search(r"^\[OBJ" + str(n) + r"\][^\n]*\r\n(.*?)(?=^'?\s*\[|\Z)", text, re.S | re.M)
    return m.group(0) if m else None


def main():
    path = os.path.join(OURS_DAT, "obj.dat")
    dat = open(path, "rb").read().decode("cp1252")
    bkp = open(BKP, "rb").read().decode("cp1252")

    # 1) reconstruir quimeras desde la ley
    blocks = split_blocks(dat)
    out_blocks = []
    rebuilt = []
    for bid, commented, lines in blocks:
        if bid in CHIMERAS and not commented:
            stub, _ = build_stub(bid)
            out_blocks.append(stub)
            rebuilt.append(bid)
        else:
            out_blocks.append(lines)
    assert sorted(rebuilt) == CHIMERAS, f"quimeras no encontradas: {rebuilt}"
    result = "\r\n".join("\r\n".join(b) for b in out_blocks)

    # 2) reubicar customs del backup a 9017+
    reloc_secs = []
    for old_id, new_id in sorted(RELOC.items(), key=lambda kv: kv[1]):
        sec = raw_section(bkp, old_id)
        assert sec, f"OBJ{old_id} no esta en el backup"
        lines = sec.rstrip("\r\n").split("\r\n")
        name = next((l.split("=", 1)[1] for l in lines[1:] if l.lower().startswith("name=")), "?")
        lines[0] = (f"[OBJ{new_id}] 'Reubicado de OBJ{old_id} por colision con slot oficial; "
                    f"conservado como ejemplo (plan 10.001 fase 3 fix 2)")
        reloc_secs.append(("\r\n".join(lines) + "\r\n", new_id, name))
    result = result.rstrip("\r\n") + "\r\n\r\n" + "\r\n".join(s for s, _, _ in reloc_secs)

    assert "NumOBJs=9016\r\n" in result, "contador NumOBJs no encontrado"
    result = result.replace("NumOBJs=9016\r\n", "NumOBJs=9038\r\n", 1)

    open(path, "w", encoding="cp1252", newline="").write(result)
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto en obj.dat"

    # 3) quest del Huevo de Fenix
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    q = open(qpath, "rb").read().decode("cp1252")
    q, nq = re.subn(r"(?im)^(RewardObj1\s*=\s*)6241\b", r"\g<1>9017", q)
    open(qpath, "w", encoding="cp1252", newline="").write(q)
    qb = open(qpath, "rb").read()
    assert qb.count(b"\n") == qb.count(b"\r\n"), "CRLF roto en Quests.DAT"

    # 4) lockfile
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    objs = set(lock["protected"].get("OBJ", []))
    lock["protected"]["OBJ"] = sorted(objs | set(RELOC.values()))
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # reporte
    print(f"quimeras reconstruidas desde ley: {rebuilt}")
    print(f"reubicados: {len(reloc_secs)}")
    for _, new_id, name in reloc_secs:
        print(f"   OBJ{new_id} = {name}")
    print(f"quest re-apuntada RewardObj1 6241->9017: x{nq}")
    final = open(path, "rb").read().decode("cp1252")
    for n, frag in ((6241, "Cofre"), (6272, "Invocar Lobo 1"), (9017, "Huevo"),
                    (9029, "Dardo de Veneno"), (9038, "Curar Veneno")):
        m = re.search(r"(?ms)^\[OBJ%d\][^\n]*\n(.*?)(?=^.?\s*\[|\Z)" % n, final)
        nm = re.search(r"(?im)^Name=([^\r\n]+)", m.group(1)) if m else None
        got = nm.group(1).strip() if nm else "NO ESTA"
        print(f"  OBJ{n}.Name = {got!r} ({'OK' if frag.lower() in got.lower() else 'MAL'})")


if __name__ == "__main__":
    main()
