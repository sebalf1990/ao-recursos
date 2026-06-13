# -*- coding: utf-8 -*-
"""Plan 10.001 Fase 2: diff fino por dominio (solo lectura).

Fuentes:
  LEY     dev/oficial/recursos_20260610/init/  (Steam 2026-06-08; sp_localindex + localindex)
  REPO    dev/oficial/ao-org-recursos/Dat/     (logica server oficial; UTF-8!)
  NUESTRO dev/Recursos/Dat/ + dev/Recursos/init/sp_localindex.dat

Clasificacion por ID y dominio (HECHIZO/OBJ/NPC/QUEST):
  MIGRAR        en ley, falta en nuestro, con logica server disponible en repo
  MIGRAR_TEXTO  en ley, falta en nuestro, SIN logica en repo (solo cascara cliente)
  CORREGIR      en ambos, campos distintos (case-insensitive); separa texto vs balance
  PROTEGER      solo nuestro, en lockfile (rangos nuevos 9000+/400+ y review aprobado)
  BORRAR        solo nuestro, marcado (comentarios 'borrar' / secciones comentadas)
  ADELANTADO    en repo pero NO en ley (Steam no lo publico) -> esperar
  REVISAR       solo nuestro sin marca ni lockfile

Extras: validacion de GRH/Body referenciados por lo que se migra, re-check de
mensajes y sonidos contra la ley fresca.
"""
import json
import os
import re
import struct
from collections import defaultdict

ROOT = r"c:\AO20"
LEY_INIT = os.path.join(ROOT, r"dev\oficial\recursos_20260610\init")
REPO_DAT = os.path.join(ROOT, r"dev\oficial\ao-org-recursos\Dat")
OURS_DAT = os.path.join(ROOT, r"dev\Recursos\Dat")
OURS_INIT = os.path.join(ROOT, r"dev\Recursos\init")
OUT_DIR = os.path.join(ROOT, r"ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs")
REPORT = os.path.join(ROOT, r"ia\reports\2026-06-10-fase2-diff-fino.md")

LOCK = json.load(open(os.path.join(OUT_DIR, "protected.lock.json"), encoding="utf-8"))

DOMAINS = {
    "HECHIZO": {"ours_dat": "Hechizos.dat", "repo_dat": "Hechizos.dat"},
    "OBJ": {"ours_dat": "obj.dat", "repo_dat": "obj.dat"},
    "NPC": {"ours_dat": "npcs.dat", "repo_dat": "npcs.dat"},
    "QUEST": {"ours_dat": "Quests.DAT", "repo_dat": "Quests.DAT"},
}

# Campos de "balance" (decision aparte: la ley gana en texto; en balance decide el usuario)
BALANCE_FIELDS = {
    "NPC": {"hp", "maxhp", "minhit", "maxhit", "exp", "giveexp", "oro", "givegld", "nivel",
            "def", "defm", "poderataque", "poderevasion", "veneno"},
    "OBJ": {"minhit", "maxhit", "mindef", "maxdef", "valor", "minhp", "maxhp"},
    "HECHIZO": {"manarequerido", "starequerido", "minskill", "maxskill", "minhp", "maxhp",
                "danomin", "danomax", "cooldown"},
    "QUEST": {"rewardexp", "rewardgld", "requiredlevel"},
}

DELETE_RE = re.compile(r"\b(borrar|eliminar)\b", re.IGNORECASE)
HEADER_RE = re.compile(r"^\s*('*)\s*\[([A-Z_]+?)(\d+)\]\s*(.*)$", re.IGNORECASE)


def read_text(path, encoding):
    return open(path, "rb").read().decode(encoding, errors="strict")


def detect_decode(path):
    """El repo oficial mezcla encodings por archivo: autodetectar utf-8 vs cp1252."""
    b = open(path, "rb").read()
    try:
        t = b.decode("utf-8")
        # utf-8 valido Y con multibyte real -> utf-8; ascii puro da igual
        if re.search(r"[¡¿áéíóúñ]", t) and b != t.encode("ascii", "ignore"):
            return t
        return b.decode("cp1252")
    except UnicodeDecodeError:
        return b.decode("cp1252")


def parse_sections(path, types, encoding="cp1252"):
    """{TYPE: {id: {'fields': {keyLower: value}, 'commented': bool, 'marker': str}}}"""
    out = {t: {} for t in types}
    if encoding == "auto":
        text = detect_decode(path)
    else:
        try:
            text = read_text(path, encoding)
        except UnicodeDecodeError:
            text = open(path, "rb").read().decode(encoding, errors="replace")
    cur = None
    for ln in text.splitlines():
        m = HEADER_RE.match(ln)
        if m:
            quote, typ, num = m.group(1), m.group(2).upper(), int(m.group(3))
            if typ in types:
                commented = bool(quote)
                marker = m.group(4).strip() if DELETE_RE.search(m.group(4)) else None
                out[typ][num] = {"fields": {}, "commented": commented, "marker": marker}
                cur = (typ, num) if not commented else None
            else:
                cur = None
            continue
        if cur and "=" in ln and not ln.lstrip().startswith("'"):
            k, _, v = ln.partition("=")
            k = k.strip().lower()
            v = v.split("'", 1)[0].strip() if "'" in v and k not in (
                "name", "nombre", "desc", "descfinal", "texto") else v.strip()
            if k and k not in out[cur[0]][cur[1]]["fields"]:
                out[cur[0]][cur[1]]["fields"][k] = v
    return out


def norm_text(v):
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def parse_grh_ind(path):
    """IDs de GRH validos en graficos.ind."""
    b = open(path, "rb").read()
    o = 8  # version i32 + count i32
    count = struct.unpack_from("<i", b, 4)[0]
    ids = set()
    while o < len(b):
        gid = struct.unpack_from("<i", b, o)[0]; o += 4
        frames = struct.unpack_from("<h", b, o)[0]; o += 2
        if frames <= 0:
            break
        if frames > 1:
            o += 4 * frames + 4
        else:
            o += 4 + 2 + 2 + 2 + 2
        ids.add(gid)
        if gid == count:
            break
    return ids


def main():
    types = tuple(DOMAINS)
    ley_sp = parse_sections(os.path.join(LEY_INIT, "sp_localindex.dat"), types)
    ley_big = parse_sections(os.path.join(LEY_INIT, "localindex.dat"), types)
    ours_li = parse_sections(os.path.join(OURS_INIT, "sp_localindex.dat"), types)

    report = ["# Fase 2 — Diff fino por dominio (ley Steam 2026-06-08)",
              "",
              "Solo lectura. Acciones propuestas por ID; requiere OK del usuario antes de la Fase 3.",
              "Balance: donde nuestro valor difiere de la ley en campos de balance, se lista aparte",
              "(decision del usuario: conservar nuestro balance o alinear al oficial).", ""]
    actions = {}

    grh_ours = parse_grh_ind(os.path.join(OURS_INIT, "graficos.ind"))
    cuerpos_ours = parse_sections(os.path.join(OURS_INIT, "cuerpos.dat"), ("BODY",))
    bodies_ours = set(cuerpos_ours["BODY"]) if cuerpos_ours["BODY"] else set()
    # fallback: algunos cuerpos.dat usan [INIT]NumBodies sin secciones
    if not bodies_ours:
        t = read_text(os.path.join(OURS_INIT, "cuerpos.dat"), "cp1252")
        m = re.search(r"(?im)^NumBodies\s*=\s*(\d+)", t)
        if m:
            bodies_ours = set(range(1, int(m.group(1)) + 1))

    for typ, cfg in DOMAINS.items():
        ours = parse_sections(os.path.join(OURS_DAT, cfg["ours_dat"]), (typ,))[typ]
        repo = parse_sections(os.path.join(REPO_DAT, cfg["repo_dat"]), (typ,), encoding="auto")[typ]
        ley_ids = set(ley_sp[typ]) | set(ley_big[typ])
        ours_active = {n for n, s in ours.items() if not s["commented"]}

        protected = set(LOCK.get("protected", {}).get(typ, []))
        deletable_lock = set(LOCK.get("deletable", {}).get(typ, []))

        migrar, migrar_texto, corregir_texto, corregir_balance = [], [], [], []
        proteger, borrar, adelantado, revisar = [], [], [], []
        grh_faltantes = defaultdict(list)

        for n in sorted(ley_ids):
            ley_fields = {}
            ley_fields.update(ley_big[typ].get(n, {}).get("fields", {}))
            ley_fields.update(ley_sp[typ].get(n, {}).get("fields", {}))
            name = ley_fields.get("name") or ley_fields.get("nombre") or "(sin nombre)"
            if n not in ours_active:
                if n in repo:
                    migrar.append((n, name))
                else:
                    migrar_texto.append((n, name))
                # validar recursos graficos del contenido a migrar
                grh = ley_fields.get("grhindex")
                if typ == "OBJ" and grh and grh.isdigit() and int(grh) not in grh_ours:
                    grh_faltantes["GrhIndex"].append((n, int(grh)))
                body = ley_fields.get("body")
                if typ == "NPC" and body and body.isdigit() and bodies_ours and int(body) not in bodies_ours:
                    grh_faltantes["Body"].append((n, int(body)))
            else:
                # comparar campos (texto vs balance) contra repo si esta, sino contra ley
                ref = repo.get(n, {}).get("fields") or ley_fields
                ours_f = ours[n]["fields"]
                diff_t, diff_b = [], []
                for k in set(ref) | set(ours_f):
                    if k.startswith(("en_", "pt_", "fr_", "it_")):
                        continue
                    if norm_text(ref.get(k)) != norm_text(ours_f.get(k)):
                        (diff_b if k in BALANCE_FIELDS.get(typ, set()) else diff_t).append(k)
                if diff_t:
                    corregir_texto.append((n, name, sorted(diff_t)))
                if diff_b:
                    corregir_balance.append((n, name, sorted(diff_b)))

        for n in sorted(ours_active - ley_ids):
            name = ours[n]["fields"].get("name") or ours[n]["fields"].get("nombre") or "(sin nombre)"
            marked = ours[n]["marker"] or (n in deletable_lock)
            if n in protected:
                proteger.append((n, name))
            elif marked:
                borrar.append((n, name, ours[n]["marker"] or "lockfile"))
            elif n in repo:
                adelantado.append((n, name))
            else:
                revisar.append((n, name))

        # secciones completamente comentadas (no activas) con marca: candidatas a limpieza fisica
        comentadas = [(n, s["marker"] or "(comentada)") for n, s in sorted(ours.items())
                      if s["commented"]]

        actions[typ] = {
            "migrar": [n for n, _ in migrar],
            "migrar_texto": [n for n, _ in migrar_texto],
            "corregir_texto": [n for n, _, _ in corregir_texto],
            "corregir_balance": [n for n, _, _ in corregir_balance],
            "proteger": [n for n, _ in proteger],
            "borrar": [n for n, _, _ in borrar],
            "adelantado": [n for n, _ in adelantado],
            "revisar": [n for n, _ in revisar],
            "limpieza_comentadas": [n for n, _ in comentadas],
        }

        report.append(f"## {typ}")
        report.append(f"- ley={len(ley_ids)} repo={len(repo)} nuestro_activo={len(ours_active)}")
        report.append(f"- **MIGRAR (con logica repo): {len(migrar)}** | MIGRAR_TEXTO (sin logica): "
                      f"{len(migrar_texto)} | CORREGIR texto: {len(corregir_texto)} | "
                      f"CORREGIR balance: {len(corregir_balance)}")
        report.append(f"- PROTEGER: {len(proteger)} | BORRAR: {len(borrar)} | ADELANTADO (repo>ley): "
                      f"{len(adelantado)} | REVISAR: {len(revisar)} | secciones comentadas: {len(comentadas)}")
        for label, rows, cap in [("MIGRAR", migrar, 30), ("MIGRAR_TEXTO", migrar_texto, 15),
                                 ("BORRAR", borrar, 30), ("ADELANTADO", adelantado, 15),
                                 ("REVISAR", revisar, 60), ("PROTEGER", proteger, 25)]:
            if rows:
                report.append(f"\n### {typ} · {label} ({len(rows)})")
                for row in rows[:cap]:
                    n, name = row[0], row[1]
                    extra = f" — {row[2]}" if len(row) > 2 else ""
                    report.append(f"- {typ}{n}: {name}{extra}")
                if len(rows) > cap:
                    report.append(f"- ... y {len(rows) - cap} mas (lista completa en fase2_acciones.json)")
        if corregir_balance:
            hist = defaultdict(int)
            for _, _, ks in corregir_balance:
                for k in ks:
                    hist[k] += 1
            report.append(f"\n### {typ} · CORREGIR balance — campos mas frecuentes: "
                          + ", ".join(f"{k}({v})" for k, v in sorted(hist.items(), key=lambda x: -x[1])[:10]))
        if grh_faltantes:
            for kind, rows in grh_faltantes.items():
                report.append(f"\n### {typ} · ⚠️ {kind} NO presentes en recursos cliente ({len(rows)})")
                for n, g in rows[:20]:
                    report.append(f"- {typ}{n} -> {kind}={g}")
                if len(rows) > 20:
                    report.append(f"- ... y {len(rows) - 20} mas")
        report.append("")

    # ---- mensajes y sonidos vs ley fresca ----
    report.append("## Mensajes y sonidos (re-check vs ley fresca)")
    ley_msg = parse_sections(os.path.join(LEY_INIT, "sp_localmsg.dat"), ("X",))  # solo para abrirlo
    def msg_keys(path):
        t = read_text(path, "cp1252")
        return dict(re.findall(r"(?im)^(Msg\d+)\s*=\s*([^\r\n]*)", t))
    ley_m = msg_keys(os.path.join(LEY_INIT, "sp_localmsg.dat"))
    our_m = msg_keys(os.path.join(OURS_INIT, "sp_localmsg.dat"))
    faltan_msg = sorted(set(ley_m) - set(our_m), key=lambda k: int(k[3:]))
    report.append(f"- Mensajes ley={len(ley_m)} nuestro={len(our_m)} faltantes={len(faltan_msg)}")
    for k in faltan_msg[:25]:
        report.append(f"  - {k} = {ley_m[k][:80]}")
    if len(faltan_msg) > 25:
        report.append(f"  - ... y {len(faltan_msg) - 25} mas")
    actions["MSG"] = {"migrar": faltan_msg}

    snd = {}
    for folder, ours_dirs in [("Sounds", ["Sounds"]), ("OGG", ["OGG", "SoundsOgg"])]:
        ley_files = {f.lower() for f in os.listdir(os.path.join(
            ROOT, r"dev\oficial\recursos_20260610", folder))}
        our_files = set()
        for d in ours_dirs:
            p = os.path.join(ROOT, "dev", "Recursos", d)
            if os.path.isdir(p):
                our_files |= {f.lower() for f in os.listdir(p)}
        missing = sorted(ley_files - our_files)
        snd[folder] = missing
        report.append(f"- {folder}: ley={len(ley_files)} nuestro={len(our_files)} "
                      f"**faltantes={len(missing)}**")
    actions["SOUNDS"] = snd

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")
    with open(os.path.join(OUT_DIR, "fase2_acciones.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(actions, f, ensure_ascii=False, indent=1)

    print("Reporte:", REPORT)
    for typ in DOMAINS:
        a = actions[typ]
        print(f"  {typ}: migrar={len(a['migrar'])} migrar_texto={len(a['migrar_texto'])} "
              f"corregir_txt={len(a['corregir_texto'])} corregir_bal={len(a['corregir_balance'])} "
              f"borrar={len(a['borrar'])} adelantado={len(a['adelantado'])} revisar={len(a['revisar'])}")
    print(f"  MSG faltantes={len(actions['MSG']['migrar'])} | "
          f"Sounds faltantes={len(snd['Sounds'])} OGG faltantes={len(snd['OGG'])}")


if __name__ == "__main__":
    main()
