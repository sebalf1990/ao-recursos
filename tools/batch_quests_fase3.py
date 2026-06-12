# -*- coding: utf-8 -*-
"""Fase 3 batch QUESTS (plan 10.001) — ultimo dominio.

Estrategia (fase 2, validada en pre-flight: repo FRESCO para quests, 0 nombres
difieren de la ley en 317 compartidas):

1. ADOPTAR el Quests.DAT del repo como base (1-353, logica server completa,
   transcode a cp1252).
2. QUESTS 354-373 construidas desde la wiki API (getAllQuestsInformation:
   logica completa, 5 idiomas, audios).
3. Nuestras customs 259 "Cenizas del Primer Fuego" y 260 "Las Alas del Fuego
   Eterno" se REUBICAN a 374/375 (decision usuario: conservar customs); sus
   refs a items ya apuntan a los fenix protegidos 9015-9017. NextQuest interno
   se remapea 259->374 / 260->375.
4. DADORES: los QuestNumber*/NumQuest/DropQuest*/NumDropQuest de npcs.dat se
   adoptan del npcs.dat del REPO (mapping coherente con su set de quests).
   NPCs sin seccion (con campos) en el repo conservan los nuestros. Al NPC21
   (dador de las customs) se le agregan QuestNumber para 374/375.

Leccion aplicada: las claves server que la fuente no publica JAMAS se pierden
(aca la fuente ES server-side, asi que se adopta entera).
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diff_fase2 import detect_decode, REPO_DAT, OURS_DAT

OUT_DIR = r"c:\AO20\ia\work\2026\junio\10.001.sync-repoblacion-contenido-oficial-v2\outputs"
WIKI = r"c:\AO20\dev\oficial\wiki-api"
RELOC = {259: 374, 260: 375}
GIVER_CUSTOM = 21  # NPC dador de las quests custom
QKEY = re.compile(r"(?i)^((?:QuestNumber|DropQuest)\d*|NumQuest|NumDropQuest)$")
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


def secs_raw(txt, typ):
    out = {}
    for m in re.finditer(r"(?ms)^\[%s(\d+)\][^\n]*\n(.*?)(?=^'?\s*\[|\Z)" % typ, txt):
        out[int(m.group(1))] = m.group(0)
    return out


def main():
    qpath = os.path.join(OURS_DAT, "Quests.DAT")
    npath = os.path.join(OURS_DAT, "npcs.dat")
    ours_q = open(qpath, "rb").read().decode("cp1252")
    repo_q = detect_decode(os.path.join(REPO_DAT, "Quests.DAT")).replace("\r\n", "\n")
    repo_n = detect_decode(os.path.join(REPO_DAT, "npcs.dat")).replace("\r\n", "\n")

    # --- 1) base repo 1-353 ---
    repo_secs = secs_raw(repo_q, "QUEST")
    out = ["[INIT]", "NumQuests=375", ""]
    for n in sorted(repo_secs):
        lines = [to_cp1252(l) for l in repo_secs[n].rstrip("\n").split("\n")]
        out.extend(lines + [""])

    # casing canonico de claves segun el repo (para las secciones wiki)
    casing = Counter()
    for body in repo_secs.values():
        for m in re.finditer(r"(?m)^(\w+)=", body):
            casing[m.group(1)] += 1
    canon = {}
    for k, _ in casing.most_common():
        canon.setdefault(k.lower(), k)

    # --- 2) 354-373 desde la wiki ---
    wq = json.load(open(os.path.join(WIKI, "getAllQuestsInformation.json"), encoding="utf-8"))
    wiki = {int(it["ID"]): it for it in wq if isinstance(it, dict) and it.get("ID")}
    n_wiki = 0
    for n in range(354, 374):
        it = wiki.get(n)
        if not it:
            print(f"AVISO: wiki no tiene QUEST{n}")
            continue
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
        lines = [f"[QUEST{n}] 'Construida desde la wiki API oficial (repo capado; plan 10.001)"]
        lines += [to_cp1252(f"{k}={v}") for k, v in base_fields]
        for kl, vs in lang_fields:
            base = kl[3:]
            cb = base_casing.get(base) or canon.get(base, base.capitalize())
            lines.append(to_cp1252(f"{kl[:3]}{cb}={vs}"))
        out.extend(lines + [""])
        n_wiki += 1

    # --- 3) customs reubicadas ---
    # NOTA reejecucion: leer SIEMPRE de un Quests.DAT que aun tenga las customs
    # en 259/260 (el backup pre-batch); el archivo vigente ya puede tener las
    # oficiales Jinete en esos ids.
    bkp_q = r"c:\AO20\backups\2026-06-11.fase3-batch-quests\Quests.DAT"
    src_q = open(bkp_q, "rb").read().decode("cp1252") if os.path.exists(bkp_q) else ours_q
    ours_secs = secs_raw(src_q, "QUEST")
    for old, new in sorted(RELOC.items()):
        sec = ours_secs[old].rstrip("\n").split("\n")
        sec[0] = (f"[QUEST{new}] 'Reubicada de QUEST{old} por colision con quest oficial; "
                  f"custom nuestra (plan 10.001 fase 3)")
        body = "\n".join(sec)
        for o2, n2 in RELOC.items():
            body = re.sub(r"(?im)^(NextQuest\s*=\s*)%d\b" % o2, r"\g<1>%d" % n2, body)
        out.extend(body.split("\n") + [""])

    result = "\r\n".join(out)
    open(qpath, "w", encoding="cp1252", newline="").write(result)
    b = open(qpath, "rb").read()
    assert b.count(b"\n") == b.count(b"\r\n"), "CRLF roto en Quests.DAT"

    # --- 4) dadores desde el repo ---
    ours_n_raw = open(npath, "rb").read().decode("cp1252")
    repo_bind = {}
    for n, sec in secs_raw(repo_n, "NPC").items():
        ks = [(m.group(1), m.group(2).strip()) for m in
              re.finditer(r"(?m)^(\w+)=([^\n]*)", sec) if QKEY.match(m.group(1))]
        has_fields = bool(re.search(r"(?m)^\w+=", "\n".join(sec.split("\n")[1:])))
        if has_fields:
            repo_bind[n] = ks  # puede ser [] = el repo dice "sin quests"

    blocks = []
    cur = []
    for ln in ours_n_raw.split("\r\n"):
        if re.match(r"^\s*'*\s*\[NPC\d+\]", ln):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)

    n_replaced = n_kept = 0
    for bi, blk in enumerate(blocks):
        if not blk:
            continue
        m = re.match(r"^\s*('*)\s*\[NPC(\d+)\]", blk[0])
        if not m or m.group(1):
            continue
        bid = int(m.group(2))
        if bid not in repo_bind:
            # conserva bindings nuestros, pero siguiendo a las quests reubicadas
            # (NPC21 Bromdir daba las customs 259/260 -> ahora 374/375)
            for li, ln in enumerate(blk):
                mm = re.match(r"(?i)^(QuestNumber\d*\s*=\s*)(\d+)\s*$", ln.strip())
                if mm and int(mm.group(2)) in RELOC:
                    blk[li] = f"{mm.group(1)}{RELOC[int(mm.group(2))]}"
            n_kept += 1
            continue
        new_blk = [l for l in blk if not (QKEY.match(l.split("=", 1)[0].strip())
                                          if "=" in l and not l.strip().startswith("'") else False)]
        binds = list(repo_bind[bid])
        if bid == GIVER_CUSTOM:
            qn = [v for k, v in binds if k.lower().startswith("questnumber")]
            binds = [(k, v) for k, v in binds if k.lower() not in ("numquest",)]
            extra = [str(RELOC[o]) for o in sorted(RELOC)]
            allq = qn + extra
            binds = [(k, v) for k, v in binds if not k.lower().startswith("questnumber")]
            binds.append(("NumQuest", str(len(allq))))
            binds += [(f"QuestNumber{i}", q) for i, q in enumerate(allq, 1)]
        if binds:
            j = len(new_blk)
            while j > 0 and new_blk[j - 1].strip() == "":
                j -= 1
            new_blk[j:j] = [f"{k}={v}" for k, v in binds]
        blocks[bi] = new_blk
        n_replaced += 1

    open(npath, "w", encoding="cp1252", newline="").write(
        "\r\n".join("\r\n".join(b) for b in blocks))
    nb = open(npath, "rb").read()
    assert nb.count(b"\n") == nb.count(b"\r\n"), "CRLF roto en npcs.dat"

    # --- lockfile ---
    lock_path = os.path.join(OUT_DIR, "protected.lock.json")
    lock = json.load(open(lock_path, encoding="utf-8"))
    qs = set(lock["protected"].get("QUEST", []))
    lock["protected"]["QUEST"] = sorted(qs | set(RELOC.values()))
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)

    # --- validaciones ---
    final_q = open(qpath, "rb").read().decode("cp1252")
    final_n = open(npath, "rb").read().decode("cp1252")
    qsecs = secs_raw(final_q, "QUEST")
    obj_ids = {int(x) for x in re.findall(
        r"(?m)^\[OBJ(\d+)\]",
        open(os.path.join(OURS_DAT, "obj.dat"), "rb").read().decode("cp1252"))}
    npc_ids = {int(x) for x in re.findall(r"(?m)^\[NPC(\d+)\]", final_n)}
    bad_refs = []
    for n, sec in qsecs.items():
        for m in re.finditer(r"(?im)^((?:Required|Reward)Obj\d+)\s*=\s*(\d+)", sec):
            if int(m.group(2)) and int(m.group(2)) not in obj_ids:
                bad_refs.append((n, m.group(1), m.group(2)))
        for m in re.finditer(r"(?im)^(RequiredNPC\d+)\s*=\s*(\d+)", sec):
            if int(m.group(2)) and int(m.group(2)) not in npc_ids:
                bad_refs.append((n, m.group(1), m.group(2)))
    givers = set()
    for m in re.finditer(r"(?im)^QuestNumber\d*\s*=\s*(\d+)", final_n):
        givers.add(int(m.group(1)))
    chained = {int(m.group(1)) for m in re.finditer(r"(?im)^NextQuest\s*=\s*(\d+)", final_q)}
    orphans = sorted(set(qsecs) - givers - chained)
    # customs nuestras perdidas (nombre que no existe en el set adoptado)
    def names(txt):
        return {norm_(m.group(2)) for m in re.finditer(
            r"(?ms)^\[QUEST(\d+)\][^\n]*\n[^\[]*?^(?:Nombre|Name)=([^\r\n]+)", txt, re.M)}
    def norm_(s):
        return re.sub(r"\s+", " ", s.strip().lower())
    old_names = {}
    for n, sec in secs_raw(ours_q, "QUEST").items():
        g = re.search(r"(?im)^(?:Nombre|Name)=([^\r\n]+)", sec)
        if g:
            old_names[n] = g.group(1).strip()
    new_names = names(final_q)
    lost = [(n, nm) for n, nm in sorted(old_names.items())
            if norm_(nm) not in new_names and n not in RELOC]

    print(f"quests adoptadas del repo: {len(repo_secs)} | wiki: {n_wiki} | "
          f"customs reubicadas: {[(o, RELOC[o]) for o in RELOC]}")
    print(f"secciones finales: {len(qsecs)} (esperado 375) | no mapeables cp1252: {unmappable}")
    print(f"dadores: NPCs con bindings del repo: {n_replaced} | sin seccion repo (conservan): {n_kept}")
    print(f"refs rotas en quests finales: {len(bad_refs)} -> {bad_refs[:10]}")
    print(f"quests sin dador ni cadena: {len(orphans)} -> {orphans[:30]}")
    print(f"nombres de quests nuestras SIN equivalente en el set nuevo: {len(lost)}")
    for n, nm in lost[:15]:
        print(f"   QUEST{n}: {nm!r}")
    for n in (374, 375):
        g = re.search(r"(?ms)^\[QUEST%d\][^\n]*\n(.*?)(?=^\[|\Z)" % n, final_q)
        nm = re.search(r"(?im)^(?:Nombre|Name)=([^\r\n]+)", g.group(1)) if g else None
        print(f"  QUEST{n}: {nm.group(1).strip() if nm else 'NO ESTA'!r}")
    m21 = re.search(r"(?ms)^\[NPC21\][^\n]*\n(.*?)(?=^.?\s*\[|\Z)", final_n)
    print("  NPC21 bindings:", [l for l in m21.group(1).split("\r\n") if "Quest" in l])


if __name__ == "__main__":
    main()
