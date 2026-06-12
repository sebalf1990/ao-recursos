# -*- coding: utf-8 -*-
"""Fase 3 — pasada punto ciego OBJ (plan 10.001).

El repo publico esta desactualizado tambien para OBJs: fase 2 uso `ref = repo or
ley` y ~1280 ids con repo==nuestro quedaron sin marcar aunque la LEY cambio.
Bloqueante para el batch QUESTS (las quests oficiales referencian el layout nuevo).

1. RENAMES (~1150, mismo item con nombre nuevo): realineacion campo a campo a la
   ley en el mismo id (guard visual: Ropaje*/GrhIndex contra registros locales).
2. IDENTIDAD DISTINTA: el slot se reconstruye desde la ley (+wiki items).
   - si el item viejo existe en otro id de la ley -> las referencias nuestras
     (Quests Required/RewardObj, NPC ObjN/QuizaDropea) se re-mapean ahi.
   - si no existe y esta referenciado o es custom valioso -> se reubica a 9039+.
   - si no existe y nadie lo referencia -> se pisa (recuperable de git/backup).
3. Vendedores: se re-corre la alineacion (los omitidos por identidad se recuperan).

Similitud rename-vs-identidad: acentos plegados + prefijos de token >=5 chars
(Almofar/Almófar, Tijera/Tijeras, Mimetizar/Mimetismo son renames).
"""
import json
import os
import re
import struct
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_objs_fase3 as B  # build/CANON/WIKI reutilizables (modulo con guard __main__)
from diff_fase2 import OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
INIT_DIR = r"c:\AO20\dev\Recursos\init"
PROTECTED = set(range(9000, 9039))
RELOC_BASE = 9039
KEEP_ALWAYS = {3746, 3748, 3256}  # camisetas Mundial + Gran Campeon AO20 (customs del usuario)
STOP = {"de", "del", "la", "el", "los", "las", "y", "con"}
VIS_BODY = re.compile(r"^(Ropaje\w+|RAZAALTOS|RAZABAJOS|NumRopaje)$", re.I)
VIS_GRH = re.compile(r"^GrhIndex$", re.I)
TEXT_KEYS = ("name", "texto", "desc")
LANG_PREF = ("en_", "pt_", "fr_", "it_")


def fold(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s):
    return re.sub(r"\s+", " ", fold(s).strip().lower())


def same_item(a, b):
    ta = {t for t in re.findall(r"\w{4,}", norm(a)) if t not in STOP}
    tb = {t for t in re.findall(r"\w{4,}", norm(b)) if t not in STOP}
    if ta & tb:
        return True
    return any(x[:5] == y[:5] for x in ta for y in tb if len(x) >= 5 and len(y) >= 5)


def clean_val(v):
    v = v.strip()
    while v.lower().startswith("name="):  # quirk 'Name=Name=...' de la ley
        v = v[5:].strip()
    return v


def ley_fields(n):
    """Campos ley para OBJ n con guard big-vs-sp (si Name difiere, big se descarta)."""
    sp = {k.lower(): (k, clean_val(v)) for k, v in B.ley_section_fields(B.ley_sp_raw, n)}
    big = {k.lower(): (k, clean_val(v)) for k, v in B.ley_section_fields(B.ley_big_raw, n)}
    if sp and big:
        a = sp.get("name", ("", ""))[1]
        c = big.get("name", ("", ""))[1]
        if a and c and norm(a) != norm(c):
            return sp
    d = dict(big)
    d.update(sp)
    return d


def load_bodies_grhs():
    cu = open(os.path.join(INIT_DIR, "cuerpos.dat"), "rb").read().decode("cp1252", errors="replace")
    bodies = {int(x) for x in re.findall(r"(?im)^\s*\[BODY(\d+)\]", cu)}
    b = open(os.path.join(INIT_DIR, "graficos.ind"), "rb").read()
    o, count, grhs = 8, struct.unpack_from("<i", b, 4)[0], set()
    while o < len(b):
        gid = struct.unpack_from("<i", b, o)[0]; o += 4
        fr = struct.unpack_from("<h", b, o)[0]; o += 2
        if fr <= 0:
            break
        o += (4 * fr + 4) if fr > 1 else (4 + 2 + 2 + 2 + 2)
        grhs.add(gid)
        if gid == count:
            break
    return bodies, grhs


BODIES, GRHS = load_bodies_grhs()
visual_kept = []


def visual_ok(key, val):
    if not val.isdigit() or int(val) == 0:
        return True
    if VIS_BODY.match(key):
        return int(val) in BODIES
    if VIS_GRH.match(key):
        return int(val) in GRHS
    return True


def rebuild_obj(n, ours_f, tag):
    """Seccion oficial limpia desde ley(+wiki), visual con fallback a lo nuestro."""
    fields, seen = [], set()
    for kl, (k, v) in ley_fields(n).items():
        ck = B.CANON_BASE.get(kl, k) if not kl.startswith(LANG_PREF) else None
        if kl.startswith(LANG_PREF):
            continue
        if ck.lower() in seen:
            continue
        if (VIS_BODY.match(ck) or VIS_GRH.match(ck)) and not visual_ok(ck, v):
            prev = ours_f.get(ck.lower())
            if prev and visual_ok(ck, prev[1]):
                visual_kept.append((n, ck, v, prev[1]))
                v = prev[1]
        seen.add(ck.lower())
        fields.append((ck, v))
    for k, v in B.WIKI.get(n, {}).items():
        kl = k.lower()
        if kl in seen or kl.startswith(LANG_PREF):
            continue
        ck = B.CANON_BASE.get(kl, k)
        if ck.lower() in seen:
            continue
        if (VIS_BODY.match(ck) or VIS_GRH.match(ck)) and not visual_ok(ck, v):
            continue
        seen.add(ck.lower())
        fields.append((ck, v))
    base_casing = {f[0].lower(): f[0] for f in fields}
    for src in (ley_fields(n), {k.lower(): (k, v) for k, v in B.WIKI.get(n, {}).items()}):
        for kl, kv in src.items():
            if not kl.startswith(LANG_PREF) or kl in seen:
                continue
            base = kv[0][3:]
            cb = base_casing.get(base.lower()) or B.CANON_BASE.get(base.lower(), base)
            seen.add(kl)
            fields.append((kl[:3] + cb, kv[1]))
    lines = [f"[OBJ{n}] '{tag}"]
    lines += [B.to_cp1252(f"{k}={v}") for k, v in fields]
    lines.append("")
    return lines


def patch_obj(n, lines):
    """Mismo item renombrado: alinea campos base diferentes de la ley."""
    ley = {}
    for kl, (k, v) in ley_fields(n).items():
        if not kl.startswith(LANG_PREF):
            ley[kl] = (B.CANON_BASE.get(kl, k), v)
    changed = 0
    new_lines = list(lines)
    present = set()
    for i, ln in enumerate(new_lines):
        s = ln.strip()
        if not s or s.startswith("'") or "=" not in s or s.startswith("["):
            continue
        k, _, v = ln.partition("=")
        key, kl = k.strip(), k.strip().lower()
        present.add(kl)
        if kl not in ley:
            continue
        cur = v.split("'")[0].strip() if kl not in TEXT_KEYS else v.strip()
        new = ley[kl][1]
        if norm(cur) == norm(new):
            continue
        if (VIS_BODY.match(key) or VIS_GRH.match(key)) and not visual_ok(key, new):
            visual_kept.append((n, key, new, cur))
            continue
        new_lines[i] = B.to_cp1252(f"{key}={new}")
        changed += 1
    add = []
    for kl, (k, v) in ley.items():
        if kl in present:
            continue
        if (VIS_BODY.match(k) or VIS_GRH.match(k)) and not visual_ok(k, v):
            continue
        add.append((k, v))
    if add:
        j = len(new_lines)
        while j > 0 and new_lines[j - 1].strip() == "":
            j -= 1
        new_lines[j:j] = [B.to_cp1252(f"{k}={v}") for k, v in add]
        changed += len(add)
    return new_lines, changed


def main():
    path = os.path.join(OURS_DAT, "obj.dat")
    dat = open(path, "rb").read().decode("cp1252")

    # nombres nuestros y de la ley
    def names_of(txt):
        out = {}
        for m in re.finditer(r"(?ms)^\[OBJ(\d+)\][^\n]*\n(.*?)(?=^'?\s*\[|\Z)", txt):
            g = re.search(r"(?im)^Name=([^\r\n]+)", m.group(2))
            out[int(m.group(1))] = clean_val(g.group(1)) if g else ""
        return out

    ours_n = names_of(dat)
    ley_n = {}
    for n in set(ours_n):
        f = ley_fields(n)
        if f.get("name"):
            ley_n[n] = f["name"][1]
    ley_all_names = {}
    for m in re.finditer(r"(?ms)^\[OBJ(\d+)\][^\n]*\n(.*?)(?=^\[|\Z)",
                         B.ley_sp_raw):
        g = re.search(r"(?im)^Name=([^\r\n]+)", m.group(2))
        if g:
            ley_all_names.setdefault(norm(clean_val(g.group(1))), []).append(int(m.group(1)))

    renames, identity = [], []
    for n in sorted(set(ours_n) & set(ley_n)):
        if n in PROTECTED:
            continue
        a, b = ours_n[n], ley_n[n]
        if not b or norm(a) == norm(b):
            continue
        (renames if same_item(a, b) else identity).append(n)

    # referencias actuales (para decidir reubicacion y re-mapear)
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    npath = os.path.join(OURS_DAT, "npcs.dat")
    q_raw = open(qpath, "rb").read().decode("cp1252")
    n_raw = open(npath, "rb").read().decode("cp1252")

    def is_referenced(n):
        return bool(re.search(r"(?im)^(Required|Reward)Obj\d*\s*=\s*%d\b" % n, q_raw) or
                    re.search(r"(?im)^(Obj\d+\s*=\s*%d-|QuizaDropea\d+\s*=\s*%d\b)" % (n, n), n_raw))

    id_map, reloc, overwrite = {}, {}, []
    next_id = RELOC_BASE
    for n in identity:
        old_name = ours_n[n]
        tgt = ley_all_names.get(norm(old_name))
        if not tgt:
            base = norm(re.sub(r"\s*\([^)]*\)\s*$", "", old_name))
            tgt = ley_all_names.get(base)
        if tgt:
            id_map[n] = min(tgt)
        elif is_referenced(n) or n in KEEP_ALWAYS:
            reloc[n] = next_id
            id_map[n] = next_id
            next_id += 1
        else:
            overwrite.append(n)

    # --- aplicar sobre bloques ---
    blocks = B.split_blocks(dat)
    out_blocks, n_patch, n_rebuild, patched_fields = [], 0, 0, 0
    reloc_secs = []
    for bid, commented, lines in blocks:
        if bid is None or commented or bid in PROTECTED:
            out_blocks.append(lines)
            continue
        if bid in reloc:
            sec = list(lines)
            sec[0] = (f"[OBJ{reloc[bid]}] 'Reubicado de OBJ{bid} (punto ciego: oficial "
                      f"repropuso el slot; plan 10.001 fase 3)")
            reloc_secs.append(sec)
        if bid in identity:
            ours_f = {k.lower(): (k, v.split("'")[0].strip()) for k, v in
                      (ln.split("=", 1) for ln in lines[1:]
                       if "=" in ln and not ln.strip().startswith("'") and ln.strip())}
            out_blocks.append(rebuild_obj(bid, ours_f,
                              "Realineado a oficial 2026-06-08 (punto ciego repo==nuestro)"))
            n_rebuild += 1
        elif bid in renames:
            new_lines, ch = patch_obj(bid, lines)
            out_blocks.append(new_lines)
            n_patch += 1
            patched_fields += ch
        else:
            out_blocks.append(lines)

    result = "\r\n".join("\r\n".join(b) for b in out_blocks).rstrip("\r\n")
    if reloc_secs:
        result += ("\r\n\r\n' ---- Customs reubicados (punto ciego, plan 10.001) ----\r\n\r\n"
                   + "\r\n".join("\r\n".join(s).rstrip("\r\n") + "\r\n" for s in reloc_secs))
    max_id = max([9038] + list(reloc.values()))
    assert "NumOBJs=9038\r\n" in result
    result = result.replace("NumOBJs=9038\r\n", f"NumOBJs={max_id}\r\n", 1)
    open(path, "w", encoding="cp1252", newline="").write(result)
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto en obj.dat"

    # --- re-mapeo de referencias ---
    # Quests.DAT: 100% legacy nuestro (las oficiales se adoptan recien en el batch
    # QUESTS) -> remap completo. npcs.dat: el batch NPCs ya alineo inventarios y
    # drops a la ley (layout NUEVO) -> remap SOLO en secciones que la ley no
    # gestiona (adelantado/revisar/customs); el resto ya habla el layout nuevo.
    def remap_lines(text, hits, fname):
        def sub_plain(m):
            old = int(m.group(2))
            if old in id_map:
                hits.append((fname, old, id_map[old]))
                return f"{m.group(1)}{id_map[old]}{m.group(3) if m.lastindex >= 3 else ''}"
            return m.group(0)
        text = re.sub(r"(?im)^((?:Required|Reward)Obj\d*\s*=\s*)(\d+)\b", sub_plain, text)
        text = re.sub(r"(?im)^(Obj\d+\s*=\s*)(\d+)(-)", sub_plain, text)
        text = re.sub(r"(?im)^(QuizaDropea\d+\s*=\s*)(\d+)\b", sub_plain, text)
        return text

    q_hits, n_hits = [], []
    q_new = remap_lines(q_raw, q_hits, "Quests.DAT")
    open(qpath, "w", encoding="cp1252", newline="").write(q_new)

    import batch_npcs_fase3 as N
    npc_blocks = N.split_blocks(n_raw)
    ley_npc_ids = set(N.ley_sp)
    out_npc = []
    for bid, commented, lines in npc_blocks:
        if bid is not None and not commented and bid not in ley_npc_ids:
            out_npc.append(remap_lines("\r\n".join(lines), n_hits, f"NPC{bid}").split("\r\n"))
        else:
            out_npc.append(lines)

    # re-correr alineacion de vendedores (recupera los omitidos por identidad)
    final_names = names_of(open(path, "rb").read().decode("cp1252"))
    N.OBJ_NAMES = final_names
    N.seller_skips, N.seller_renames, N.blindspot = [], [], {}
    n_sellers = 0
    for i, blk in enumerate(out_npc):
        if not blk:
            continue
        m = N.HEADER_RE.match(blk[0])
        if m and not m.group(1) and int(m.group(2)) in N.wiki_sell:
            out_npc[i], _ = N.apply_seller(int(m.group(2)), blk)
            n_sellers += 1
    open(npath, "w", encoding="cp1252", newline="").write(
        "\r\n".join("\r\n".join(b) for b in out_npc))
    for p in (qpath, npath):
        bb = open(p, "rb").read()
        assert bb.count(b"\n") == bb.count(b"\r\n"), f"CRLF roto en {p}"
    print(f"vendedores re-alineados: {n_sellers} | items aun omitidos: {len(N.seller_skips)}")
    for s in N.seller_skips[:8]:
        print(f"   NPC{s[0]} OBJ{s[1]}={s[2]}: {s[3]}")

    # --- lockfile ---
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    objs = set(lock["protected"].get("OBJ", []))
    lock["protected"]["OBJ"] = sorted(objs | set(reloc.values()))
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # --- reporte ---
    print(f"renames realineados: {n_patch} (campos: {patched_fields})")
    print(f"identidades reconstruidas: {n_rebuild} | pisadas sin referencia: {len(overwrite)}")
    print(f"re-mapeos de id (item movido por oficial): {len(id_map) - len(reloc)}")
    print(f"reubicados a 9039+: {len(reloc)} -> {sorted(reloc.items())}")
    print(f"refs re-apuntadas: Quests {len(q_hits)} | npcs {len(n_hits)}")
    print(f"visual conservado nuestro: {len(visual_kept)}")
    final = open(path, "rb").read().decode("cp1252")
    fn = names_of(final)
    for n, want in ((460, "Pluma"), (3075, "Frasco"), (15, "Daga"), (2467, "Invocar Lobo")):
        got = fn.get(n, "?")
        print(f"  OBJ{n}.Name = {got!r} ({'OK' if want.lower() in got.lower() else 'MAL'})")
    hdrs = [int(x) for q_, x in re.findall(r"(?m)^('*)\s*\[OBJ(\d+)\]", final) if not q_]
    dups = sorted({x for x in hdrs if hdrs.count(x) > 1})
    print(f"  duplicados: {dups or 'ninguno'} | NumOBJs={max_id}")


if __name__ == "__main__":
    main()
