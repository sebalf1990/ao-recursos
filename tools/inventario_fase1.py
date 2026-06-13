# -*- coding: utf-8 -*-
"""Fase 1 del plan 10.001: inventario del contenido propio + marcadores de borrado.

Solo lectura. Cruza nuestro contenido (dev/Recursos) contra la LEY FRESCA
(extracción Steam 2026-06-08 en dev/oficial/recursos_20260610) y clasifica cada
entrada "solo nuestra" en PROTEGIDO / BORRABLE / REVISAR.

Fuentes:
  - Cliente (texto):   dev/Recursos/init/sp_localindex.dat
  - Ley fresca:        dev/oficial/recursos_20260610/init/sp_localindex.dat
  - Server (lógica):   dev/Recursos/Dat/{npcs.dat, obj.dat, Quests.DAT, Hechizos.dat}

Marcadores de borrado (criterio del usuario):
  (a) sección ACTIVA con comentario tipo "borrar/eliminar proxima temporada/parche"
      en la línea del header:  [NPC30] 'Borrar proximo parche
  (b) sección COMPLETAMENTE COMENTADA:  '[NPC723]'Borrar proxima temporada
"""
import os
import re
import json

ROOT = r"c:\AO20"
OURS_INIT = os.path.join(ROOT, r"dev\Recursos\init\sp_localindex.dat")
LAW_INIT = os.path.join(ROOT, r"dev\oficial\recursos_20260610\init\sp_localindex.dat")
LAW_BIG = os.path.join(ROOT, r"dev\oficial\recursos_20260610\init\localindex.dat")
DAT_DIR = os.path.join(ROOT, r"dev\Recursos\Dat")
OUT_DIR = os.path.join(ROOT, r"ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs")

# Contenido protegido conocido (rangos + features propias)
PROTECTED_RANGES = {
    "NPC": [(1405, 1411)],            # maestros de profesión
    "OBJ": [(4997, 5010)],            # manuales + pociones de olvido (profesiones)
}
# Hechizos del sistema de venenos nuevo (feature propia). Se valida abajo
# que NO existan en la ley; el rango se confirma por diff, no se asume ciego.
POISON_SPELL_HINT = range(295, 308)

DELETE_RE = re.compile(r"\b(borrar|eliminar)\b", re.IGNORECASE)
HEADER_RE = re.compile(r"^\s*('*)\s*\[([A-Z_]+?)(\d+)\]\s*(.*)$")


def read_lines(path):
    with open(path, encoding="cp1252", errors="replace", newline="") as f:
        return [ln.rstrip("\r\n") for ln in f]


def parse_sections(path, types):
    """Devuelve dict type -> {id: {'commented': bool, 'marker': str|None, 'name': str}}."""
    result = {t: {} for t in types}
    cur = None
    for ln in read_lines(path):
        m = HEADER_RE.match(ln)
        if m:
            quote, typ, num, rest = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            if typ in types:
                commented = bool(quote) or ln.lstrip().startswith("'")
                marker = rest.strip() if DELETE_RE.search(rest) else None
                # marcador también puede venir tras un apóstrofe extra en rest
                result[typ][num] = {"commented": commented, "marker": marker,
                                    "name": None, "header": ln.strip()}
                cur = (typ, num)
            else:
                cur = None
            continue
        if cur and "=" in ln:
            key, _, val = ln.partition("=")
            k = key.strip().lower().lstrip("'")
            if k in ("name", "nombre") and result[cur[0]][cur[1]]["name"] is None:
                result[cur[0]][cur[1]]["name"] = val.strip()
    return result


def in_ranges(typ, num):
    for lo, hi in PROTECTED_RANGES.get(typ, []):
        if lo <= num <= hi:
            return True
    return False


def law_section_ids(path, typ):
    """IDs de secciones [TYPEnnn] en un archivo (case-insensitive en el tipo)."""
    ids = set()
    with open(path, encoding="cp1252", errors="replace") as f:
        for ln in f:
            m = re.match(r"^\s*\[" + typ + r"(\d+)\]", ln, re.IGNORECASE)
            if m:
                ids.add(int(m.group(1)))
    return ids


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    types = ("QUEST", "NPC", "OBJ", "HECHIZO")

    ours = parse_sections(OURS_INIT, types)
    law = parse_sections(LAW_INIT, types)
    # "Oficial" = unión de ambos índices de la ley (sp_localindex + localindex.dat):
    # tienen cobertura distinta (NPCs de combate sin texto viven solo en el grande).
    law_union = {}
    for typ in types:
        law_union[typ] = (law_section_ids(LAW_INIT, typ)
                          | law_section_ids(LAW_BIG, typ))

    # Marcadores de borrado en los Dat server (donde viven los comentarios)
    dat_files = {
        "NPC": os.path.join(DAT_DIR, "npcs.dat"),
        "OBJ": os.path.join(DAT_DIR, "obj.dat"),
        "HECHIZO": os.path.join(DAT_DIR, "Hechizos.dat"),
        "QUEST": os.path.join(DAT_DIR, "Quests.DAT"),
    }
    dat_sections = {}
    for typ, p in dat_files.items():
        if os.path.exists(p):
            dat_sections[typ] = parse_sections(p, (typ,))[typ]
        else:
            dat_sections[typ] = {}

    report = ["# Fase 1 — Inventario del contenido propio y marcadores de borrado",
              "",
              "Ley fresca: Steam 2026-06-08 (`dev/oficial/recursos_20260610`).",
              "Solo lectura. Clasificación preliminar — requiere OK del usuario.",
              ""]
    lock = {"protected": {}, "deletable": {}, "review": {}}

    for typ in types:
        law_ids = law_union[typ]
        ours_ids = set(ours[typ])
        only_ours = sorted(ours_ids - law_ids)

        protected, deletable, review, collision = [], [], [], []
        for num in only_ours:
            info = ours[typ][num]
            dat_info = dat_sections.get(typ, {}).get(num, {})
            is_marked = bool(info["marker"]) or bool(dat_info.get("marker")) \
                or info["commented"] or dat_info.get("commented", False)
            marker_txt = info["marker"] or dat_info.get("marker") or \
                ("(sección comentada)" if (info["commented"] or dat_info.get("commented")) else "")
            name = info["name"] or dat_info.get("name") or "(sin nombre)"

            if in_ranges(typ, num):
                protected.append((num, name, "rango privado reservado"))
            elif typ == "HECHIZO" and num in POISON_SPELL_HINT:
                protected.append((num, name, "candidato feature venenos"))
            elif is_marked:
                deletable.append((num, name, marker_txt))
            else:
                review.append((num, name, ""))

        # COLISIÓN: IDs en rango privado que la ley AHORA también ocupa con otra cosa.
        for lo, hi in PROTECTED_RANGES.get(typ, []):
            for num in range(lo, hi + 1):
                if num in law_ids and num in ours_ids:
                    ours_name = ours[typ][num].get("name") or "?"
                    collision.append((num, ours_name, "ocupado por la ley oficial"))

        # marcados para borrar que SÍ existen en la ley (ya oficiales -> quizá ya no borrar)
        marked_in_law = []
        for num in sorted(ours_ids & law_ids):
            info = ours[typ][num]
            dat_info = dat_sections.get(typ, {}).get(num, {})
            if info["marker"] or dat_info.get("marker") or info["commented"] or dat_info.get("commented"):
                marked_in_law.append((num, info["name"] or dat_info.get("name") or "?",
                                      info["marker"] or dat_info.get("marker") or "(comentada)"))

        report.append(f"## {typ}")
        report.append(f"- Ley fresca (unión sp+big): {len(law_ids)} | Nuestro: {len(ours_ids)} | "
                      f"Solo nuestro: {len(only_ours)}")
        report.append(f"- PROTEGIDO: {len(protected)} | COLISIÓN: {len(collision)} | "
                      f"BORRABLE (marcado): {len(deletable)} | "
                      f"REVISAR (solo nuestro sin marca): {len(review)} | "
                      f"Marcado pero ya en ley: {len(marked_in_law)}")
        for label, rows in [("PROTEGIDO", protected), ("COLISIÓN", collision),
                            ("BORRABLE", deletable),
                            ("REVISAR", review), ("MARCADO-PERO-YA-EN-LEY", marked_in_law)]:
            if not rows:
                continue
            report.append(f"\n### {typ} · {label} ({len(rows)})")
            for num, name, note in rows[:200]:
                suffix = f" — {note}" if note else ""
                report.append(f"- {typ}{num}: {name}{suffix}")
            if len(rows) > 200:
                report.append(f"- ... y {len(rows) - 200} más")
        report.append("")

        lock["protected"][typ] = [n for n, _, _ in protected]
        lock["deletable"][typ] = [n for n, _, _ in deletable]
        lock["review"][typ] = [n for n, _, _ in review]
        lock.setdefault("collision", {})[typ] = [n for n, _, _ in collision]

    with open(os.path.join(OUT_DIR, "fase1_inventario.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")
    with open(os.path.join(OUT_DIR, "protected.lock.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=2)

    print("Inventario:", os.path.join(OUT_DIR, "fase1_inventario.md"))
    for typ in types:
        print(f"  {typ}: protegido={len(lock['protected'][typ])} "
              f"colision={len(lock['collision'][typ])} "
              f"borrable={len(lock['deletable'][typ])} revisar={len(lock['review'][typ])}")


if __name__ == "__main__":
    main()
