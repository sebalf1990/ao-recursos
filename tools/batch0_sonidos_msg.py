# -*- coding: utf-8 -*-
"""Fase 3 batch 0: sonidos OGG nuevos + mensajes faltantes (plan 10.001).

- Copia los OGG de la ley fresca que no tenemos (solo adiciones, no pisa nada).
- Agrega los Msg faltantes a los 5 *_localmsg.dat (cp1252 + CRLF) y ajusta el contador.
"""
import os
import re
import shutil

ROOT = r"c:\AO20"
LEY = os.path.join(ROOT, r"dev\oficial\recursos_20260610")
OURS_INIT = os.path.join(ROOT, r"dev\Recursos\init")

# --- OGG ---
ley_ogg = os.path.join(LEY, "OGG")
our_ogg = os.path.join(ROOT, r"dev\Recursos\OGG")
ours_files = {f.lower() for f in os.listdir(our_ogg)}
ours_files |= {f.lower() for f in os.listdir(os.path.join(ROOT, r"dev\Recursos\SoundsOgg"))}
copied = 0
for f in sorted(os.listdir(ley_ogg)):
    if f.lower() not in ours_files:
        shutil.copy2(os.path.join(ley_ogg, f), os.path.join(our_ogg, f))
        copied += 1
print(f"OGG copiados: {copied}")

# --- Mensajes ---
LANGS = [("sp", "SP"), ("en", "EN"), ("pt", "PT"), ("fr", "FR"), ("it", "IT")]


def find_file(folder, name):
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


for lang, up in LANGS:
    ley_path = find_file(os.path.join(LEY, "init"), f"{lang}_localmsg.dat")
    our_path = find_file(OURS_INIT, f"{lang}_localmsg.dat")
    if not ley_path or not our_path:
        print(f"{lang}: archivo no encontrado (ley={bool(ley_path)} nuestro={bool(our_path)})")
        continue
    ley_t = open(ley_path, "rb").read().decode("cp1252")
    raw = open(our_path, "rb").read().decode("cp1252")
    ley_msgs = dict(re.findall(r"(?im)^(Msg\d+)\s*=\s*([^\r\n]*)", ley_t))
    our_msgs = dict(re.findall(r"(?im)^(Msg\d+)\s*=\s*([^\r\n]*)", raw))
    missing = sorted(set(ley_msgs) - set(our_msgs), key=lambda k: int(k[3:]))
    if missing:
        block = "".join(f"{k}={ley_msgs[k]}\r\n" for k in missing)
        # insertar al final del archivo (la seccion de msgs es la ultima)
        if not raw.endswith("\r\n"):
            raw += "\r\n"
        raw += block
    # contador
    max_id = max(int(k[3:]) for k in set(ley_msgs) | set(our_msgs))
    raw = re.sub(r"(?im)^(NumLocale" + up + r"_Msg\s*=\s*)(\d+)",
                 lambda m: f"{m.group(1)}{max(int(m.group(2)), max_id)}", raw, count=1)
    open(our_path, "w", encoding="cp1252", newline="").write(raw)
    b = open(our_path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), f"{lang}: CRLF roto"
    print(f"{lang}_localmsg: +{len(missing)} mensajes, contador>={max_id}, CRLF OK")
