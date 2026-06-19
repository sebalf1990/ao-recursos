#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Plan 18.002 - Reconcilia VENDEDORES de NPCs.dat contra la API oficial (MERGE).

Vendedores (getAllSellersNpcs): empareja por id (73/75 nombres coinciden; 2 divergencias
de identidad se adoptan al oficial por decision del usuario). MERGE: pisa/inserta los campos
de la API (Name+idiomas, Desc+idiomas, DescClose, Body, Head, SoundOpen/Close, NpcType,
Comercia, TipoItems) y REEMPLAZA el inventario (NROITEMS+Objn). Preserva el resto.
Autorea el [BODYn] en cuerpos.dat si falta y su grh animado ya existe; si no hay grh
resoluble, NO cambia el body y lo loguea (sub-track de autoria de grh).
Maneja headers duplicados (opera sobre la seccion con Name= sin comentar). cp1252+CRLF.

Hostiles NO entran aca: sus ids no alinean con la API (matching por nombre + gate, aparte).

Uso: python reconcile_npcs_api.py --all [--dry]   |   --ids 689,1349 [--dry]
"""
import json, re, os, glob, argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RES = os.path.join(ROOT, "dev", "Recursos")
NPCDAT = os.path.join(RES, "Dat", "NPCs.dat")
CUERPOS = os.path.join(RES, "init", "cuerpos.dat")
GRAFINI = os.path.join(RES, "init", "graficos.ini")
APIDIR = os.path.join(ROOT, "dev", "oficial", "wiki-api")
NL = "\r\n"

SCAL = [("NAME", "Name"), ("EN_NAME", "en_Name"), ("PT_NAME", "PT_Name"), ("FR_NAME", "FR_Name"), ("IT_NAME", "IT_Name"),
        ("DESC", "Desc"), ("EN_DESC", "en_Desc"), ("PT_DESC", "PT_Desc"), ("FR_DESC", "FR_Desc"), ("IT_DESC", "IT_Desc"),
        ("DESCCLOSE", "DescClose"), ("BODY", "Body"), ("HEAD", "Head"), ("SOUNDOPEN", "SoundOpen"),
        ("SOUNDCLOSE", "SoundClose"), ("NPCTYPE", "NpcType"), ("COMERCIA", "Comercia"), ("TIPOITEMS", "TipoItems")]

_PUNCT = {0x2019: "'", 0x2018: "'", 0x0092: "'", 0x0091: "'", 0x201c: '"', 0x201d: '"',
          0x0093: '"', 0x0094: '"', 0x2013: "-", 0x2014: "-", 0x0096: "-", 0x0097: "-",
          0x2026: "...", 0x0085: "...", 0x00a0: " "}
_TR = {chr(k): v for k, v in _PUNCT.items()}


def clean(x):
    x = str(x)
    for k, v in _TR.items():
        x = x.replace(k, v)
    x.encode("cp1252")
    return x


def load_grh():
    grh = {}
    for ln in open(GRAFINI, encoding="cp1252"):
        if ln.startswith("Grh") and "=" in ln:
            k, v = ln.split("=", 1)
            grh[k[3:]] = v.split("'")[0].strip()
    static, afirst = {}, {}
    for n, v in grh.items():
        p = v.split("-")
        if p[0] == "1" and len(p) >= 6:
            static[(p[1], p[2], p[3], p[4], p[5])] = n
        elif p[0].isdigit() and int(p[0]) > 1:
            afirst.setdefault(p[1], []).append(n)
    return static, afirst


def resolve_grh(a, static, afirst):
    bd = a.get("bodyData") or {}
    sg = static.get((bd.get("fileName"), bd.get("initialPositionX"), bd.get("initialPositionY"),
                     bd.get("width"), bd.get("height")))
    ani = afirst.get(sg, []) if sg else []
    return (ani[0] if ani else None, bd.get("headOffsetX", "0"), bd.get("headOffsetY", "0"))


def find_section(s, nid):
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[NPC%d\].*?(?=\r\n\[NPC|\Z)" % nid, s, re.S)]
    if not spans:
        return None
    for st, en in spans:
        if re.search(r"\r\nName=", s[st:en]):
            return (st, en)
    return spans[0]


def setf(seg, key, val):
    rx = re.compile(r"\r\n" + re.escape(key) + r"=[^\r\n]*", re.I)
    if rx.search(seg):
        return rx.sub(lambda m: NL + key + "=" + val, seg, count=1)
    m = re.search(r"\r\nName=[^\r\n]*", seg, re.I)
    if m:
        return seg[:m.end()] + NL + key + "=" + val + seg[m.end():]
    i = seg.find(NL)
    return seg[:i] + NL + key + "=" + val + seg[i:]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    sellers = {int(n["id"]): n for n in json.load(open(os.path.join(APIDIR, "getAllSellersNpcs.json"), encoding="utf-8"))}
    static, afirst = load_grh()
    npc = open(NPCDAT, "rb").read().decode("cp1252")
    cu = open(CUERPOS, "rb").read().decode("cp1252")
    bodies = set(re.findall(r"\[BODY(\d+)\]", cu))
    ids = sorted(sellers) if a.all else [int(x) for x in a.ids.split(",") if x.strip()]
    applied = deferred = skipped = 0
    log = []
    for nid in ids:
        if nid not in sellers:
            skipped += 1; continue
        sec = find_section(npc, nid)
        if not sec:
            skipped += 1; log.append("NPC%d skip (no en NPCs.dat)" % nid); continue
        ai = sellers[nid]
        st, en = sec
        seg = npc[st:en]
        # body authoring si falta
        body = str(ai.get("BODY") or "")
        defer_body = False
        if body and body not in bodies:
            ag, hx, hy = resolve_grh(ai, static, afirst)
            if ag:
                block = ("[BODY%s]" % body + NL + "".join("Walk%d=%s ' d" % (i, ag) + NL for i in range(1, 5))
                         + "HeadOffsetX=%s" % hx + NL + "HeadOffsetY=%s" % hy + NL + "AnimateOnIdle=1" + NL + NL)
                if not a.dry:
                    cu = cu.replace("[BODY6001]" + NL, block + "[BODY6001]" + NL, 1)
                bodies.add(body)
                log.append("NPC%d body NEW %s(grh%s)" % (nid, body, ag))
            else:
                defer_body = True
                deferred += 1
                log.append("NPC%d body %s SIN grh -> diferido" % (nid, body))
        # merge escalares
        for ak, dk in SCAL:
            v = ai.get(ak)
            if v is None or str(v) == "":
                continue
            if dk == "Body" and defer_body:
                continue
            seg = setf(seg, dk, clean(v))
        # inventario
        seg = re.sub(r"\r\nNROITEMS=[^\r\n]*", "", seg, flags=re.I)
        seg = re.sub(r"\r\nObj\d+=[^\r\n]*", "", seg, flags=re.I)
        objs = []
        i = 1
        while ai.get("OBJ%d" % i):
            v = ai["OBJ%d" % i]
            if isinstance(v, str) and "-" in v:
                objs.append(v)
            i += 1
        nro = str(ai.get("NROITEMS") or len(objs))
        inv = NL + "NROITEMS=" + nro + "".join(NL + "Obj%d=%s" % (j + 1, ov) for j, ov in enumerate(objs))
        if re.search(r"\r\nComercia=[^\r\n]*", seg):
            seg = re.sub(r"(\r\nComercia=[^\r\n]*)", lambda m: m.group(1) + inv, seg, count=1)
        else:
            seg = seg + inv
        npc = npc[:st] + seg + npc[en:]
        applied += 1
    if not a.dry:
        npc.encode("cp1252"); cu.encode("cp1252")
        open(NPCDAT, "w", encoding="cp1252", newline="").write(npc)
        open(CUERPOS, "w", encoding="cp1252", newline="").write(cu)
        for f in (NPCDAT, CUERPOS):
            b = open(f, "rb").read()
            assert b.count(b"\n") == b.count(b"\r\n") and b.count(b"\r\r\n") == 0, "CRLF roto " + f
    print("\n".join(log[:50]))
    if len(log) > 50:
        print("... (%d mas)" % (len(log) - 50))
    print("aplicados=%d body_diferidos=%d skip=%d %s" % (applied, deferred, skipped, "(dry)" if a.dry else "ESCRITO"))


if __name__ == "__main__":
    main()
