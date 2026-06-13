# -*- coding: utf-8 -*-
"""Fase 3 batch OBJs (plan 10.001).

1. MIGRAR 56: reemplaza las secciones comentadas (lista limpieza == migrar) por la
   logica completa del repo oficial (transcode a cp1252).
2. CORREGIR 665 texto + 71 balance (decision usuario: convergencia total a oficial):
   - con seccion en repo -> reemplazo completo desde repo.
   - sin seccion en repo (IDs > corte del repo capado) -> patch de campos base
     diferentes desde la ley (localindex), preservando la logica server propia.
3. MIGRAR_TEXTO 1100: stubs desde la ley (sp_localindex + localindex), enriquecidos
   con los campos server de la wiki API oficial donde hay item_id coincidente.
4. Protege 9000-9013 (reubicados 10.003) y no toca 6281-6291 (REVISAR).

Preserva los banners decorativos ('**** SECCION ****) entre secciones.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import detect_decode, parse_sections, LEY_INIT, REPO_DAT, OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
WIKI_DIR = r"c:\AO20\dev\oficial\wiki-api"
PROTECTED = set(range(9000, 9014))
REVISAR = set(range(6281, 6292))
TEXT_KEYS = ("name", "nombre", "desc", "descfinal", "texto")
WIKI_SKIP = {"canvasimage", "item_id"}
LANG_PREF = ("en_", "pt_", "fr_", "it_")

# Casing canonico (de la whitelist de generar_localindex + claves server frecuentes).
# Sin esto, un stub que mezcla 'Name' (ley sp) con 'EN_NAME' (ley big) produce dos
# claves distintas en el indice por idioma y el cliente lee la linea equivocada.
CANON_BASE = {k.lower(): k for k in (
    "Name", "GrhIndex", "ObjType", "Agarrable", "Texto", "Llave", "Valor", "MaxDef",
    "MinDef", "MinHit", "MaxHit", "CD", "CDType", "CreaGRH", "Destruye", "Hechizo",
    "Info", "Madera", "MaderaElfica", "Municiones", "Proyectil", "Raices",
    "SKHerreria", "SKPociones", "SKSastreria", "SKCarpinteria", "LingH", "LingO",
    "LingP", "RopajeElfa", "RopajeElfaOscura", "RopajeElfo", "RopajeElfoOscuro",
    "RopajeEnana", "RopajeEnano", "RopajeGnoma", "RopajeGnomo", "RopajeHumana",
    "RopajeHumano", "RopajeOrca", "RopajeOrco", "Anim", "WeaponType", "Subtipo",
    "SubTipo", "Crucial", "MinELV", "MaxLEV", "MinHam", "MinSed", "MinHP", "MaxHP",
    "StaffPower", "MagicDamageBonus", "NumRopaje", "Desc",
)}

actions = json.load(open(os.path.join(OUT_DIR, "fase2_acciones.json"), encoding="utf-8"))["OBJ"]
migrar_ids = set(actions["migrar"]) - PROTECTED
fix_ids = (set(actions["corregir_texto"]) | set(actions["corregir_balance"])) - PROTECTED
stub_ids = sorted(set(actions["migrar_texto"]) - PROTECTED)

path = os.path.join(OURS_DAT, "obj.dat")
ours_raw = open(path, "rb").read().decode("cp1252")
repo_raw = detect_decode(os.path.join(REPO_DAT, "obj.dat")).replace("\r\n", "\n")
ley_sp_raw = open(os.path.join(LEY_INIT, "sp_localindex.dat"), "rb").read().decode("cp1252").replace("\r\n", "\n")
ley_big_raw = open(os.path.join(LEY_INIT, "localindex.dat"), "rb").read().decode("cp1252").replace("\r\n", "\n")

HEADER_RE = re.compile(r"^\s*('*)\s*\[OBJ(\d+)\]", re.IGNORECASE)


# ---------- fuentes ----------
def ley_section_fields(raw, n):
    """[(clave_casing_original, valor)] de [OBJn] en un localindex de la ley."""
    m = re.search(r"^\[OBJ" + str(n) + r"\][^\n]*\n(.*?)(?=^\[|\Z)", raw, re.S | re.M)
    if not m:
        return []
    out = []
    for ln in m.group(1).split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith("'") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        if k.strip():
            out.append((k.strip(), v.strip()))
    return out


def repo_section(n):
    """Lineas de la seccion [OBJn] del repo, sin cola decorativa, casing original.

    Devuelve None si la seccion no existe O no tiene campos reales (slots
    '[OBJn]'Libre del repo capado: la ley es la fuente valida en esos casos,
    igual que hizo el diff de fase 2 con su `repo.get(n) or ley_fields`).
    """
    m = re.search(r"^\[OBJ" + str(n) + r"\][^\n]*(?:\n.*?)?(?=^\s*'?\s*\[|\Z)",
                  repo_raw, re.S | re.M)
    if not m:
        return None
    lines = m.group(0).split("\n")
    while lines and (lines[-1].strip() == "" or
                     (lines[-1].lstrip().startswith("'") and "=" not in lines[-1])):
        lines.pop()
    fields = [l for l in lines[1:] if "=" in l and not l.lstrip().startswith("'")]
    return lines if fields else None


def load_wiki_items():
    """item_id -> campos escalares de Data, mergeando todos los datasets del HAR."""
    items = {}
    for fn in sorted(os.listdir(WIKI_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(WIKI_DIR, fn), encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(data, list):
            seq = data
        elif isinstance(data, dict):
            seq = list(data.values())
        else:
            continue
        for it in seq:
            if not (isinstance(it, dict) and "item_id" in it and isinstance(it.get("Data"), dict)):
                continue
            tgt = items.setdefault(int(it["item_id"]), {})
            for k, v in it["Data"].items():
                if not isinstance(v, (str, int, float)) or k.lower() in WIKI_SKIP:
                    continue
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                    continue
                v = str(v).replace("\r", " ").replace("\n", " ").strip()
                if v and k.lower() not in {x.lower() for x in tgt}:
                    tgt[k] = v
    return items


WIKI = load_wiki_items()
unmappable = 0


def to_cp1252(line):
    global unmappable
    try:
        line.encode("cp1252")
        return line
    except UnicodeEncodeError:
        unmappable += 1
        return line.encode("cp1252", errors="replace").decode("cp1252")


# ---------- parseo en bloques ----------
def split_blocks(text):
    """[(id|None, commented, [lineas])] — id None = preambulo/INIT/no-OBJ."""
    lines = text.split("\r\n")
    blocks, cur, cur_id, cur_comm = [], [], None, False
    for ln in lines:
        m = HEADER_RE.match(ln)
        if m:
            blocks.append((cur_id, cur_comm, cur))
            cur, cur_id, cur_comm = [ln], int(m.group(2)), bool(m.group(1))
        else:
            cur.append(ln)
    blocks.append((cur_id, cur_comm, cur))
    return blocks


def split_decoration(lines):
    """Separa la cola decorativa (blanks + banners sin '=') del contenido."""
    i = len(lines)
    while i > 0:
        s = lines[i - 1].strip()
        if s == "":
            i -= 1
            continue
        if (s.startswith("'") and "=" not in s and len(s.strip("'- *")) > 3
                and not HEADER_RE.match(s)):
            i -= 1
            continue
        break
    return lines[:i], lines[i:]


def norm_val(k, v):
    """Normaliza valor como fase 2: sin comentario inline (salvo claves de texto)."""
    if "'" in v and k not in TEXT_KEYS:
        v = v.split("'", 1)[0]
    return re.sub(r"\s+", " ", v.strip().lower())


def ley_objtype(n):
    for raw in (ley_sp_raw, ley_big_raw):
        for k, v in ley_section_fields(raw, n):
            if k.lower() == "objtype" and v.strip():
                return v.split("'")[0].strip()
    return None


def ours_objtype(lines):
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("objtype") and "=" in s and not s.startswith("'"):
            return s.split("=", 1)[1].split("'")[0].strip()
    return None


def patch_from_ley(n, lines):
    """Alinea a la ley los campos base que difieren; agrega los que faltan."""
    ley = {}
    for k, v in ley_section_fields(ley_big_raw, n) + ley_section_fields(ley_sp_raw, n):
        if not k.lower().startswith(LANG_PREF) and v != "":
            ley[k.lower()] = (k, v)  # sp pisa a big
    content, deco = split_decoration(lines)
    present, changed = set(), 0
    for i, ln in enumerate(content):
        s = ln.strip()
        if not s or s.startswith("'") or "=" not in s or HEADER_RE.match(s):
            continue
        k, _, v = ln.partition("=")
        kl = k.strip().lower()
        present.add(kl)
        if kl in ley and norm_val(kl, ley[kl][1]) != norm_val(kl, v):
            content[i] = to_cp1252(f"{k.strip()}={ley[kl][1]}")
            changed += 1
    add = [to_cp1252(f"{k}={v}") for kl, (k, v) in sorted(ley.items()) if kl not in present]
    if add:
        j = len(content)
        while j > 0 and content[j - 1].strip() == "":
            j -= 1
        content[j:j] = add
        changed += len(add)
    return content + deco, changed


def build_stub(n):
    fields, seen = [], set()
    for k, v in ley_section_fields(ley_sp_raw, n) + ley_section_fields(ley_big_raw, n):
        if v != "" and k.lower() not in seen:
            seen.add(k.lower())
            fields.append((k, v))
    wiki_added = 0
    for k, v in WIKI.get(n, {}).items():
        if k.lower() not in seen:
            seen.add(k.lower())
            fields.append((k, v))
            wiki_added += 1
    # casing canonico: primero claves base, despues idiomas alineados a la base
    base_casing = {}
    canon_fields = []
    for k, v in fields:
        kl = k.lower()
        if not kl.startswith(LANG_PREF):
            k = CANON_BASE.get(kl, k)
            base_casing[kl] = k
            canon_fields.append((k, v))
    for k, v in fields:
        kl = k.lower()
        if kl.startswith(LANG_PREF):
            base = k[3:]
            canon = base_casing.get(base.lower()) or CANON_BASE.get(base.lower(), base)
            canon_fields.append((kl[:3] + canon, v))
    fields = canon_fields
    tag = (" + wiki API oficial" if wiki_added
           else "; logica server pendiente (repo capado)")
    lines = [f"[OBJ{n}] 'Reconstruido de localindex oficial 2026-06-08{tag}"]
    lines += [to_cp1252(f"{k}={v}") for k, v in fields]
    lines.append("")
    return lines, wiki_added


# ---------- ejecucion ----------
def content_only(lines):
    """Contenido sin cola de blanks/comentarios: solo para comparar bloques
    activos pre/post (el banner anexado al EOF lleva '=' y split_decoration
    no lo reconoceria como decoracion)."""
    i = len(lines)
    while i > 0 and (lines[i - 1].strip() == "" or lines[i - 1].lstrip().startswith("'")):
        i -= 1
    return "\r\n".join(lines[:i])


def main():
    global unmappable
    blocks = split_blocks(ours_raw)
    pre_state = {bid: content_only(ls) for bid, _, ls in blocks
                 if bid in PROTECTED | REVISAR}

    n_migrar = n_fix_repo = n_fix_ley = patched_fields = n_reconv = 0
    missing, reconv_ids = [], []
    out_blocks = []
    for bid, commented, lines in blocks:
        if bid is None or bid in PROTECTED or bid in REVISAR:
            out_blocks.append(lines)
            continue
        if commented and bid in migrar_ids:
            sec = repo_section(bid)
            _, deco = split_decoration(lines)
            if sec is None:
                # repo sin logica real para este id -> cascara desde la ley
                stub, _ = build_stub(bid)
                out_blocks.append(stub + deco)
                missing.append(("migrar->stub_ley", bid))
            else:
                out_blocks.append([to_cp1252(l) for l in sec] + [""] + deco)
            n_migrar += 1
        elif not commented and bid in fix_ids:
            sec = repo_section(bid)
            if sec is not None:
                _, deco = split_decoration(lines)
                out_blocks.append([to_cp1252(l) for l in sec] + [""] + deco)
                n_fix_repo += 1
            else:
                ot_ley, ot_ours = ley_objtype(bid), ours_objtype(lines)
                if ot_ley and ot_ours and ot_ley != ot_ours:
                    # el oficial repropuso el slot (cambio de naturaleza):
                    # reconstruccion completa desde la ley, sin claves viejas
                    stub, _ = build_stub(bid)
                    _, deco = split_decoration(lines)
                    out_blocks.append(stub + deco)
                    n_reconv += 1
                    reconv_ids.append(bid)
                else:
                    new_lines, ch = patch_from_ley(bid, lines)
                    out_blocks.append(new_lines)
                    n_fix_ley += 1
                    patched_fields += ch
        else:
            out_blocks.append(lines)

    result = "\r\n".join("\r\n".join(b) for b in out_blocks)

    banner = ("\r\n' =====================================================================\r\n"
              "' OBJs reconstruidos del localindex oficial (Steam 2026-06-08) y de la\r\n"
              "' wiki API oficial donde hubo item_id coincidente. El repo publico de\r\n"
              "' ao-org no incluye su logica server (capado): los stubs sin wiki solo\r\n"
              "' traen los campos cliente del localindex.\r\n"
              "' Plan 10.001 Fase 3, batch OBJs.\r\n"
              "' =====================================================================\r\n\r\n")
    stub_lines, n_wiki = [], 0
    for n in stub_ids:
        ls, w = build_stub(n)
        stub_lines.extend(ls)
        n_wiki += 1 if w else 0
    result = result.rstrip("\r\n") + "\r\n" + banner + "\r\n".join(stub_lines) + "\r\n"

    open(path, "w", encoding="cp1252", newline="").write(result)

    # ---------- validaciones ----------
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"

    final = parse_sections(path, ("OBJ",))["OBJ"]
    active = {k for k, s in final.items() if not s["commented"]}
    commented_left = {k for k, s in final.items() if s["commented"]}

    post_text = open(path, "rb").read().decode("cp1252")
    hdrs = [int(n) for q, n in re.findall(r"(?m)^('*)\s*\[OBJ(\d+)\]", post_text) if not q]
    dups = sorted({n for n in hdrs if hdrs.count(n) > 1})

    post_state = {bid: content_only(ls) for bid, _, ls in split_blocks(post_text)
                  if bid in PROTECTED | REVISAR}
    intactos = all(pre_state[k] == post_state.get(k) for k in pre_state)

    print(f"migrar desde repo (eran comentadas): {n_migrar} (faltantes: {missing})")
    print(f"corregir reemplazo repo: {n_fix_repo} | corregir patch ley: {n_fix_ley} "
          f"(campos tocados: {patched_fields})")
    print(f"reconvertidos desde ley (ObjType cambio, slot repropuesto): {n_reconv} "
          f"-> {reconv_ids}")
    print(f"stubs creados: {len(stub_ids)} (enriquecidos con wiki: {n_wiki})")
    print(f"caracteres no representables en cp1252 (reemplazados): {unmappable}")
    print(f"secciones activas: {len(active)} (esperado 5518) | comentadas restantes: "
          f"{len(commented_left)} -> {sorted(commented_left)[:10]}")
    print(f"headers duplicados: {dups if dups else 'ninguno'}")
    print(f"protegidos 9000-9013 y revisar 6281-6291 intactos (contenido): {intactos}")
    for n, key, want in ((668, "name", "Harbinger Kin"), (6336, "name", "Escudo del Bosque"),
                         (1100, "mindef", "35"), (9000, "name", "Manual de Carpinteria")):
        got = final.get(n, {}).get("fields", {}).get(key, "?")
        print(f"  OBJ{n}.{key} = {got!r} (esperado {want!r}) {'OK' if got == want else 'MAL'}")


if __name__ == "__main__":
    main()
