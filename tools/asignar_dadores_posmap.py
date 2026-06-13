# -*- coding: utf-8 -*-
"""Asignacion de dadores de quest por PosMap (plan 10.001, post batch QUESTS).

Los dadores de las quests nuevas no son publicos (repo npcs viejo, wiki TALKTO
casi vacio). Heuristica con datos reales:
  - PosMap de la quest = mapa donde vive
  - .csm = posiciones de NPCs por mapa
  - candidato = NPC tipo quest SIN quests spawneado en ese mapa

Fase A (siempre): valida la semantica de PosMap contra dadores CONOCIDOS.
Fase B: --report  -> reporte de curaduria (no escribe nada)
        --apply   -> aplica solo las asignaciones INEQUIVOCAS (1 candidato);
                     las ambiguas quedan en el reporte para curaduria manual.
"""
import os
import re
import struct
import sys

DAT = r"c:\AO20\dev\Recursos\Dat"
MAPAS = r"c:\AO20\dev\Recursos\Mapas"
OUT = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"


def parse_csm_npcs(path):
    b = open(path, "rb").read()
    o = 0

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", b, o)[0]
        o += 4
        return v

    def i16():
        nonlocal o
        v = struct.unpack_from("<h", b, o)[0]
        o += 2
        return v

    def u8():
        nonlocal o
        v = b[o]
        o += 1
        return v

    def s():
        nonlocal o
        ln = struct.unpack_from("<H", b, o)[0]
        o += 2 + ln

    h = [i32() for _ in range(11)]  # blocked,l1,l2,l3,l4,triggers,lights,particles,npcs,objects,tileExits
    blocked, l1, l2, l3, l4, triggers, lights, particles, npcs, objects, _exits = h
    o += 8  # size: 4 x i16
    s(); o += 1; s(); o += 8; o += 1; s(); s(); s(); o += 16; s(); o += 3  # mapDat
    o += blocked * 6
    o += (l1 + l2 + l3 + l4) * 8
    o += triggers * 6
    o += particles * 8
    o += lights * 10
    o += objects * 8
    out = []
    for _ in range(npcs):
        x, y, idx = i16(), i16(), i16()
        out.append((idx, x, y))
    return out


def main():
    apply_mode = "--apply" in sys.argv

    # mapas -> npcs spawneados
    spawn = {}  # npc_id -> set(map)
    map_npcs = {}  # map -> [(id,x,y)]
    for f in os.listdir(MAPAS):
        m = re.match(r"(?i)^mapa(\d+)\.csm$", f)
        if not m:
            continue
        mid = int(m.group(1))
        try:
            lst = parse_csm_npcs(os.path.join(MAPAS, f))
        except Exception as e:
            print(f"AVISO mapa{mid}: {e}")
            continue
        map_npcs[mid] = lst
        for idx, x, y in lst:
            spawn.setdefault(idx, set()).add(mid)
    print(f"mapas parseados: {len(map_npcs)} | NPCs spawneados distintos: {len(spawn)}")

    q = open(os.path.join(DAT, "Quests.DAT"), "rb").read().decode("cp1252")
    n = open(os.path.join(DAT, "npcs.dat"), "rb").read().decode("cp1252")

    qsecs, qname, qpos = {}, {}, {}
    for m in re.finditer(r"(?ms)^\[QUEST(\d+)\][^\n]*\n(.*?)(?=^\[|\Z)", q):
        qid = int(m.group(1))
        qsecs[qid] = m.group(2)
        g = re.search(r"(?im)^Nombre=([^\r\n]+)", m.group(2))
        qname[qid] = g.group(1).strip() if g else "?"
        p = re.search(r"(?im)^PosMap=(\d+)", m.group(2))
        if p:
            qpos[qid] = int(p.group(1))

    npc_name, npc_type, npc_quests = {}, {}, {}
    for m in re.finditer(r"(?ms)^\[NPC(\d+)\][^\n]*\n(.*?)(?=^'?\s*\[|\Z)", n):
        nid = int(m.group(1))
        body = m.group(2)
        g = re.search(r"(?im)^Name=([^\r\n]+)", body)
        npc_name[nid] = g.group(1).strip() if g else "?"
        t = re.search(r"(?im)^NpcType=(\d+)", body)
        npc_type[nid] = int(t.group(1)) if t else 0
        npc_quests[nid] = [int(x) for x in re.findall(r"(?im)^QuestNumber\d*\s*=\s*(\d+)", body)]

    givers = {qid for qs in npc_quests.values() for qid in qs}
    chained = {int(x) for x in re.findall(r"(?im)^NextQuest\s*=\s*(\d+)", q)}
    orphans = sorted(set(qsecs) - givers - chained)

    # --- Fase A: validar semantica de PosMap con dadores conocidos ---
    ok = bad = 0
    for nid, qs in npc_quests.items():
        for qid in qs:
            if qid in qpos and nid in spawn:
                if qpos[qid] in spawn[nid]:
                    ok += 1
                else:
                    bad += 1
    total = ok + bad
    print(f"validacion PosMap==mapa del dador (casos conocidos): {ok}/{total} "
          f"({100.0 * ok / total:.0f}%)" if total else "sin casos para validar")

    # --- Fase B: candidatos por mapa ---
    questless = [nid for nid in npc_name
                 if (npc_type.get(nid) == 17 or "<quest>" in npc_name[nid].lower())
                 and not npc_quests.get(nid)]
    print(f"NPCs de quest sin quests: {len(questless)} | huerfanas: {len(orphans)} "
          f"(con PosMap: {len([o_ for o_ in orphans if o_ in qpos])})")

    auto, ambiguous, nomatch = [], [], []
    by_map = {}
    for qid in orphans:
        if qid in qpos:
            by_map.setdefault(qpos[qid], []).append(qid)
    for mid, qids in sorted(by_map.items()):
        cands = sorted({nid for nid, _, _ in map_npcs.get(mid, []) if nid in questless})
        if len(cands) == 1:
            auto.append((mid, qids, cands[0]))
        elif cands:
            ambiguous.append((mid, qids, cands))
        else:
            nomatch.append((mid, qids))

    rep = [f"# Curaduria de dadores por PosMap — {len(orphans)} huerfanas",
           f"# Validacion semantica PosMap: {ok}/{total} dadores conocidos en su mapa",
           ""]
    rep.append(f"## AUTO (1 candidato): {sum(len(q_) for _, q_, _ in auto)} quests")
    for mid, qids, nid in auto:
        for qid in qids:
            rep.append(f"mapa{mid}: QUEST{qid} ({qname[qid]}) -> NPC{nid} ({npc_name[nid]})")
    rep.append("")
    rep.append(f"## AMBIGUOS (elegir a mano): {sum(len(q_) for _, q_, _ in ambiguous)} quests")
    for mid, qids, cands in ambiguous:
        rep.append(f"mapa{mid}: quests {[(q_, qname[q_]) for q_ in qids]}")
        rep.append(f"   candidatos: {[(c, npc_name[c]) for c in cands]}")
    rep.append("")
    rep.append(f"## SIN CANDIDATO en el mapa: {sum(len(q_) for _, q_ in nomatch)} quests")
    for mid, qids in nomatch:
        rep.append(f"mapa{mid}: {[(q_, qname[q_]) for q_ in qids]}")
    rep.append("")
    rep.append(f"## Huerfanas SIN PosMap: {len([o_ for o_ in orphans if o_ not in qpos])}")
    rep_path = os.path.join(OUT, "curaduria_dadores_posmap.md")
    with open(rep_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rep) + "\n")
    print(f"reporte: {rep_path}")
    print(f"auto: {sum(len(q_) for _, q_, _ in auto)} | ambiguas: "
          f"{sum(len(q_) for _, q_, _ in ambiguous)} | sin candidato: "
          f"{sum(len(q_) for _, q_ in nomatch)}")

    if not apply_mode:
        print("(modo reporte; usar --apply para aplicar las AUTO)")
        return

    # aplicar AUTO: agregar QuestNumber al NPC
    npath = os.path.join(DAT, "npcs.dat")
    text = open(npath, "rb").read().decode("cp1252")
    applied = 0
    per_npc = {}
    for mid, qids, nid in auto:
        per_npc.setdefault(nid, []).extend(qids)
    for nid, qids in sorted(per_npc.items()):
        m = re.search(r"(?ms)^(\[NPC%d\][^\n]*\n)(.*?)(?=^.?\s*\[|\Z)" % nid, text)
        body = m.group(2)
        existing = [int(x) for x in re.findall(r"(?im)^QuestNumber\d*\s*=\s*(\d+)", body)]
        allq = existing + [q_ for q_ in sorted(set(qids)) if q_ not in existing]
        body2 = re.sub(r"(?im)^(?:NumQuest|QuestNumber\d*)\s*=[^\r\n]*\r\n", "", body)
        lines = body2.split("\r\n")
        j = len(lines)
        while j > 0 and lines[j - 1].strip() == "":
            j -= 1
        add = ["NumQuest=%d" % len(allq)] + ["QuestNumber%d=%d" % (i, q_)
                                            for i, q_ in enumerate(allq, 1)]
        add[0] += "  'Dadores asignados por PosMap (plan 10.001)"
        lines[j:j] = add
        text = text[:m.start(2)] + "\r\n".join(lines) + text[m.end(2):]
        applied += len(qids)
    open(npath, "w", encoding="cp1252", newline="").write(text)
    b = open(npath, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto"
    print(f"aplicadas {applied} asignaciones AUTO en {len(per_npc)} NPCs")


if __name__ == "__main__":
    main()
