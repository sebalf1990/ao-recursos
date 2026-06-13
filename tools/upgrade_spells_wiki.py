# -*- coding: utf-8 -*-
"""Fase 3: upgrade de stubs de hechizos con la data completa de la API de la wiki
oficial (captura del usuario via DevTools, 2026-06-10).

Reemplaza los stubs cubiertos por getAllSpells.txt con secciones completas
(Tipo, MinHP/MaxHP, SubeHP, Target, WAV, FX, particulas, textos 5 idiomas).
Limitacion documentada: la API no expone flags de efecto (Invisibilidad/Paraliza/
RemoverParalisis/Estupidez) ni datos de invocacion (Invoca/NumNpc/Cant) ->
quedan pendientes de curaduria fina; el hechizo es casteable y el server lo
carga sin riesgo.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import OURS_DAT

WIKI = r"C:\Users\Seba\Downloads\ao20wiki\quest y otros\getAllSpells.txt"
OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
PROTECTED = set(range(400, 413))

# JSON key -> clave del parser del server (FileIO.bas:498-607) / cliente
KEYMAP = [
    ("NOMBRE", "Nombre"), ("DESC", "Desc"), ("PALABRASMAGICAS", "PalabrasMagicas"),
    ("HECHIZEROMSG", "HechizeroMsg"), ("TARGETMSG", "TargetMsg"), ("PROPIOMSG", "PropioMsg"),
    ("TIPO", "Tipo"), ("SUBEHP", "SubeHP"), ("MINHP", "MinHP"), ("MAXHP", "MaxHP"),
    ("TARGET", "Target"), ("TARGETEFFECTTYPE", "TargetEffectType"),
    ("MANAREQUERIDO", "ManaRequerido"), ("STAREQUERIDO", "StaRequerido"),
    ("MINSKILL", "MinSkill"), ("WAV", "WAV"), ("FXGRH", "Fxgrh"), ("LOOPS", "Loops"),
    ("PARTICLEVIAJE", "ParticleViaje"), ("ICONOINDEX", "IconoIndex"),
    ("ISBINDABLE", "IsBindable"),
]
LANG_KEYS = [("NOMBRE", "Nombre"), ("DESC", "Desc"),
             ("HECHIZEROMSG", "HechizeroMsg"), ("TARGETMSG", "TargetMsg")]

acts = json.load(open(os.path.join(OUT_DIR, "fase2_acciones.json"), encoding="utf-8"))
stub_ids = set(acts["HECHIZO"]["migrar_texto"]) - PROTECTED
spells = json.load(open(WIKI, encoding="utf-8", errors="replace"))
upgradable = {s["spell_id"]: s for s in spells if s.get("spell_id") in stub_ids}

path = os.path.join(OURS_DAT, "Hechizos.dat")
raw = open(path, "rb").read().decode("cp1252")


def build_section(n, s):
    lines = [f"[HECHIZO{n}] 'Data completa de la API wiki oficial 2026-06-10; "
             "flags de efecto/invocacion pendientes de curaduria si aplica"]
    for jk, dk in KEYMAP:
        v = s.get(jk)
        if v not in (None, ""):
            lines.append(f"{dk}={v}")
    for lang in ("EN", "PT", "FR", "IT"):
        for jk, dk in LANG_KEYS:
            v = s.get(f"{lang}_{jk}")
            if v not in (None, ""):
                lines.append(f"{lang.lower()}_{dk}={v}")
    return "\r\n".join(lines) + "\r\n"


replaced = []
for n, s in sorted(upgradable.items()):
    sec = build_section(n, s)
    pat = re.compile(r"^\[HECHIZO" + str(n) + r"\][^\r\n]*\r\n.*?(?=^\[|\Z)", re.S | re.M)
    if pat.search(raw):
        raw = pat.sub(lambda _: sec + "\r\n", raw, count=1)
        replaced.append(n)

open(path, "w", encoding="cp1252", newline="").write(raw)
b = open(path, "rb").read()
assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"

# sanity: nombres con acentos correctos
t = b.decode("cp1252")
m = re.search(r"\[HECHIZO50\][^\r\n]*\r\n(.*?)(?=\r\n\[)", t, re.S)
print(f"upgradeados con data completa: {len(replaced)} -> {replaced}")
print("muestra HECHIZO50:")
print(m.group(1)[:300] if m else "no encontrado")
