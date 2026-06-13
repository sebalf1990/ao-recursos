# -*- coding: utf-8 -*-
"""Integra las quests cosechadas via getQuestById (plan 10.001).

Cosecha del usuario: el set oficial real es 1-373 + 380-386 (374-379 y los
huecos del repo dan 404: no existen). Integra las 7 nuevas con logica completa
y aplica los bindings pendientes (QUEST385/386).
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
HARVEST = r"c:\AO20\dev\oficial\wiki-api\quests_oficial.json"
LANG_PREF = ("en_", "pt_", "fr_", "it_")

unmappable = 0


def to_cp1252(line):
    global unmappable
    try:
        line.encode("cp1252")
        return line
    except UnicodeEncodeError:
        unmappable += 1
        return line.encode("cp1252", errors="replace").decode("cp1252")


def main():
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    npath = os.path.join(OURS_DAT, "npcs.dat")
    q = open(qpath, "rb").read().decode("cp1252")
    n = open(npath, "rb").read().decode("cp1252")
    harvest = json.load(open(HARVEST, encoding="utf-8"))["quests"]

    have = {int(x) for x in re.findall(r"(?m)^\[QUEST(\d+)\]", q)}
    new_ids = sorted(int(k) for k in harvest if int(k) not in have)
    assert new_ids, "nada nuevo para integrar"

    # casing canonico segun el set ya adoptado
    casing = Counter(re.findall(r"(?m)^(\w+)=", q))
    canon = {}
    for k, _ in casing.most_common():
        canon.setdefault(k.lower(), k)

    secs = []
    for qid in new_ids:
        it = harvest[str(qid)]
        base_fields, lang_fields = [], []
        for k, v in it.items():
            if not isinstance(v, (str, int, float)):
                continue
            ks = str(k).strip()
            if ks.upper() in ("ID",) or "INFORMATION" in ks.upper():
                continue
            vs = str(v).replace("\r", " ").replace("\n", " ").strip()
            if vs == "":
                continue
            kl = ks.lower()
            if kl.startswith(LANG_PREF):
                lang_fields.append((kl, vs))
            else:
                base_fields.append((canon.get(kl, ks.capitalize()), vs))
        base_casing = {k.lower(): k for k, _ in base_fields}
        lines = [f"[QUEST{qid}] 'Cosechada de getQuestById oficial 2026-06-12 (plan 10.001)"]
        lines += [to_cp1252(f"{k}={v}") for k, v in base_fields]
        for kl, vs in lang_fields:
            base = kl[3:]
            cb = base_casing.get(base) or canon.get(base, base.capitalize())
            lines.append(to_cp1252(f"{kl[:3]}{cb}={vs}"))
        secs.append("\r\n".join(lines) + "\r\n")

    # insertar antes del bloque de customs (QUEST900) para mantener orden
    m = re.search(r"(?m)^\[QUEST900\]", q)
    insert_at = m.start() if m else len(q)
    q = q[:insert_at] + "\r\n".join(secs) + "\r\n" + q[insert_at:]
    open(qpath, "w", encoding="cp1252", newline="").write(q)
    qb = open(qpath, "rb").read()
    assert qb.count(b"\n") == qb.count(b"\r\n"), "CRLF roto en Quests.DAT"

    # bindings pendientes
    pend = json.load(open(os.path.join(OUT_DIR, "bindings_pendientes_quests.json"),
                          encoding="utf-8"))["pendientes"]
    applied = []
    for nid, qid in pend:
        if qid not in new_ids:
            continue
        m = re.search(r"(?ms)^(\[NPC%d\][^\n]*\n)(.*?)(?=^.?\s*\[|\Z)" % nid, n)
        body = m.group(2)
        existing = [int(x) for x in re.findall(r"(?im)^QuestNumber\d*\s*=\s*(\d+)", body)]
        if qid in existing:
            continue
        allq = existing + [qid]
        body2 = re.sub(r"(?im)^(?:NumQuest|QuestNumber\d*)\s*=[^\r\n]*\r\n", "", body)
        lines = body2.split("\r\n")
        j = len(lines)
        while j > 0 and lines[j - 1].strip() == "":
            j -= 1
        add = ["NumQuest=%d" % len(allq)]
        add += ["QuestNumber%d=%d" % (i, x) for i, x in enumerate(allq, 1)]
        lines[j:j] = add
        n = n[:m.start(2)] + "\r\n".join(lines) + n[m.end(2):]
        applied.append((nid, qid))
    open(npath, "w", encoding="cp1252", newline="").write(n)
    nb = open(npath, "rb").read()
    assert nb.count(b"\n") == nb.count(b"\r\n"), "CRLF roto en npcs.dat"

    # validacion de refs de las nuevas
    obj_ids = {int(x) for x in re.findall(
        r"(?m)^\[OBJ(\d+)\]",
        open(os.path.join(OURS_DAT, "obj.dat"), "rb").read().decode("cp1252"))}
    bad = []
    final_q = open(qpath, "rb").read().decode("cp1252")
    for qid in new_ids:
        m = re.search(r"(?ms)^\[QUEST%d\][^\n]*\n(.*?)(?=^\[|\Z)" % qid, final_q)
        for mm in re.finditer(r"(?im)^((?:Required|Reward)Obj\d+)\s*=\s*(\d+)", m.group(1)):
            if int(mm.group(2)) and int(mm.group(2)) not in obj_ids:
                bad.append((qid, mm.group(1), mm.group(2)))

    print(f"quests integradas: {new_ids} | no mapeables cp1252: {unmappable}")
    print(f"bindings aplicados: {applied}")
    print(f"refs rotas en las nuevas: {bad if bad else 'ninguna'}")
    for qid in new_ids[:3]:
        m = re.search(r"(?ms)^\[QUEST%d\][^\n]*\n(.*?)(?=^\[|\Z)" % qid, final_q)
        nm = re.search(r"(?im)^Nombre=([^\r\n]+)", m.group(1))
        print(f"  QUEST{qid}: {nm.group(1).strip() if nm else '?'}")


if __name__ == "__main__":
    main()
