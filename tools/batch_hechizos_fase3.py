# -*- coding: utf-8 -*-
"""Fase 3 batch HECHIZOS (plan 10.001).

1. Alinea a oficial las secciones que difieren (texto + balance; decision del
   usuario 2026-06-10: convergencia total) tomandolas del repo (transcode cp1252).
2. Crea stubs para los hechizos que la ley conoce y nosotros no (repo capado:
   sin logica server publica). Campos del localindex oficial; combate queda en 0
   hasta que se publique/disenie la logica. Marcados con comentario.
3. Protege 400-412 (venenos reubicados): NUNCA se tocan.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import parse_sections, detect_decode, LEY_INIT, REPO_DAT, OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
PROTECTED = set(range(400, 413))

KEY_CANON = {
    "nombre": "Nombre", "desc": "Desc", "texto": "Texto", "grhindex": "GrhIndex",
    "manarequerido": "ManaRequerido", "hechizotipo": "HechizoTipo",
    "minskill": "MinSkill", "maxskill": "MaxSkill", "hechizeromsg": "HechizeroMsg",
    "cooldown": "Cooldown", "iconoindex": "IconoIndex",
    "palabrasmagicas": "PalabrasMagicas", "propiomsg": "PropioMsg",
    "starequerido": "StaRequerido", "targetmsg": "TargetMsg",
}
LANGS = ("en", "pt", "fr", "it")

actions = json.load(open(os.path.join(OUT_DIR, "fase2_acciones.json"), encoding="utf-8"))
align_ids = sorted((set(actions["HECHIZO"]["corregir_texto"])
                    | set(actions["HECHIZO"]["corregir_balance"])) - PROTECTED)
stub_ids = sorted(set(actions["HECHIZO"]["migrar_texto"]) - PROTECTED)

path = os.path.join(OURS_DAT, "Hechizos.dat")
ours_raw = open(path, "rb").read().decode("cp1252")
repo_raw = detect_decode(os.path.join(REPO_DAT, "Hechizos.dat")).replace("\r\n", "\n")

ley_big = parse_sections(os.path.join(LEY_INIT, "localindex.dat"), ("HECHIZO",))["HECHIZO"]
ley_sp = parse_sections(os.path.join(LEY_INIT, "sp_localindex.dat"), ("HECHIZO",))["HECHIZO"]


def repo_section(n):
    """Texto completo de la seccion [HECHIZOn] del repo, normalizado a CRLF."""
    m = re.search(r"^\[HECHIZO" + str(n) + r"\][^\n]*\n(.*?)(?=^\[|\Z)",
                  repo_raw, re.S | re.M)
    if not m:
        return None
    body = m.group(0).rstrip("\n")
    return body.replace("\n", "\r\n") + "\r\n"


def build_stub(n):
    fields = {}
    for src in (ley_big.get(n, {}).get("fields", {}), ley_sp.get(n, {}).get("fields", {})):
        for k, v in src.items():
            if v != "" and k not in fields:
                fields[k] = v
    lines = [f"[HECHIZO{n}] 'Reconstruido de localindex oficial 2026-06-10; logica server pendiente (repo capado)"]
    for low, canon in KEY_CANON.items():
        if low in fields:
            lines.append(f"{canon}={fields[low]}")
    for lang in LANGS:
        for low, canon in (("name", "Nombre"), ("desc", "Desc"),
                           ("hechizeromsg", "HechizeroMsg"), ("propiomsg", "PropioMsg"),
                           ("targetmsg", "TargetMsg")):
            v = fields.get(f"{lang}_{low}")
            if v:
                lines.append(f"{lang}_{canon}={v}")
    return "\r\n".join(lines) + "\r\n"


# 1) alinear secciones existentes
replaced, missing_repo = [], []
for n in align_ids:
    sec = repo_section(n)
    if sec is None:
        missing_repo.append(n)
        continue
    pat = re.compile(r"^\[HECHIZO" + str(n) + r"\][^\r\n]*\r\n.*?(?=^\[|\Z)", re.S | re.M)
    if pat.search(ours_raw):
        ours_raw = pat.sub(lambda _: sec + "\r\n", ours_raw, count=1)
        replaced.append(n)

# 2) stubs nuevos al final, con banner
stubs = [build_stub(n) for n in stub_ids]
banner = ("\r\n' =====================================================================\r\n"
          "' Hechizos reconstruidos del localindex oficial (Steam 2026-06-08).\r\n"
          "' El repo publico de ao-org no incluye su logica server (capado).\r\n"
          "' Campos de combate ausentes => el hechizo no hace efecto hasta completar.\r\n"
          "' Plan 10.001 Fase 3, batch hechizos.\r\n"
          "' =====================================================================\r\n")
ours_raw = ours_raw.rstrip("\r\n") + "\r\n" + banner + "\r\n".join(stubs)

open(path, "w", encoding="cp1252", newline="").write(ours_raw)
b = open(path, "rb").read()
assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"

# validaciones
final = parse_sections(path, ("HECHIZO",))["HECHIZO"]
prot_ok = all(n in final for n in PROTECTED)
print(f"alineados desde repo: {len(replaced)} (sin seccion en repo: {missing_repo})")
print(f"stubs creados: {len(stubs)}")
print(f"secciones totales ahora: {len(final)} (antes ~160)")
print(f"protegidos 400-412 intactos: {prot_ok}")
nombre_400 = final.get(400, {}).get("fields", {}).get("nombre", "?")
print(f"HECHIZO400 sigue siendo: {nombre_400}")
