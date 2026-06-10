# -*- coding: utf-8 -*-
"""Plan 10.003: reubicación de rangos privados que colisionaron con la ley Heroism.

Remap determinista (cp1252 + CRLF preservado):
  NPC      1405..1411 -> 9000..9006   (+7595)
  OBJ      4997..5010 -> 9000..9013   (+4003)
  HECHIZO  295..307   -> 400..412     (+105)

Toca: dats server (npcs/obj/Hechizos), localindex cliente (5 idiomas),
profesiones.ini. El mapa756.csm se reescribe aparte (script node).
Reporta cada cambio. No regenera el localindex (preserva la migración v1):
hace el mismo remap quirúrgico de secciones también en el localindex.
"""
import os
import re

ROOT = r"c:\AO20"

NPC_MAP = {old: old + 7595 for old in range(1405, 1412)}      # 1405->9000
OBJ_MAP = {old: old + 4003 for old in range(4997, 5011)}      # 4997->9000
HEC_MAP = {old: old + 105 for old in range(295, 308)}         # 295->400

NEW_MAX = {"NPC": max(NPC_MAP.values()), "OBJ": max(OBJ_MAP.values()),
           "HEC": max(HEC_MAP.values())}  # 9006 / 9013 / 412

report = []


def load(path):
    return open(path, "rb").read().decode("cp1252")


def save(path, text):
    open(path, "w", encoding="cp1252", newline="").write(text)


def assert_crlf(path):
    b = open(path, "rb").read()
    crlf, lf = b.count(b"\r\n"), b.count(b"\n")
    assert lf == crlf, f"CRLF roto en {path}: {crlf} CRLF, {lf} LF, {lf-crlf} sueltos"


def remap_section_headers(text, prefix, mapping, fname):
    """Renombra [PREFIXnnn] segun mapping. Solo cambia el numero del header."""
    pat = re.compile(r"^(\s*\[)" + prefix + r"(\d+)(\])", re.M)
    return pat.sub(lambda m: _hdr(m, prefix, mapping, fname), text)


def _hdr(m, prefix, mapping, fname):
    old = int(m.group(2))
    if old in mapping:
        new = mapping[old]
        report.append(f"  {fname}: [{prefix}{old}] -> [{prefix}{new}]")
        return f"{m.group(1)}{prefix}{new}{m.group(3)}"
    return m.group(0)


def remap_obj_inventory(text, fname):
    """ObjN=<id>-<cant>  remap del <id> si esta en OBJ_MAP (inventarios de maestros)."""
    def repl(m):
        old = int(m.group(2))
        if old in OBJ_MAP:
            new = OBJ_MAP[old]
            report.append(f"  {fname}: {m.group(1).strip()}={old}-... -> {new}-...")
            return f"{m.group(1)}={new}{m.group(3)}"
        return m.group(0)
    return re.sub(r"(?im)^(Obj\d+)\s*=\s*(\d+)(-\d+)", repl, text)


def remap_hechizo_index(text, fname):
    """HechizoIndex=<id> remap si esta en HEC_MAP (pergaminos)."""
    def repl(m):
        old = int(m.group(2))
        if old in HEC_MAP:
            new = HEC_MAP[old]
            report.append(f"  {fname}: HechizoIndex={old} -> {new}")
            return f"{m.group(1)}{new}"
        return m.group(0)
    return re.sub(r"(?im)^(HechizoIndex\s*=\s*)(\d+)", repl, text)


def bump_init_counter(text, key, new_min, fname):
    """Sube el contador [INIT] <key> a max(actual, new_min)."""
    def repl(m):
        cur = int(m.group(2))
        target = max(cur, new_min)
        if target != cur:
            report.append(f"  {fname}: [INIT] {m.group(1).strip()}={cur} -> {target}")
        return f"{m.group(1)}{target}"
    # OJO: sin `\s*$` para no consumir el \r y romper el CRLF de la línea.
    return re.sub(r"(?im)^(" + key + r"\s*=\s*)(\d+)", repl, text, count=1)


def process_dat(path, prefix, mapping, counter_key, counter_min,
                do_inv=False, do_hec=False):
    fname = os.path.basename(path)
    report.append(f"[{fname}]")
    text = load(path)
    text = remap_section_headers(text, prefix, mapping, fname)
    if do_inv:
        text = remap_obj_inventory(text, fname)
    if do_hec:
        text = remap_hechizo_index(text, fname)
    text = bump_init_counter(text, counter_key, counter_min, fname)
    save(path, text)
    assert_crlf(path)


def process_localindex(path):
    fname = os.path.basename(path)
    report.append(f"[{fname}]")
    text = load(path)
    text = remap_section_headers(text, "NPC", NPC_MAP, fname)
    text = remap_section_headers(text, "OBJ", OBJ_MAP, fname)
    text = remap_section_headers(text, "HECHIZO", HEC_MAP, fname)
    # localindex usa claves en MAYUSCULAS
    text = bump_init_counter(text, "NUMNPCS", NEW_MAX["NPC"], fname)
    text = bump_init_counter(text, "NUMOBJS", NEW_MAX["OBJ"], fname)
    text = bump_init_counter(text, "NUMEROHECHIZO", NEW_MAX["HEC"], fname)
    save(path, text)
    assert_crlf(path)


def process_profesiones(path):
    fname = os.path.basename(path)
    report.append(f"[{fname}]")
    text = load(path)

    def remap_field(m, mapping):
        old = int(m.group(2))
        if old in mapping:
            new = mapping[old]
            report.append(f"  {fname}: {m.group(1).strip()}{old} -> {new}")
            return f"{m.group(1)}{new}"
        return m.group(0)

    text = re.sub(r"(?im)^(NpcMaestroId\s*=\s*)(\d+)",
                  lambda m: remap_field(m, NPC_MAP), text)
    text = re.sub(r"(?im)^(ItemManualId\s*=\s*)(\d+)",
                  lambda m: remap_field(m, OBJ_MAP), text)
    text = re.sub(r"(?im)^(ItemPocionOlvidoId\s*=\s*)(\d+)",
                  lambda m: remap_field(m, OBJ_MAP), text)
    save(path, text)
    assert_crlf(path)


def main():
    dat = os.path.join(ROOT, r"dev\Recursos\Dat")
    process_dat(os.path.join(dat, "npcs.dat"), "NPC", NPC_MAP,
                "NumNPCs", NEW_MAX["NPC"], do_inv=True)
    process_dat(os.path.join(dat, "obj.dat"), "OBJ", OBJ_MAP,
                "NumOBJs", NEW_MAX["OBJ"], do_hec=True)
    process_dat(os.path.join(dat, "Hechizos.dat"), "HECHIZO", HEC_MAP,
                "NumeroHechizos", NEW_MAX["HEC"])

    init = os.path.join(ROOT, r"dev\Recursos\init")
    for lang in ("sp", "en", "pt", "fr", "it"):
        process_localindex(os.path.join(init, f"{lang}_localindex.dat"))

    process_profesiones(os.path.join(ROOT, r"dev\server\profesiones.ini"))

    print("\n".join(report))
    print(f"\nTotal cambios reportados: {len(report) - 0}")


if __name__ == "__main__":
    main()
