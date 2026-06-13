# -*- coding: utf-8 -*-
"""Fase 3 batch OBJs — fix 1 post-smoke-test (plan 10.001).

Repara las regresiones detectadas por el smoke test del usuario:

1. VISUAL: el update oficial 2026-06-08 referencia bodies/grhs que no existen en
   nuestra base visual (cuerpos.dat del 4/5; el cliente oficial los resuelve por
   un mecanismo que nuestro fork no tiene — ver bitacora). Para cada clave visual
   (Ropaje*, RAZAALTOS/RAZABAJOS, NumRopaje, GrhIndex) cuyo valor NUEVO no existe
   localmente y cuyo valor de BACKUP si existia: se restaura el valor del backup.
   Stubs nuevos sin historia quedan como estan (cascara, se loguean).

2. COLISIONES: items custom nuestros pisados por slots oficiales se reubican a la
   franja protegida: 5170 Detectar Personajes -> 9014, 6240 Pluma de Fenix -> 9015,
   6242 Alas de Fenix -> 9016. NumOBJs 9013 -> 9016.

3. QUESTS 259/260 (custom): re-apuntan RequiredOBJ1 6240 -> 9015 y
   RewardObj1 6242 -> 9016.

4. Lockfile: protege 9014-9016.
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_objs_fase3 import split_blocks, OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
BKP = r"c:\AO20\backups\2026-06-11.fase3-batch-objs\obj.dat"
INIT = r"c:\AO20\dev\Recursos\init"

BODY_KEYS = re.compile(r"^(Ropaje\w+|RAZAALTOS|RAZABAJOS|NumRopaje)$", re.I)
GRH_KEYS = re.compile(r"^GrhIndex$", re.I)
RELOC = {5170: 9014, 6240: 9015, 6242: 9016}


def load_bodies():
    t = open(os.path.join(INIT, "cuerpos.dat"), "rb").read().decode("cp1252", errors="replace")
    return {int(n) for n in re.findall(r"(?im)^\s*\[BODY(\d+)\]", t)}


def load_grhs():
    b = open(os.path.join(INIT, "graficos.ind"), "rb").read()
    o = 8
    count = struct.unpack_from("<i", b, 4)[0]
    ids = set()
    while o < len(b):
        gid = struct.unpack_from("<i", b, o)[0]; o += 4
        frames = struct.unpack_from("<h", b, o)[0]; o += 2
        if frames <= 0:
            break
        o += (4 * frames + 4) if frames > 1 else (4 + 2 + 2 + 2 + 2)
        ids.add(gid)
        if gid == count:
            break
    return ids


def parse_fields(text):
    """{obj_id: {key_lower: valor}} de un obj.dat (solo secciones activas)."""
    out = {}
    for m in re.finditer(r"(?ms)^\[OBJ(\d+)\][^\n]*\n(.*?)(?=^'?\s*\[|\Z)", text):
        d = {}
        for ln in m.group(2).split("\n"):
            ln = ln.strip()
            if not ln or ln.startswith("'") or "=" not in ln:
                continue
            k, _, v = ln.partition("=")
            d.setdefault(k.strip().lower(), v.split("'")[0].strip())
        out[int(m.group(1))] = d
    return out


def raw_section(text, n):
    m = re.search(r"^\[OBJ" + str(n) + r"\][^\n]*\r\n(.*?)(?=^'?\s*\[|\Z)", text, re.S | re.M)
    return m.group(0) if m else None


def main():
    bodies = load_bodies()
    grhs = load_grhs()
    path = os.path.join(OURS_DAT, "obj.dat")
    dat = open(path, "rb").read().decode("cp1252")
    bkp = open(BKP, "rb").read().decode("cp1252")
    bkp_fields = parse_fields(bkp)

    def valid(key, val):
        if not val.isdigit() or int(val) == 0:
            return True  # 0/vacio = sin visual, no es referencia rota
        if BODY_KEYS.match(key):
            return int(val) in bodies
        if GRH_KEYS.match(key):
            return int(val) in grhs
        return True

    restored, unresolved = [], []
    blocks = split_blocks(dat)
    out_blocks = []
    for bid, commented, lines in blocks:
        if bid is None or commented:
            out_blocks.append(lines)
            continue
        old = bkp_fields.get(bid, {})
        new_lines = list(lines)
        for i, ln in enumerate(new_lines):
            s = ln.strip()
            if not s or s.startswith("'") or "=" not in s or s.startswith("["):
                continue
            k, _, v = ln.partition("=")
            key = k.strip()
            val = v.split("'")[0].strip()
            if not (BODY_KEYS.match(key) or GRH_KEYS.match(key)) or valid(key, val):
                continue
            prev = old.get(key.lower())
            if prev is not None and valid(key, prev) and prev != val:
                new_lines[i] = f"{key}={prev}"
                restored.append((bid, key, val, prev))
            else:
                unresolved.append((bid, key, val))
        out_blocks.append(new_lines)

    result = "\r\n".join("\r\n".join(b) for b in out_blocks)

    # --- reubicaciones a franja protegida ---
    reloc_secs = []
    for old_id, new_id in sorted(RELOC.items()):
        sec = raw_section(bkp, old_id)
        assert sec, f"OBJ{old_id} no esta en el backup"
        lines = sec.rstrip("\r\n").split("\r\n")
        hdr = lines[0]
        name = next((l.split("=", 1)[1] for l in lines[1:] if l.lower().startswith("name=")), "?")
        lines[0] = (f"[OBJ{new_id}] 'Reubicado de OBJ{old_id} por colision con slot oficial "
                    f"(plan 10.001 fase 3)")
        reloc_secs.append(("\r\n".join(lines) + "\r\n", new_id, name))
    result = result.rstrip("\r\n") + "\r\n\r\n" + "\r\n".join(s for s, _, _ in reloc_secs)
    # nota: con CRLF el `$` de re.M no matchea antes de \r; reemplazo literal
    assert "NumOBJs=9013\r\n" in result, "contador NumOBJs no encontrado"
    result = result.replace("NumOBJs=9013\r\n", "NumOBJs=9016\r\n", 1)

    open(path, "w", encoding="cp1252", newline="").write(result)
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto en obj.dat"

    # --- quests 259/260 ---
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    q = open(qpath, "rb").read().decode("cp1252")
    q, n1 = re.subn(r"(?im)^(RequiredOBJ1\s*=\s*)6240\b", r"\g<1>9015", q)
    q, n2 = re.subn(r"(?im)^(RewardObj1\s*=\s*)6242\b", r"\g<1>9016", q)
    open(qpath, "w", encoding="cp1252", newline="").write(q)
    qb = open(qpath, "rb").read()
    assert qb.count(b"\n") == qb.count(b"\r\n"), "CRLF roto en Quests.DAT"

    # --- lockfile ---
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    objs = set(lock.setdefault("protected", {}).get("OBJ", []))
    lock["protected"]["OBJ"] = sorted(objs | {9014, 9015, 9016})
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # --- reporte ---
    print(f"claves visuales restauradas del backup: {len(restored)} "
          f"en {len({r[0] for r in restored})} secciones")
    for r in restored[:12]:
        print(f"   OBJ{r[0]}.{r[1]}: {r[2]} -> {r[3]}")
    if len(restored) > 12:
        print(f"   ... y {len(restored)-12} mas")
    print(f"sin resolver (stubs/cascara, quedan como estan): {len(unresolved)} claves "
          f"en {len({u[0] for u in unresolved})} secciones")
    for s, new_id, name in reloc_secs:
        print(f"reubicado: OBJ{new_id} = {name}")
    print(f"quests re-apuntadas: RequiredOBJ1 6240->9015 x{n1}, RewardObj1 6242->9016 x{n2}")
    final = parse_fields(open(path, "rb").read().decode("cp1252"))
    for n, want in ((9014, "Detectar Personajes"), (9015, "Pluma de Fenix"), (9016, "Alas de Fenix")):
        got = final.get(n, {}).get("name", "?")
        print(f"  OBJ{n}.Name = {got!r}")
    for n in (3500, 3502):
        rops = {k: v for k, v in final.get(n, {}).items() if k.startswith("ropaje")}
        bad = [v for v in rops.values() if v.isdigit() and int(v) > 0 and int(v) not in bodies]
        print(f"  OBJ{n}: ropajes rotos restantes: {bad if bad else 'ninguno'}")


if __name__ == "__main__":
    main()
