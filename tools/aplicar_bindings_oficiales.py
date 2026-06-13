# -*- coding: utf-8 -*-
"""Aplica los bindings de quest OFICIALES cosechados via getNpcById (plan 10.001).

Fuente: dev/oficial/wiki-api/npcs_quests_oficial.json (cosecha del usuario via
snippet de consola; endpoint descubierto: /api/public/dats/getNpcById/<id>).

1. Reubica nuestras quests custom 374/375 -> 900/901: el set oficial ya llega a
   la QUEST386 (mas alla de la ley 8/6) y pisaria 374/375. NPC21 Bromdir
   conserva las customs ADEMAS de sus oficiales.
2. Para cada NPC cosechado: NumQuest/QuestNumber* = lo oficial (incluye vaciar
   si el oficial dice 0). DropQuest* NO se toca (el endpoint no lo expone).
   Bindings a quests que NO tenemos (374-386+, huecos del repo) se omiten y
   quedan en lista pendiente hasta cosechar getQuestById.
3. Los 404 (NPCs sin version oficial) conservan sus bindings actuales.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
HARVEST = r"c:\AO20\dev\oficial\wiki-api\npcs_quests_oficial.json"
RELOC_Q = {374: 900, 375: 901}
BROMDIR = 21
QKEY_GIVER = re.compile(r"(?i)^(QuestNumber\d*|NumQuest)$")


def main():
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    npath = os.path.join(OURS_DAT, "npcs.dat")
    q = open(qpath, "rb").read().decode("cp1252")
    n = open(npath, "rb").read().decode("cp1252")
    harvest = json.load(open(HARVEST, encoding="utf-8"))["npcs"]

    # --- 1) reubicar customs 374/375 -> 900/901 ---
    for old, new in sorted(RELOC_Q.items()):
        m = re.search(r"(?m)^\[QUEST%d\]([^\r\n]*)" % old, q)
        assert m and ("custom" in m.group(1).lower() or "Reubicada" in m.group(1)), \
            f"QUEST{old} no parece nuestra custom: {m.group(1) if m else 'NO ESTA'}"
        # [^\r\n]* preserva el \r\n del final de linea (leccion fix 1)
        q = re.sub(r"(?m)^\[QUEST%d\][^\r\n]*" % old,
                   "[QUEST%d] 'Custom nuestra; movida de %d (el set oficial ya usa 374+)" % (new, old),
                   q, count=1)
    for old, new in RELOC_Q.items():
        q = re.sub(r"(?im)^(NextQuest\s*=\s*)%d\b" % old, r"\g<1>%d" % new, q)
    assert "NumQuests=375\r\n" in q
    q = q.replace("NumQuests=375\r\n", "NumQuests=901\r\n", 1)
    open(qpath, "w", encoding="cp1252", newline="").write(q)
    qb = open(qpath, "rb").read()
    assert qb.count(b"\n") == qb.count(b"\r\n"), "CRLF roto en Quests.DAT"

    our_quests = {int(x) for x in re.findall(r"(?m)^\[QUEST(\d+)\]", q)}

    # --- 2) bindings oficiales ---
    blocks, cur = [], []
    for ln in n.split("\r\n"):
        if re.match(r"^\s*'*\s*\[NPC\d+\]", ln):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)

    applied = emptied = 0
    pending = []  # (npc, quest) bindings a quests que no tenemos
    for bi, blk in enumerate(blocks):
        if not blk:
            continue
        m = re.match(r"^\s*('*)\s*\[NPC(\d+)\]", blk[0])
        if not m or m.group(1):
            continue
        bid = int(m.group(2))
        if str(bid) not in harvest:
            # sin version oficial: solo seguir la reubicacion de customs
            for li, ln in enumerate(blk):
                mm = re.match(r"(?i)^(QuestNumber\d*\s*=\s*)(\d+)\s*$", ln.strip())
                if mm and int(mm.group(2)) in RELOC_Q:
                    blk[li] = f"{mm.group(1)}{RELOC_Q[int(mm.group(2))]}"
            continue
        v = harvest[str(bid)]
        official = []
        for i in range(1, int(v.get("NUMQUEST", 0) or 0) + 1):
            x = v.get("QUESTNUMBER%d" % i)
            if not x:
                continue
            x = int(x)
            if x in our_quests:
                official.append(x)
            else:
                pending.append((bid, x))
        if bid == BROMDIR:
            official += sorted(RELOC_Q.values())
        new_blk = [l for l in blk
                   if not (("=" in l and not l.strip().startswith("'"))
                           and QKEY_GIVER.match(l.split("=", 1)[0].strip()))]
        if official:
            j = len(new_blk)
            while j > 0 and new_blk[j - 1].strip() == "":
                j -= 1
            add = ["NumQuest=%d" % len(official)]
            add += ["QuestNumber%d=%d" % (i, x) for i, x in enumerate(official, 1)]
            new_blk[j:j] = add
            applied += 1
        else:
            emptied += 1
        blocks[bi] = new_blk

    n_out = "\r\n".join("\r\n".join(b) for b in blocks)
    open(npath, "w", encoding="cp1252", newline="").write(n_out)
    nb = open(npath, "rb").read()
    assert nb.count(b"\n") == nb.count(b"\r\n"), "CRLF roto en npcs.dat"

    # --- lockfile ---
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    qs = set(lock["protected"].get("QUEST", []))
    lock["protected"]["QUEST"] = sorted((qs - set(RELOC_Q)) | set(RELOC_Q.values()))
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # --- validaciones / reporte ---
    final_n = open(npath, "rb").read().decode("cp1252")
    givers = {int(x) for x in re.findall(r"(?im)^QuestNumber\d*\s*=\s*(\d+)", final_n)}
    chained = {int(x) for x in re.findall(r"(?im)^NextQuest\s*=\s*(\d+)", q)}
    orphans = sorted(our_quests - givers - chained)
    print(f"NPCs con bindings oficiales aplicados: {applied} | vaciados (oficial=0): {emptied}")
    print(f"bindings pendientes (quests que no tenemos): {len(pending)} -> "
          f"{sorted(set(x for _, x in pending))}")
    print(f"customs movidas: {RELOC_Q} | huerfanas AHORA: {len(orphans)} "
          f"(antes 202)")
    pend_path = os.path.join(OUT_DIR, "bindings_pendientes_quests.json")
    with open(pend_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"pendientes": pending,
                   "nota": "aplicar al cosechar getQuestById de estas quests"}, f, indent=1)
    for nid, want in ((20, "319"), (1114, "37"), (1339, "285"), (21, None), (698, "108")):
        m = re.search(r"(?ms)^\[NPC%d\][^\n]*\n(.*?)(?=^.?\s*\[|\Z)" % nid, final_n)
        qs_ = re.findall(r"(?im)^QuestNumber\d*=(\d+)", m.group(1))
        print(f"  NPC{nid} quests: {qs_}" + (f" ({'OK' if want in qs_ else 'MAL'})" if want else ""))


if __name__ == "__main__":
    main()
