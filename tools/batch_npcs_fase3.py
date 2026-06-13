# -*- coding: utf-8 -*-
"""Fase 3 batch NPCs + vendedores (plan 10.001).

Fuentes y prioridad: ley sp_localindex (primaria; el repo esta DESACTUALIZADO para
NPCs: 365 nombres difieren) > ley localindex grande (rellena; sp pisa) > wiki API
(hostiles: stats server PoderAtaque/PoderEvasion; vendedores: inventarios completos).

Lecciones del batch OBJs aplicadas:
- Slot repropuesto = Name cambiado (norm) -> REBUILD limpio desde ley+wiki.
  Name igual -> PATCH campo a campo preservando claves nuestras (custom incl.).
- Claves visuales (Body/Head/BodyIdle/Ataque*/BodyOn*) NUNCA se alinean si el
  destino no existe en los registros locales (cuerpos.dat / cabezas.ini).
- Claves de la ley son de CLIENTE: EXP/HP/ORO se re-mapean a GiveEXP/MaxHp/GiveGLD
  (las que lee el server, FileIO.bas/MODULO_NPCs.bas).
- Customs colisionando se reubican: 1804 Vibora Test -> 9007, 1805 Escorpion
  Test -> 9008, 1806 Arana Test -> 9009 (decision usuario: conservar como ejemplos).

Ademas: borra NPC30/31 (marcados, sin referencias), limpia las 64 secciones
comentadas aprobadas, alinea inventarios de los 74 vendedores de la wiki
(items con identidad distinta a la nuestra se omiten y loguean).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import LEY_INIT, OURS_DAT, parse_sections

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
WIKI = r"c:\AO20\dev\oficial\wiki-api"
INIT_DIR = r"c:\AO20\dev\Recursos\init"

PROTECTED = set(range(9000, 9007))
RELOC = {1804: 9007, 1805: 9008, 1806: 9009}
BORRAR = {30, 31}
LANG_PREF = ("en_", "pt_", "fr_", "it_")
TEXT_KEYS = ("name", "desc", "descclose")

# clave ley (cliente) -> clave dat (server)
LEY2DAT = {"exp": "GiveEXP", "oro": "GiveGLD", "hp": "MaxHp"}
BODY_KEYS = {"body", "bodyidle", "ataque1", "ataque2", "bodyonland",
             "bodyonwater", "bodyonwateridle"}
HEAD_KEYS = {"head"}

CANON = {k.lower(): k for k in (
    "Name", "Desc", "DescClose", "Body", "Head", "BodyIdle", "Ataque1", "Ataque2",
    "BodyOnLand", "BodyOnWater", "BodyOnWaterIdle", "NpcType", "Comercia", "Nivel",
    "GiveEXP", "GiveGLD", "MaxHp", "MinHp", "MaxHIT", "MinHIT", "PoderAtaque",
    "PoderEvasion", "Hostile", "Attackable", "Movement", "Heading", "TipoItems",
    "NROITEMS", "SoundOpen", "ShowName", "MiniMap", "NoMapInfo", "NumQuiza",
    "PuedeInvocar", "QuizaProb", "IsGlobalQuestBoss",
)}

HOSTIL_KEYS = {"poderataque", "poderevasion", "nivel", "attackable", "hostile",
               "movement", "heading", "giveexp", "givegld", "maxhit", "minhit",
               "maxhp", "minhp", "body", "bodyidle", "ataque1", "head"}

HEADER_RE = re.compile(r"^\s*('*)\s*\[NPC(\d+)\]", re.IGNORECASE)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def canon_key(k):
    kl = k.lower()
    kl = LEY2DAT.get(kl, kl).lower() if kl in LEY2DAT else kl
    return CANON.get(kl, LEY2DAT.get(k.lower(), k))


# ---------- carga de fuentes ----------
def ley_fields_all(raw):
    out = {}
    for m in re.finditer(r"(?ms)^\[NPC(\d+)\][^\n]*\n(.*?)(?=^\[|\Z)", raw):
        d = {}
        for ln in m.group(2).split("\n"):
            ln = ln.strip()
            if not ln or ln.startswith("'") or "=" not in ln:
                continue
            k, _, v = ln.partition("=")
            k, v = k.strip(), v.strip()
            if k and v != "" and k.lower() not in d:
                d[k.lower()] = (k, v)
        out[int(m.group(1))] = d
    return out


actions = json.load(open(os.path.join(OUT_DIR, "fase2_acciones.json"), encoding="utf-8"))["NPC"]
fix_ids = (set(actions["corregir_texto"]) | set(actions["corregir_balance"])) - PROTECTED - set(RELOC)
stub_ids = sorted(set(actions["migrar_texto"]) - PROTECTED)
limpieza = set(actions["limpieza_comentadas"])

path = os.path.join(OURS_DAT, "npcs.dat")
ours_raw = open(path, "rb").read().decode("cp1252")
ley_sp = ley_fields_all(open(os.path.join(LEY_INIT, "sp_localindex.dat"), "rb")
                        .read().decode("cp1252").replace("\r\n", "\n"))
ley_big = ley_fields_all(open(os.path.join(LEY_INIT, "localindex.dat"), "rb")
                         .read().decode("cp1252").replace("\r\n", "\n"))


def ley_of(n):
    """Campos de la ley para NPC n. El localindex grande es un snapshot VIEJO
    (215 ids con Name distinto al sp: Liliana/Horacio/Eldrin...): si los dos
    indices no coinciden en Name, el big se descarta entero para ese id (evita
    contaminacion tipo Hormiga Negra con Desc del Skills Seller). Si coinciden,
    big rellena lo que al sp le falte (idiomas, etc.)."""
    sp = ley_sp.get(n, {})
    big = ley_big.get(n, {})
    if sp and big:
        a, b = sp.get("name", ("", ""))[1], big.get("name", ("", ""))[1]
        if a and b and norm(a) != norm(b):
            return dict(sp)
    d = dict(big)
    d.update(sp)
    return d


bodies = {int(x) for x in re.findall(
    r"(?im)^\s*\[BODY(\d+)\]",
    open(os.path.join(INIT_DIR, "cuerpos.dat"), "rb").read().decode("cp1252", errors="replace"))}
heads = {int(x) for x in re.findall(
    r"(?im)^\s*\[HEAD(\d+)\]",
    open(os.path.join(INIT_DIR, "cabezas.ini"), "rb").read().decode("cp1252", errors="replace"))}

wiki_host = {}
for it in json.load(open(os.path.join(WIKI, "getAllHostileNpcs.json"), encoding="utf-8")):
    if isinstance(it, dict) and "id" in it:
        wiki_host[int(it["id"])] = {k: str(v).strip() for k, v in it.items()
                                    if isinstance(v, (str, int, float)) and str(v).strip()}
wiki_sell = {}
for it in json.load(open(os.path.join(WIKI, "getAllSellersNpcs.json"), encoding="utf-8")):
    if isinstance(it, dict) and "id" in it:
        wiki_sell[int(it["id"])] = it

visual_kept, visual_broken = [], []
seller_renames, blindspot = [], {}

STOPWORDS = {"de", "del", "la", "el", "los", "las", "y"}


def same_item(a, b):
    """Heuristica rename-vs-repropuesto: comparten algun token de contenido."""
    ta = {t for t in re.findall(r"\w{4,}", norm(a)) if t not in STOPWORDS}
    tb = {t for t in re.findall(r"\w{4,}", norm(b)) if t not in STOPWORDS}
    return bool(ta & tb)


def visual_ok(key, val):
    kl = key.lower()
    if not val.isdigit() or int(val) == 0:
        return True
    if kl in BODY_KEYS:
        return int(val) in bodies
    if kl in HEAD_KEYS:
        return int(val) in heads
    return True


def section_fields(lines):
    d = {}
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("'") or "=" not in s or s.startswith("["):
            continue
        k, _, v = s.partition("=")
        d.setdefault(k.strip().lower(), (k.strip(), v.split("'")[0].strip()))
    return d


def build_npc(n, ours_f, tag):
    """Seccion nueva desde ley (+wiki hostil), claves server-mapeadas, visual con
    fallback a lo nuestro, custom keys nuestras preservadas al final."""
    fields, seen = [], set()
    for kl, (k, v) in ley_of(n).items():
        if kl.startswith(LANG_PREF):
            continue
        ck = canon_key(k)
        if ck.lower() in seen:
            continue
        if (ck.lower() in BODY_KEYS | HEAD_KEYS) and not visual_ok(ck, v):
            prev = ours_f.get(ck.lower())
            if prev and visual_ok(ck, prev[1]):
                visual_kept.append((n, ck, v, prev[1]))
                v = prev[1]
            else:
                visual_broken.append((n, ck, v))
        seen.add(ck.lower())
        fields.append((ck, v))
        if ck == "MaxHp" and "minhp" not in seen:
            seen.add("minhp")
            fields.append(("MinHp", v))
    for k, v in wiki_host.get(n, {}).items():
        kl = k.lower()
        if kl not in HOSTIL_KEYS:
            continue
        ck = canon_key(k)
        if ck.lower() in seen:
            continue
        if (ck.lower() in BODY_KEYS | HEAD_KEYS) and not visual_ok(ck, v):
            visual_broken.append((n, ck, v))
            continue
        seen.add(ck.lower())
        fields.append((ck, v))
    # idiomas al final, casing alineado a la base
    for src in (ley_of(n), {k.lower(): (k, v) for k, v in wiki_host.get(n, {}).items()}):
        for kl, kv in src.items():
            if not kl.startswith(LANG_PREF) or kl in seen:
                continue
            base = kv[0][3:]
            cb = next((f[0] for f in fields if f[0].lower() == base.lower()), canon_key(base))
            seen.add(kl)
            fields.append((kl[:3] + cb, kv[1]))
    # custom nuestras que la ley no conoce
    kept_custom = []
    for kl, (k, v) in ours_f.items():
        if re.match(r"(?i)^(PerfilVeneno\w*|RequireToggle|EsMaestro\w*|Profesion\w*)$", k) \
                and kl not in seen:
            seen.add(kl)
            fields.append((k, v))
            kept_custom.append(k)
    lines = [f"[NPC{n}] '{tag}"]
    lines += [f"{k}={v}" for k, v in fields]
    lines.append("")
    return lines, kept_custom


def patch_npc(n, lines):
    """Name igual: alinea campos diferentes de la ley sobre nuestra seccion.
    PoderAtaque/PoderEvasion vienen de la wiki (la ley no los publica) y son
    balance -> tambien convergen a oficial."""
    ours_f = section_fields(lines)
    ley = {}
    for kl, (k, v) in ley_of(n).items():
        if kl.startswith(LANG_PREF):
            continue
        ck = canon_key(k)
        ley[ck.lower()] = (ck, v)
    for k, v in wiki_host.get(n, {}).items():
        kl = k.lower()
        if kl in ("poderataque", "poderevasion") or (
                kl in HOSTIL_KEYS - BODY_KEYS - HEAD_KEYS and canon_key(k).lower() not in ley):
            ck = canon_key(k)
            ley.setdefault(ck.lower(), (ck, v))
            if kl in ("poderataque", "poderevasion"):
                ley[ck.lower()] = (ck, v)
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
        if kl in BODY_KEYS | HEAD_KEYS and not visual_ok(key, new):
            visual_kept.append((n, key, new, cur))
            continue
        new_lines[i] = f"{key}={new}"
        changed += 1
    add = []
    for kl, (k, v) in ley.items():
        if kl in present:
            continue
        if kl in BODY_KEYS | HEAD_KEYS and not visual_ok(k, v):
            visual_broken.append((n, k, v))
            continue
        if kl == "maxhp" and "minhp" not in present and "minhp" not in ley:
            add.append(("MinHp", v))
        add.append((k, v))
    if add:
        j = len(new_lines)
        while j > 0 and new_lines[j - 1].strip() == "":
            j -= 1
        new_lines[j:j] = [f"{k}={v}" for k, v in add]
        changed += len(add)
    return new_lines, changed


def apply_seller(n, lines):
    """Reemplaza inventario del vendedor con el oficial; items cuya identidad no
    coincide con nuestro obj.dat se omiten (punto ciego repo-vs-ley)."""
    s = wiki_sell[n]
    items = []
    for i in range(1, int(s.get("NROITEMS", 0)) + 1):
        raw = str(s.get(f"OBJ{i}", "")).strip()
        if not raw:
            continue
        oid = int(raw.split("-")[0])
        # OBJSINFORMATION: lista de {id, qty, Data:{NAME...}}
        oname = None
        for d in (s.get("OBJSINFORMATION") or []):
            if isinstance(d, dict) and str(d.get("id")) == str(oid):
                oname = (d.get("Data") or {}).get("NAME")
                break
        ours_name = OBJ_NAMES.get(oid)
        if ours_name is None:
            seller_skips.append((n, i, raw, "no existe en obj.dat"))
            continue
        if oname and norm(oname) != norm(ours_name):
            # rename oficial (mismo item) vs identidad distinta (punto ciego)
            if same_item(oname, ours_name):
                seller_renames.append((oid, ours_name, oname))
            else:
                seller_skips.append((n, i, raw, f"identidad distinta: "
                                                f"oficial={oname!r} nuestro={ours_name!r}"))
                blindspot.setdefault(oid, (ours_name, oname))
                continue
        items.append(raw)
    new_lines = [ln for ln in lines
                 if not re.match(r"(?i)^\s*(Obj\d+|NROITEMS|TipoItems)\s*=", ln.strip())]
    add = [f"TipoItems={s.get('TIPOITEMS', '100')}", f"NROITEMS={len(items)}"]
    add += [f"Obj{i}={raw}" for i, raw in enumerate(items, 1)]
    j = len(new_lines)
    while j > 0 and new_lines[j - 1].strip() == "":
        j -= 1
    new_lines[j:j] = add
    return new_lines, len(items)


def split_blocks(text):
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


def main():
    global OBJ_NAMES, seller_skips
    obj_dat = open(os.path.join(OURS_DAT, "obj.dat"), "rb").read().decode("cp1252")
    OBJ_NAMES = {}
    for m in re.finditer(r"(?ms)^\[OBJ(\d+)\][^\n]*\n(.*?)(?=^'?\s*\[|\Z)", obj_dat):
        g = re.search(r"(?im)^Name=([^\r\n]+)", m.group(2))
        if g:
            OBJ_NAMES[int(m.group(1))] = g.group(1).strip()
    seller_skips = []

    blocks = split_blocks(ours_raw)
    pre = {bid: "\r\n".join(ls) for bid, c, ls in blocks if bid in PROTECTED and not c}

    n_patch = n_rebuild = n_borrar = n_limpieza = patched_fields = 0
    rebuilt_ids, reloc_secs, custom_kept = [], [], []
    out_blocks = []
    for bid, commented, lines in blocks:
        if bid is None or bid in PROTECTED:
            out_blocks.append(lines)
            continue
        if commented:
            if bid in limpieza:
                n_limpieza += 1
                continue  # corpse aprobado: fuera
            out_blocks.append(lines)
            continue
        if bid in BORRAR:
            n_borrar += 1
            continue
        if bid in RELOC:
            new_id = RELOC[bid]
            sec = list(lines)
            sec[0] = (f"[NPC{new_id}] 'Reubicado de NPC{bid} por colision con slot oficial; "
                      f"conservado como ejemplo (plan 10.001 fase 3)")
            reloc_secs.append((sec, new_id))
            if ley_of(bid):  # la ley define el slot -> reconstruir oficial
                stub, kept = build_npc(bid, {}, "Reconstruido de localindex oficial 2026-06-08 "
                                              "(slot era custom nuestro, reubicado)")
                out_blocks.append(stub)
                rebuilt_ids.append(bid)
            continue
        if bid in fix_ids:
            ours_f = section_fields(lines)
            ley_name = ley_of(bid).get("name", ("", ""))[1]
            our_name = ours_f.get("name", ("", ""))[1]
            if ley_name and norm(ley_name) != norm(our_name):
                stub, kept = build_npc(bid, ours_f, "Realineado a oficial 2026-06-08 "
                                                    "(slot repropuesto)")
                if kept:
                    custom_kept.append((bid, kept))
                out_blocks.append(stub)
                n_rebuild += 1
                rebuilt_ids.append(bid)
            else:
                new_lines, ch = patch_npc(bid, lines)
                out_blocks.append(new_lines)
                n_patch += 1
                patched_fields += ch
            continue
        out_blocks.append(lines)

    # stubs nuevos
    stub_lines = []
    for n in stub_ids:
        sl, _ = build_npc(n, {}, "Reconstruido de localindex oficial 2026-06-08 "
                                 "(repo capado, sin logica publica)")
        stub_lines.extend(sl)

    # vendedores sobre el resultado
    n_sellers = 0
    for i, blk in enumerate(out_blocks):
        if not blk or not HEADER_RE.match(blk[0]):
            continue
        m = HEADER_RE.match(blk[0])
        bid = int(m.group(2))
        if not m.group(1) and bid in wiki_sell:
            out_blocks[i], cnt = apply_seller(bid, blk)
            n_sellers += 1
    new_stub_blocks = []
    cur = []
    for ln in stub_lines:
        if HEADER_RE.match(ln):
            if cur:
                new_stub_blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        new_stub_blocks.append(cur)
    for i, blk in enumerate(new_stub_blocks):
        bid = int(HEADER_RE.match(blk[0]).group(2))
        if bid in wiki_sell:
            new_stub_blocks[i], _ = apply_seller(bid, blk)
            n_sellers += 1

    banner = ["", "' =====================================================================",
              "' NPCs reconstruidos del localindex oficial (Steam 2026-06-08) y wiki API.",
              "' El repo publico esta capado/desactualizado para NPCs: la ley es la",
              "' fuente primaria. Stats server de hostiles desde getAllHostileNpcs.",
              "' Plan 10.001 Fase 3, batch NPCs.",
              "' =====================================================================", ""]
    reloc_banner = ["", "' ---- Customs reubicados (colision con slots oficiales) ----", ""]

    result = "\r\n".join("\r\n".join(b) for b in out_blocks).rstrip("\r\n")
    result += "\r\n" + "\r\n".join(banner)
    result += "\r\n".join("\r\n".join(b) + "\r\n" for b in new_stub_blocks)
    result += "\r\n".join(reloc_banner) + "\r\n"
    result += "\r\n".join("\r\n".join(sec) + "\r\n" for sec, _ in reloc_secs)
    assert "NumNPCs=9006\r\n" in result, "contador NumNPCs no encontrado"
    result = result.replace("NumNPCs=9006\r\n", "NumNPCs=9009\r\n", 1)

    open(path, "w", encoding="cp1252", newline="").write(result)
    b = open(path, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"

    # lockfile
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    npcs = set(lock["protected"].get("NPC", []))
    lock["protected"]["NPC"] = sorted(npcs | set(RELOC.values()))
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # ---------- validaciones ----------
    final = parse_sections(path, ("NPC",))["NPC"]
    active = {k for k, s in final.items() if not s["commented"]}
    post_blocks = split_blocks(open(path, "rb").read().decode("cp1252"))
    post = {bid: "\r\n".join(ls) for bid, c, ls in post_blocks if bid in PROTECTED and not c}
    hdrs = [int(x) for q, x in re.findall(r"(?m)^('*)\s*\[NPC(\d+)\]",
                                          open(path, "rb").read().decode("cp1252")) if not q]
    dups = sorted({x for x in hdrs if hdrs.count(x) > 1})

    print(f"patch: {n_patch} (campos: {patched_fields}) | rebuild: {n_rebuild} | "
          f"stubs: {len(new_stub_blocks)} | vendedores alineados: {n_sellers}")
    print(f"borrados: {n_borrar} | comentadas limpiadas: {n_limpieza} | "
          f"reubicados: {[(f'NPC{o}->NPC{d}') for o, d in RELOC.items()]}")
    print(f"custom keys preservadas en rebuilds: {custom_kept}")
    print(f"visual conservado nuestro (destino ley inexistente): {len(visual_kept)}")
    print(f"visual roto sin fallback (cascara): {len(visual_broken)}")
    print(f"items de vendedor: renames tolerados {len(seller_renames)} | "
          f"omitidos por identidad {len(seller_skips)}")
    for s in seller_skips[:12]:
        print(f"   NPC{s[0]} OBJ{s[1]}={s[2]}: {s[3]}")
    if blindspot:
        bs = os.path.join(OUT_DIR, "obj_blindspot_vendedores.txt")
        with open(bs, "w", encoding="utf-8", newline="\n") as f:
            f.write("# OBJs con identidad distinta a la ley detectados via vendedores\n"
                    "# (punto ciego fase 2: repo viejo == nuestro, ley cambio). Pasada pendiente.\n")
            for oid, (ours_n, ley_n) in sorted(blindspot.items()):
                f.write(f"OBJ{oid}: nuestro={ours_n!r} oficial={ley_n!r}\n")
        print(f"punto ciego obj.dat registrado: {len(blindspot)} ids -> {bs}")
    print(f"secciones activas: {len(active)} (esperado 1075) | duplicados: {dups or 'ninguno'}")
    print(f"protegidos 9000-9006 intactos: {all(pre[k] == post.get(k) for k in pre)}")
    for n, key, want in ((1334, "requiretoggle", None), (9007, "name", "Vibora Test"),
                         (9008, "name", "Escorpion Test"), (9009, "name", "Arana Test"),
                         (1804, "name", None), (511, "poderataque", "5")):
        got = final.get(n, {}).get("fields", {}).get(key, "?")
        ok = "OK" if (want is None and got != "?") or got == want else ("?" if want is None else "MAL")
        print(f"  NPC{n}.{key} = {got!r} {ok}")


if __name__ == "__main__":
    main()
