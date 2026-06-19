#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Plan 18.002 - Reconcilia DATOS de items de obj.dat contra la API oficial de AO (MERGE).

Politica "todo al oficial" = igualar los ATRIBUTOS OFICIALES (icono, ropaje, def/dano,
valor, nivel, skill, clases permitidas, textos). PRESERVA los campos propios de AO20 que
la API no expone (peso, NFT, subastable, Donador, Crafteable/Materiales, RazaX,
intirable/Instransferible, DosManos, NumRopaje, pieles de crafteo, etc.).

- MERGE, no rewrite: solo pisa/inserta los campos de la API; el resto queda intacto.
- Clases: reemplaza el bloque CPn con ClasesPermitidas SOLO si la API lo trae no-vacio.
- Solo toca items que EXISTEN en la API (los propios-puros no se tocan).
- Maneja headers duplicados: opera sobre la seccion con contenido real (Name= sin comentar).
- Textos se PULLEAN de la API y se sanitizan a cp1252. cp1252 + CRLF preservados.

Uso:
  python reconcile_objs_api.py --all            # todos los items en API
  python reconcile_objs_api.py --ids 169,4332   # solo esos
  agregar --dry para solo reportar.
"""
import json, re, os, glob, argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OBJDAT = os.path.join(ROOT, "dev", "Recursos", "Dat", "obj.dat")
APIDIR = os.path.join(ROOT, "dev", "oficial", "wiki-api")
NL = "\r\n"

KEYMAP = {
    "NAME": "Name", "TEXTO": "Texto", "GRHINDEX": "GrhIndex", "OBJTYPE": "ObjType",
    "VALOR": "Valor", "CRUCIAL": "Crucial", "MAXDEF": "MaxDef", "MINDEF": "MinDef",
    "MAXHIT": "MaxHit", "MINHIT": "MinHit", "MINELV": "MinELV", "MAXLEV": "MaxLev",
    "SKHERRERIA": "SkHerreria", "SKCARPINTERIA": "SkCarpinteria", "SKSASTRERIA": "SkSastreria",
    "SKPOCIONES": "SkPociones", "LINGH": "LingH", "LINGP": "LingP", "LINGO": "LingO",
    "MADERA": "Madera", "MADERAELFICA": "MaderaElfica", "ANIM": "Anim", "WEAPONTYPE": "WeaponType",
    "MAXMODIFICADOR": "MaxModificador", "MINMODIFICADOR": "MinModificador", "TIPOPOCION": "TipoPocion",
    "SUBTIPO": "SubTipo", "PORCENTAJE": "Porcentaje", "PROYECTIL": "Proyectil", "MUNICIONES": "Municiones",
    "HECHIZO": "Hechizo", "MAXHITTONPC": "MaxHitToNpc", "MINHITTONPC": "MinHitToNpc",
    "ROPAJEELFA": "RopajeElfa", "ROPAJEELFAOSCURA": "RopajeElfaOscura", "ROPAJEELFO": "RopajeElfo",
    "ROPAJEELFOOSCURO": "RopajeElfoOscuro", "ROPAJEENANA": "RopajeEnana", "ROPAJEENANO": "RopajeEnano",
    "ROPAJEGNOMA": "RopajeGnoma", "ROPAJEGNOMO": "RopajeGnomo", "ROPAJEHUMANA": "RopajeHumana",
    "ROPAJEHUMANO": "RopajeHumano", "ROPAJEORCA": "RopajeOrca", "ROPAJEORCO": "RopajeOrco",
    "EN_NAME": "en_Name", "EN_TEXTO": "en_texto", "PT_NAME": "PT_Name", "PT_TEXTO": "PT_texto",
    "FR_NAME": "FR_Name", "FR_TEXTO": "FR_texto", "IT_NAME": "IT_Name", "IT_TEXTO": "IT_texto",
}
SKIP = {"ITEM_ID", "ID", "CANVASIMAGE", "SPELLSNAMES", "CLASESPERMITIDAS", "NOWIKI"}

# puntuacion Unicode -> ASCII (fuente ASCII pura via code points)
_PUNCT = {
    0x2019: "'", 0x2018: "'", 0x0092: "'", 0x0091: "'",
    0x201c: '"', 0x201d: '"', 0x0093: '"', 0x0094: '"',
    0x2013: "-", 0x2014: "-", 0x0096: "-", 0x0097: "-",
    0x2026: "...", 0x0085: "...", 0x00a0: " ",
}
_TR = {chr(k): v for k, v in _PUNCT.items()}


def clean(x):
    x = str(x)
    for k, v in _TR.items():
        x = x.replace(k, v)
    x.encode("cp1252")  # ruidoso si queda algo no representable
    return x


def load_api():
    items = {}
    for f in glob.glob(os.path.join(APIDIR, "getAll*.json")):
        fn = os.path.basename(f)
        if any(x in fn for x in ("Npcs", "Sellers", "Quest", "Spells", "Magic", "Patreon")):
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
            arr = d if isinstance(d, list) else list(d.values())[0]
            for n in arr:
                iid = n.get("item_id") or n.get("id")
                if iid is not None and str(iid).isdigit():
                    items[int(iid)] = n.get("Data", n)
        except Exception as e:
            print("WARN", fn, e)
    return items


def find_section(s, oid):
    """(start, end) de la seccion [OBJoid] con contenido real (Name= sin comentar)."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[OBJ%d\].*?(?=\r\n\[OBJ|\Z)" % oid, s, re.S)]
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


def merge_section(seg, D):
    changed = []
    for k, v in D.items():
        ku = k.upper()
        if ku in SKIP or isinstance(v, (list, dict)) or str(v).startswith("data:") or ku.endswith("GRAPHICDATA"):
            continue
        dk = KEYMAP.get(ku, k)
        before = seg
        seg = setf(seg, dk, clean(v))
        if before != seg:
            changed.append(dk)
    cps = D.get("ClasesPermitidas") or []
    if cps:
        had = re.search(r"\r\nCP\d+=", seg, re.I)
        seg = re.sub(r"\r\nCP\d+=[^\r\n]*", "", seg, flags=re.I)
        seg = seg + "".join(NL + "CP%d=%s" % (i + 1, clean(c)) for i, c in enumerate(cps))
        if had:
            changed.append("CPn")
    return seg, changed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    api = load_api()
    s = open(OBJDAT, "rb").read().decode("cp1252")
    ids = sorted(api.keys()) if a.all else [int(x) for x in a.ids.split(",") if x.strip()]
    applied = skipped = 0
    log = []
    for oid in ids:
        if oid not in api:
            skipped += 1; log.append("OBJ%d skip (no en API)" % oid); continue
        sec = find_section(s, oid)
        if not sec:
            skipped += 1; log.append("OBJ%d skip (no en obj.dat)" % oid); continue
        st, en = sec
        new, changed = merge_section(s[st:en], api[oid])
        if not a.dry:
            s = s[:st] + new + s[en:]
        applied += 1
        if changed:
            log.append("OBJ%d <- %s" % (oid, ",".join(changed)))
    if not a.dry:
        s.encode("cp1252")
        open(OBJDAT, "w", encoding="cp1252", newline="").write(s)
        b = open(OBJDAT, "rb").read()
        assert b.count(b"\n") == b.count(b"\r\n") and b.count(b"\r\r\n") == 0, "CRLF roto"
    print("\n".join(log[:50]))
    if len(log) > 50:
        print("... (%d mas)" % (len(log) - 50))
    print("aplicados=%d skip=%d %s" % (applied, skipped, "(dry)" if a.dry else "ESCRITO"))


if __name__ == "__main__":
    main()
