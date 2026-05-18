#!/usr/bin/env python3
"""Audit AO20 private DAT visual references against official localindex data.

This tool is read-only by default. It reports:
- NPC Body/Head values that are missing in the current init catalogs and can be
  proposed from sp_localindex.dat.
- Equipable item Ropaje* values that are missing in cuerpos.dat and can be
  proposed from sp_localindex.dat.
- Active references to deprecated OBJ ids when obj.dat comments point to an
  explicit replacement OBJ.
"""

from __future__ import annotations

import argparse
import re
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Set, Tuple


RESOURCE_ROOT = Path(__file__).resolve().parents[1]
DAT_DIR = RESOURCE_ROOT / "Dat"
INIT_DIR = RESOURCE_ROOT / "init"
MAPS_DIR = RESOURCE_ROOT / "Mapas"

ROPaje_KEYS = (
    "RopajeHumano",
    "RopajeElfo",
    "RopajeElfoOscuro",
    "RopajeEnano",
    "RopajeOrco",
    "RopajeGnomo",
    "RopajeHumana",
    "RopajeElfa",
    "RopajeElfaOscura",
    "RopajeEnana",
    "RopajeOrca",
    "RopajeGnoma",
)


@dataclass
class Section:
    kind: str
    num: int
    header: str
    comment: str
    line: int
    values: Dict[str, str] = field(default_factory=dict)
    raw_lines: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.kind}{self.num}"

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key.lower(), default)

    def name(self) -> str:
        return self.get("Name") or self.get("name") or self.get("En_Name")


@dataclass(frozen=True)
class FieldChange:
    path: Path
    section_kind: str
    section_num: int
    key: str
    old: int
    new: int
    label: str
    reason: str

    def render(self) -> str:
        return f"{self.label}: {self.key} {self.old} {self.reason} -> {self.new}"


@dataclass(frozen=True)
class LineChange:
    path: Path
    line_no: int
    old_obj: int
    new_obj: int
    old_line: str
    new_line: str

    def render(self) -> str:
        return (
            f"{self.path.name}:{self.line_no}: OBJ{self.old_obj} -> OBJ{self.new_obj}: "
            f"{self.old_line.strip()} => {self.new_line.strip()}"
        )


def read_text(path: Path) -> str:
    return path.read_text(encoding="cp1252", errors="replace")


def parse_csm_map(path: Path) -> dict:
    raw = path.read_bytes()
    off = 0
    (
        num_blocks,
        num_l1,
        num_l2,
        num_l3,
        num_l4,
        num_triggers,
        num_luces,
        num_particulas,
        num_npcs,
        num_objs,
        num_te,
    ) = struct.unpack_from("<11l", raw, off)
    off += 44

    off += 8

    off = skip_vb6_string(raw, off)
    off += 1
    off = skip_vb6_string(raw, off)
    off += 4 + 4 + 1
    off = skip_vb6_string(raw, off)
    off = skip_vb6_string(raw, off)
    off = skip_vb6_string(raw, off)
    off += 4 + 4 + 4 + 4
    off = skip_vb6_string(raw, off)
    off += 1 + 1 + 1

    off += num_blocks * 5
    off += num_l1 * 8
    off += num_l2 * 8
    off += num_l3 * 8
    off += num_l4 * 8
    off += num_triggers * 6
    off += num_particulas * 8
    off += num_luces * 9

    obj_spawns = []
    for _ in range(num_objs):
        x, y, obj_id, amount = struct.unpack_from("<4h", raw, off)
        obj_spawns.append({"obj_id": obj_id, "x": x, "y": y, "amount": amount})
        off += 8

    npc_spawns = []
    for _ in range(num_npcs):
        x, y, npc_id = struct.unpack_from("<3h", raw, off)
        npc_spawns.append({"npc_id": npc_id, "x": x, "y": y})
        off += 6

    return {
        "header": {"num_npcs": num_npcs, "num_objs": num_objs, "num_te": num_te},
        "npc_spawns": npc_spawns,
        "obj_spawns": obj_spawns,
    }


def skip_vb6_string(raw: bytes, off: int) -> int:
    (length,) = struct.unpack_from("<h", raw, off)
    return off + 2 + max(0, length)


def parse_sections(path: Path, wanted: Iterable[str]) -> Dict[int, Section]:
    wanted_set = {w.upper() for w in wanted}
    sections: Dict[int, Section] = {}
    current: Optional[Section] = None
    header_re = re.compile(r"^\[(?P<kind>[A-Za-z_]+)(?P<num>\d+)\](?P<comment>.*)$")

    for line_no, line in enumerate(read_text(path).splitlines(), start=1):
        match = header_re.match(line.strip())
        if match and match.group("kind").upper() in wanted_set:
            current = Section(
                kind=match.group("kind").upper(),
                num=int(match.group("num")),
                header=line.strip(),
                comment=match.group("comment").strip(),
                line=line_no,
            )
            sections[current.num] = current
            continue

        if current is None:
            continue

        current.raw_lines.append(line)
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("'"):
            continue
        current.values[key.lower()] = value.strip()

    return sections


def existing_body_ids(path: Path) -> set[int]:
    text = read_text(path)
    return {int(match.group(1)) for match in re.finditer(r"(?m)^\[BODY(\d+)\]", text)}


def existing_head_ids(path: Path) -> set[int]:
    """`cabezas.ind` es binario:
       tCabecera (255+4+4 = 263 bytes) + Numheads(Integer 2 bytes) +
       Miscabezas(0..Numheads) cada uno con 4 Long = 16 bytes.
       Un head ID i es valido si Miscabezas(i).Head(1) != 0 (criterio cliente).
    """
    raw = path.read_bytes()
    if len(raw) < 263 + 2:
        return set()
    (num_heads,) = struct.unpack_from("<h", raw, 263)
    ids: set[int] = {0}  # Head=0 siempre valido (sin cabeza)
    base = 263 + 2
    for i in range(0, num_heads + 1):
        off = base + i * 16
        if off + 4 > len(raw):
            break
        (head1,) = struct.unpack_from("<l", raw, off)
        if head1 != 0:
            ids.add(i)
    return ids


def as_int(value: str) -> Optional[int]:
    value = value.strip()
    if not value:
        return None
    match = re.match(r"^-?\d+", value)
    return int(match.group(0)) if match else None


def parse_id_filter(raw_ids: str) -> Optional[Set[Tuple[str, int]]]:
    if not raw_ids:
        return None
    ids: Set[Tuple[str, int]] = set()
    for part in raw_ids.split(","):
        part = part.strip().upper()
        if not part:
            continue
        match = re.fullmatch(r"(NPC|OBJ)?\s*(\d+)", part)
        if not match:
            raise ValueError(f"ID invalido: {part!r}. Usar formato NPC4,OBJ3502.")
        kind = match.group(1)
        if not kind:
            raise ValueError(f"ID ambiguo: {part!r}. Usar prefijo NPC u OBJ.")
        ids.add((kind, int(match.group(2))))
    return ids


def map_id_filter(map_num: int) -> Tuple[Set[Tuple[str, int]], dict]:
    path = MAPS_DIR / f"mapa{map_num}.csm"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    parsed = parse_csm_map(path)
    ids: Set[Tuple[str, int]] = set()
    for spawn in parsed["npc_spawns"]:
        if spawn["npc_id"] > 0:
            ids.add(("NPC", int(spawn["npc_id"])))
    for spawn in parsed["obj_spawns"]:
        if spawn["obj_id"] > 0:
            ids.add(("OBJ", int(spawn["obj_id"])))
    return ids, parsed


def combine_filters(
    explicit_ids: Optional[Set[Tuple[str, int]]],
    map_ids: Optional[Set[Tuple[str, int]]],
) -> Optional[Set[Tuple[str, int]]]:
    if explicit_ids is None:
        return map_ids
    if map_ids is None:
        return explicit_ids
    return explicit_ids & map_ids


def audit_map_dat_gaps(map_num: int, parsed_map: dict) -> List[str]:
    private_npcs = parse_sections(DAT_DIR / "npcs.dat", ("NPC",))
    private_objs = parse_sections(DAT_DIR / "obj.dat", ("OBJ",))
    rows: List[str] = []

    npc_spawns: DefaultDict[int, List[str]] = defaultdict(list)
    for spawn in parsed_map["npc_spawns"]:
        npc_id = int(spawn["npc_id"])
        if npc_id > 0:
            npc_spawns[npc_id].append(f"{spawn['x']}-{spawn['y']}")
    for npc_id, positions in sorted(npc_spawns.items()):
        section = private_npcs.get(npc_id)
        if section is None:
            rows.append(f"mapa{map_num}: NPC{npc_id} no existe en NPCs.dat; posiciones {', '.join(positions)}")
        elif not section.name().strip():
            rows.append(f"mapa{map_num}: NPC{npc_id} no tiene Name; posiciones {', '.join(positions)}")

    obj_spawns: DefaultDict[int, List[str]] = defaultdict(list)
    for spawn in parsed_map["obj_spawns"]:
        obj_id = int(spawn["obj_id"])
        if obj_id > 0:
            obj_spawns[obj_id].append(f"{spawn['x']}-{spawn['y']}")
    for obj_id, positions in sorted(obj_spawns.items()):
        section = private_objs.get(obj_id)
        if section is None:
            rows.append(f"mapa{map_num}: OBJ{obj_id} no existe en obj.dat; posiciones {', '.join(positions)}")
        elif not section.name().strip():
            rows.append(f"mapa{map_num}: OBJ{obj_id} no tiene Name; posiciones {', '.join(positions)}")
    return rows


def id_allowed(kind: str, num: int, ids: Optional[Set[Tuple[str, int]]]) -> bool:
    return ids is None or (kind.upper(), num) in ids


def collect_npc_changes(
    limit: int = 0,
    include_different: bool = False,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[FieldChange]:
    private_npcs = parse_sections(DAT_DIR / "npcs.dat", ("NPC",))
    official_npcs = parse_sections(INIT_DIR / "sp_localindex.dat", ("NPC",))
    body_ids = existing_body_ids(INIT_DIR / "cuerpos.dat")
    head_ids = existing_head_ids(INIT_DIR / "cabezas.ind")

    changes: List[FieldChange] = []
    for num, npc in sorted(private_npcs.items()):
        if not id_allowed("NPC", num, ids):
            continue
        official = official_npcs.get(num)
        if not official:
            continue
        for key, valid_ids in (("Body", body_ids), ("Head", head_ids)):
            old = as_int(npc.get(key))
            new = as_int(official.get(key))
            if old is None or new is None or old == new:
                continue
            missing = old not in valid_ids and old != 0
            if missing:
                reason = "missing"
            elif include_different:
                reason = "differs"
            else:
                continue
            changes.append(
                FieldChange(
                    path=DAT_DIR / "npcs.dat",
                    section_kind="NPC",
                    section_num=num,
                    key=key,
                    old=old,
                    new=new,
                    label=f"NPC{num} {npc.name()!r}",
                    reason=reason,
                )
            )
            if limit and len(changes) >= limit:
                return changes
    return changes


def audit_npcs(
    limit: int = 0,
    include_different: bool = False,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[str]:
    grouped: DefaultDict[str, List[str]] = defaultdict(list)
    for change in collect_npc_changes(limit, include_different, ids):
        grouped[change.label].append(f"{change.key} {change.old} {change.reason} -> {change.new}")
    return [f"{label}: " + "; ".join(problems) for label, problems in grouped.items()]


def collect_item_changes(
    limit: int = 0,
    include_different: bool = False,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[FieldChange]:
    private_objs = parse_sections(DAT_DIR / "obj.dat", ("OBJ",))
    official_objs = parse_sections(INIT_DIR / "sp_localindex.dat", ("OBJ",))
    body_ids = existing_body_ids(INIT_DIR / "cuerpos.dat")

    changes: List[FieldChange] = []
    for num, obj in sorted(private_objs.items()):
        if not id_allowed("OBJ", num, ids):
            continue
        has_ropaje = any(obj.get(key) for key in ROPaje_KEYS)
        if obj.get("ObjType") != "3" and not has_ropaje:
            continue
        official = official_objs.get(num)
        if not official:
            continue
        for key in ROPaje_KEYS:
            old = as_int(obj.get(key))
            new = as_int(official.get(key))
            if old is None or new is None or old == new:
                continue
            missing = old not in body_ids and old != 0
            if missing:
                reason = "missing"
            elif include_different and new in body_ids:
                reason = "differs"
            else:
                continue
            changes.append(
                FieldChange(
                    path=DAT_DIR / "obj.dat",
                    section_kind="OBJ",
                    section_num=num,
                    key=key,
                    old=old,
                    new=new,
                    label=f"OBJ{num} {obj.name()!r}",
                    reason=reason,
                )
            )
            if limit and len(changes) >= limit:
                return changes
    return changes


def audit_items(
    limit: int = 0,
    include_different: bool = False,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[str]:
    grouped: DefaultDict[str, List[str]] = defaultdict(list)
    for change in collect_item_changes(limit, include_different, ids):
        grouped[change.label].append(f"{change.key} {change.old} {change.reason} -> {change.new}")
    return [f"{label}: " + "; ".join(problems) for label, problems in grouped.items()]


def explicit_obj_replacements() -> Dict[int, int]:
    objs = parse_sections(DAT_DIR / "obj.dat", ("OBJ",))
    replacements: Dict[int, int] = {}
    for old_id, section in objs.items():
        comment = section.comment
        if not comment:
            continue
        if not re.search(r"(?i)borrar|reemplazar|modificar|cambiar", comment):
            continue
        if not re.search(r"(?i)reemplazar\s+con|entrega\s+por|entregar\s+\d+|modificar\s+codigo\s+de\s+entrega|modificar\s+c[oó]digo\s+de\s+entrega", comment):
            continue
        candidates = [int(n) for n in re.findall(r"(?i)\b(?:OBJ)?(\d{3,5})\b", comment)]
        candidates = [n for n in candidates if n != old_id and n in objs]
        if len(candidates) == 1:
            replacements[old_id] = candidates[0]
    return replacements


def collect_deprecated_changes(limit: int = 0, ids: Optional[Set[Tuple[str, int]]] = None) -> List[LineChange]:
    replacements = explicit_obj_replacements()
    changes: List[LineChange] = []
    if not replacements:
        return changes

    patterns = {
        old: re.compile(
            rf"(?i)\b(?P<field>Obj\d+|DropQuest\d+|GiveObj\d*|RewardOBJ|Obj)\s*=\s*(?P<prefix>(?:\d+-)?)"
            rf"{old}(?P<suffix>(?:-\d+)*\b)"
        )
        for old in replacements
    }

    for path in sorted(DAT_DIR.glob("*.dat")):
        for line_no, line in enumerate(read_text(path).splitlines(), start=1):
            for old, pattern in patterns.items():
                if not id_allowed("OBJ", old, ids):
                    continue
                for match in pattern.finditer(line):
                    new = replacements[old]
                    new_line = pattern.sub(
                        lambda m: f"{m.group('field')}={m.group('prefix')}{new}{m.group('suffix')}",
                        line,
                        count=1,
                    )
                    changes.append(
                        LineChange(
                            path=path,
                            line_no=line_no,
                            old_obj=old,
                            new_obj=new,
                            old_line=line,
                            new_line=new_line,
                        )
                    )
                    if limit and len(changes) >= limit:
                        return changes
    return changes


def audit_deprecated_refs(limit: int = 0, ids: Optional[Set[Tuple[str, int]]] = None) -> List[str]:
    return [change.render() for change in collect_deprecated_changes(limit, ids)]


# IDs privados intocables: NPCs maestros del sistema de profesiones (CHANGELOG 2026-04-27).
# Existen solo en NPCs.dat privado, NO en sp_localindex.dat. Tienen campos custom
# (RequireToggle, EsMaestroProfesion, ProfesionEnsenada) que deben preservarse.
PRIVATE_NPC_RANGES: List[Tuple[int, int]] = [(1405, 1411)]


def is_private_npc(num: int) -> bool:
    return any(lo <= num <= hi for lo, hi in PRIVATE_NPC_RANGES)


# Campos del localindex que se permiten copiar al stub.
# Detalle del criterio en docs/audit/07_pipeline_localindex_a_servidor.md
STUB_ALLOWLIST_LOCALINDEX = (
    "Name",
    "Desc",
    "En_Name",
    "En_Desc",
    "Body",
    "Head",
    "BodyIdle",
    "NpcType",
    "ShowName",
    "PuedeInvocar",
    "SoundOpen",
    "SoundClose",
    "Minimap",
    "Comercia",
    "NoMapInfo",
)

# Defaults seguros cuando no estan en localindex.
# IMPORTANTE: Heading=3 es OBLIGATORIO. Sin Heading el server no spawnea
# correctamente al NPC (queda invisible para el cliente). Bug detectado el
# 2026-05-06 en mapas Morgrim (591-594) tras lote 3/fase B con scripts
# one-shot que olvidaron este default. Cualquier script externo que haga
# resync/upsert de NPCs DEBE incluir Heading.
STUB_DEFAULTS = (
    ("ShowName", "1"),
    ("Heading", "3"),
    ("Movement", "1"),
    ("Attackable", "0"),
    ("Hostile", "0"),
    ("ReSpawn", "0"),
)

# Allowlist de campos OBJ a copiar al stub desde localindex.
STUB_OBJ_ALLOWLIST = (
    "Name",
    "Desc",
    "Texto",
    "GrhIndex",
    "ObjType",
    "Agarrable",
    "Radio",
    "en_Name",
    "En_Name",
)


@dataclass
class StubCreation:
    kind: str  # 'NPC' o 'OBJ'
    sec_id: int
    name: str
    summary: str  # texto corto para reporte (Body/Head/NpcType o GrhIndex/ObjType)
    section_text: str  # bloque [Kindn]\nKey=Value\n... ya formateado con CRLF
    map_nums: List[int]  # mapas donde aparece spawneado

    @property
    def npc_id(self) -> int:
        # Compat con código previo que asumía npc_id; ahora es alias.
        return self.sec_id

    def render(self) -> str:
        maps = ",".join(f"mapa{m}" for m in self.map_nums)
        return f"{self.kind}{self.sec_id} '{self.name}' {self.summary} ({maps})"


def _collect_target_maps(map_nums: Optional[Iterable[int]]) -> List[int]:
    if map_nums is not None:
        return list(map_nums)
    return sorted(
        int(m.group(1))
        for m in (re.match(r"mapa(\d+)\.csm$", p.name) for p in MAPS_DIR.glob("mapa*.csm"))
        if m
    )


def _collect_npc_stubs(
    map_nums: Optional[Iterable[int]],
    ids: Optional[Set[Tuple[str, int]]],
) -> List[StubCreation]:
    private_npcs = parse_sections(DAT_DIR / "npcs.dat", ("NPC",))
    official_npcs = parse_sections(INIT_DIR / "sp_localindex.dat", ("NPC",))
    body_ids = existing_body_ids(INIT_DIR / "cuerpos.dat")
    head_ids = existing_head_ids(INIT_DIR / "cabezas.ind")

    target_maps = _collect_target_maps(map_nums)
    npc_to_maps: DefaultDict[int, List[int]] = defaultdict(list)
    for mn in target_maps:
        path = MAPS_DIR / f"mapa{mn}.csm"
        if not path.exists():
            continue
        try:
            parsed = parse_csm_map(path)
        except Exception:
            continue
        seen = set()
        for spawn in parsed["npc_spawns"]:
            nid = int(spawn["npc_id"])
            if nid > 0 and nid not in seen:
                npc_to_maps[nid].append(mn)
                seen.add(nid)

    stubs: List[StubCreation] = []
    for nid in sorted(npc_to_maps):
        if not id_allowed("NPC", nid, ids):
            continue
        if is_private_npc(nid):
            continue
        existing = private_npcs.get(nid)
        if existing is not None and existing.name().strip():
            continue
        official = official_npcs.get(nid)
        if not official:
            continue
        body = as_int(official.get("Body")) or 0
        head = as_int(official.get("Head")) or 0
        if body and body not in body_ids:
            continue
        if head and head not in head_ids and head != 0:
            continue

        lines: List[str] = []
        comment = " 'AUTO desde sp_localindex.dat (audit_visual_refs --create-stubs)"
        lines.append(f"[NPC{nid}]{comment}")
        used_keys = set()
        for key in STUB_ALLOWLIST_LOCALINDEX:
            v = official.values.get(key.lower())
            if v is None or v == "":
                continue
            lines.append(f"{key}={v}")
            used_keys.add(key.lower())
        for key, default in STUB_DEFAULTS:
            if key.lower() not in used_keys:
                lines.append(f"{key}={default}")

        section_text = "\r\n".join(lines) + "\r\n"
        npctype = official.get("NpcType") or "0"
        summary = f"Body={body} Head={head} NpcType={npctype}"
        stubs.append(
            StubCreation(
                kind="NPC",
                sec_id=nid,
                name=official.get("Name") or official.get("En_Name") or "(sin nombre)",
                summary=summary,
                section_text=section_text,
                map_nums=npc_to_maps[nid],
            )
        )
    return stubs


def _collect_obj_stubs(
    map_nums: Optional[Iterable[int]],
    ids: Optional[Set[Tuple[str, int]]],
) -> List[StubCreation]:
    private_objs = parse_sections(DAT_DIR / "obj.dat", ("OBJ",))
    official_objs = parse_sections(INIT_DIR / "sp_localindex.dat", ("OBJ",))

    target_maps = _collect_target_maps(map_nums)
    obj_to_maps: DefaultDict[int, List[int]] = defaultdict(list)
    for mn in target_maps:
        path = MAPS_DIR / f"mapa{mn}.csm"
        if not path.exists():
            continue
        try:
            parsed = parse_csm_map(path)
        except Exception:
            continue
        seen = set()
        for spawn in parsed["obj_spawns"]:
            oid = int(spawn["obj_id"])
            if oid > 0 and oid not in seen:
                obj_to_maps[oid].append(mn)
                seen.add(oid)

    stubs: List[StubCreation] = []
    for oid in sorted(obj_to_maps):
        if not id_allowed("OBJ", oid, ids):
            continue
        existing = private_objs.get(oid)
        # Saltar si OBJ existe Y tiene Name
        if existing is not None and existing.name().strip():
            continue
        official = official_objs.get(oid)
        if not official:
            continue
        # Requiere al menos Name + GrhIndex/ObjType para ser un stub mínimo válido
        if not (official.get("Name") and (official.get("GrhIndex") or official.get("ObjType"))):
            continue

        lines: List[str] = []
        comment = " 'AUTO desde sp_localindex.dat (audit_visual_refs --create-stubs)"
        lines.append(f"[OBJ{oid}]{comment}")
        used_keys = set()
        for key in STUB_OBJ_ALLOWLIST:
            v = official.values.get(key.lower())
            if v is None or v == "":
                continue
            if key.lower() in used_keys:
                continue  # evitar duplicados (en_Name vs En_Name)
            lines.append(f"{key}={v}")
            used_keys.add(key.lower())

        section_text = "\r\n".join(lines) + "\r\n"
        summary = f"GrhIndex={official.get('GrhIndex') or '?'} ObjType={official.get('ObjType') or '?'}"
        stubs.append(
            StubCreation(
                kind="OBJ",
                sec_id=oid,
                name=official.get("Name"),
                summary=summary,
                section_text=section_text,
                map_nums=obj_to_maps[oid],
            )
        )
    return stubs


def collect_stub_creations(
    map_nums: Optional[Iterable[int]] = None,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[StubCreation]:
    """Detecta NPCs/OBJs spawneados en mapas que no existen en NPCs.dat/obj.dat
    (o no tienen Name) y propone stubs creados desde sp_localindex.dat.
    """
    return _collect_npc_stubs(map_nums, ids) + _collect_obj_stubs(map_nums, ids)


def audit_stub_creations(
    map_nums: Optional[Iterable[int]] = None,
    ids: Optional[Set[Tuple[str, int]]] = None,
) -> List[str]:
    return [s.render() for s in collect_stub_creations(map_nums, ids)]


def _apply_stubs_to_file(
    file_path: Path,
    section_kind: str,
    init_counter_key: str,
    stubs_for_file: List[StubCreation],
) -> None:
    """Worker compartido: aplica stubs en un .dat puntual (NPCs.dat o obj.dat).
    Reemplaza in-place si existe la sección, agrega al final si no.
    Actualiza [INIT].<init_counter_key> si el nuevo max supera el actual.
    """
    if not stubs_for_file:
        return

    backup = backup_path(file_path)
    backup.write_bytes(file_path.read_bytes())
    text = read_text(file_path)

    new_max_id = max(s.sec_id for s in stubs_for_file)
    init_match = re.search(r"(?m)^\[INIT\][^\r\n]*", text)
    if init_match:
        next_sec = re.search(r"(?m)^\[[A-Za-z_]+\d*\][^\r\n]*", text[init_match.end():])
        init_end = init_match.end() + next_sec.start() if next_sec else len(text)
        init_block = text[init_match.start():init_end]
        num_re = re.compile(rf"(?im)^({re.escape(init_counter_key)}\s*=\s*)(\d+)(\s*)$")
        nm = num_re.search(init_block)
        if nm:
            current = int(nm.group(2))
            if new_max_id > current:
                init_block = num_re.sub(rf"\g<1>{new_max_id}\g<3>", init_block, count=1)
                text = text[:init_match.start()] + init_block + text[init_end:]

    appended: List[StubCreation] = []
    for stub in stubs_for_file:
        header_re = rf"(?m)^\[{section_kind}{stub.sec_id}\][^\r\n]*"
        match = re.search(header_re, text)
        if match:
            next_match = re.search(r"(?m)^\[[A-Za-z_]+\d*\][^\r\n]*", text[match.end():])
            end = match.end() + next_match.start() if next_match else len(text)
            text = text[: match.start()] + stub.section_text + text[end:]
        else:
            appended.append(stub)

    if appended:
        if not text.endswith("\r\n"):
            text += "\r\n"
        text += "\r\n".join(s.section_text for s in appended)

    file_path.write_text(normalize_crlf(text), encoding="cp1252", newline="")


def apply_stub_creations(stubs: List[StubCreation]) -> List[Path]:
    """Aplica stubs al archivo correspondiente según kind (NPC -> npcs.dat,
    OBJ -> obj.dat). Devuelve lista de archivos tocados.
    """
    if not stubs:
        return []
    npc_stubs = [s for s in stubs if s.kind == "NPC"]
    obj_stubs = [s for s in stubs if s.kind == "OBJ"]
    touched: List[Path] = []
    if npc_stubs:
        path = DAT_DIR / "npcs.dat"
        _apply_stubs_to_file(path, "NPC", "NumNPCs", npc_stubs)
        touched.append(path)
    if obj_stubs:
        path = DAT_DIR / "obj.dat"
        _apply_stubs_to_file(path, "OBJ", "NumOBJs", obj_stubs)
        touched.append(path)
    return touched


def normalize_crlf(text: str) -> str:
    return re.sub(r"(?<!\r)\n", "\r\n", text)


def backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.name}.pre_audit_visual_refs_{stamp}")


def replace_section_value(text: str, change: FieldChange) -> str:
    header_re = rf"(?m)^\[{change.section_kind}{change.section_num}\][^\r\n]*"
    match = re.search(header_re, text)
    if not match:
        raise RuntimeError(f"No se encontro seccion {change.section_kind}{change.section_num}")

    next_match = re.search(r"(?m)^\[[A-Za-z_]+\d+\][^\r\n]*", text[match.end() :])
    end = match.end() + next_match.start() if next_match else len(text)
    block = text[match.start() : end]
    key_re = re.compile(rf"(?im)^({re.escape(change.key)}\s*=\s*)[-]?\d+(\s*)$")
    if not key_re.search(block):
        raise RuntimeError(f"No se encontro {change.key} en {change.section_kind}{change.section_num}")
    block = key_re.sub(rf"\g<1>{change.new}\2", block, count=1)
    return text[: match.start()] + block + text[end:]


def apply_changes(field_changes: List[FieldChange], line_changes: List[LineChange]) -> List[Path]:
    by_path_fields: DefaultDict[Path, List[FieldChange]] = defaultdict(list)
    by_path_lines: DefaultDict[Path, List[LineChange]] = defaultdict(list)
    for change in field_changes:
        by_path_fields[change.path].append(change)
    for change in line_changes:
        by_path_lines[change.path].append(change)

    touched = sorted(set(by_path_fields) | set(by_path_lines))
    for path in touched:
        backup = backup_path(path)
        backup.write_bytes(path.read_bytes())
        text = read_text(path)
        for change in by_path_fields.get(path, []):
            text = replace_section_value(text, change)
        if path in by_path_lines:
            lines = text.splitlines()
            for change in by_path_lines[path]:
                if lines[change.line_no - 1] != change.old_line:
                    raise RuntimeError(f"La linea {path.name}:{change.line_no} cambio antes de aplicar")
                lines[change.line_no - 1] = change.new_line
            text = "\r\n".join(lines)
            if path.read_text(encoding="cp1252", errors="replace").endswith(("\r\n", "\n")):
                text += "\r\n"
        path.write_text(normalize_crlf(text), encoding="cp1252", newline="")
    return touched


def print_section(title: str, rows: List[str]) -> None:
    print(f"\n## {title}")
    if not rows:
        print("OK: no se detectaron hallazgos.")
        return
    for row in rows:
        print(f"- {row}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita referencias visuales privadas vs localindex oficial.")
    parser.add_argument("--npcs", action="store_true", help="Auditar NPCs.")
    parser.add_argument("--items", action="store_true", help="Auditar items equipables.")
    parser.add_argument("--deprecated", action="store_true", help="Auditar referencias a OBJ reemplazados.")
    parser.add_argument(
        "--create-stubs",
        action="store_true",
        help="Crear secciones [NPCn] faltantes desde sp_localindex.dat para NPCs spawneados sin entrada (o sin Name) en NPCs.dat.",
    )
    parser.add_argument("--limit", type=int, default=50, help="Limite por seccion. 0 = sin limite.")
    parser.add_argument("--ids", default="", help="Filtrar IDs, por ejemplo NPC4,OBJ3502.")
    parser.add_argument("--map", type=int, default=0, help="Filtrar por IDs usados en dev/Recursos/Mapas/mapaN.csm.")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios reportados. Crea backup automatico.")
    parser.add_argument("--yes-all", action="store_true", help="Permite --apply sin --ids.")
    parser.add_argument(
        "--include-different",
        action="store_true",
        help="Incluir referencias validas que difieren del localindex oficial. Por defecto solo faltantes.",
    )
    args = parser.parse_args()
    ids = parse_id_filter(args.ids)
    map_ids = None
    parsed_map = None
    if args.map:
        map_ids, parsed_map = map_id_filter(args.map)
        ids = combine_filters(ids, map_ids)

    run_all = not (args.npcs or args.items or args.deprecated or args.create_stubs)
    map_nums_for_stubs = [args.map] if args.map else None

    if parsed_map:
        npc_ids = sorted(n for kind, n in map_ids or set() if kind == "NPC")
        obj_ids = sorted(n for kind, n in map_ids or set() if kind == "OBJ")
        print(f"Mapa {args.map}: {len(parsed_map['npc_spawns'])} spawns NPC ({len(npc_ids)} IDs unicos), "
              f"{len(parsed_map['obj_spawns'])} spawns OBJ ({len(obj_ids)} IDs unicos).")
        print("NPC IDs:", ",".join(f"NPC{n}" for n in npc_ids) or "-")
        print("OBJ IDs:", ",".join(f"OBJ{n}" for n in obj_ids) or "-")
        print_section("Gaps de DAT del mapa", audit_map_dat_gaps(args.map, parsed_map))

    if args.apply:
        if args.include_different:
            parser.error("--apply no permite --include-different; solo se aplican faltantes/reemplazos explicitos.")
        if ids is None and not args.yes_all:
            parser.error("--apply requiere --ids o --yes-all.")
        field_changes: List[FieldChange] = []
        line_changes: List[LineChange] = []
        if run_all or args.npcs:
            field_changes.extend(collect_npc_changes(args.limit, False, ids))
        if run_all or args.items:
            field_changes.extend(collect_item_changes(args.limit, False, ids))
        if run_all or args.deprecated:
            line_changes.extend(collect_deprecated_changes(args.limit, ids))

        stubs: List[StubCreation] = []
        if run_all or args.create_stubs:
            stubs = collect_stub_creations(map_nums_for_stubs, ids)

        print_section("Cambios de campos", [change.render() for change in field_changes])
        print_section("Cambios de lineas", [change.render() for change in line_changes])
        print_section("Stubs nuevos a crear", [s.render() for s in stubs])
        if not field_changes and not line_changes and not stubs:
            return 0
        touched = apply_changes(field_changes, line_changes) if (field_changes or line_changes) else []
        stub_paths = apply_stub_creations(stubs) if stubs else []
        for sp in stub_paths:
            if sp not in touched:
                touched.append(sp)
        print("\nArchivos modificados:")
        for path in touched:
            print(f"- {path}")
        return 0

    if run_all or args.npcs:
        print_section("NPCs", audit_npcs(args.limit, args.include_different, ids))
    if run_all or args.items:
        print_section("Items equipables", audit_items(args.limit, args.include_different, ids))
    if run_all or args.deprecated:
        print_section("OBJ deprecated con reemplazo explicito", audit_deprecated_refs(args.limit, ids))
    if run_all or args.create_stubs:
        print_section("Stubs propuestos (faltantes en NPCs.dat con localindex disponible)",
                      audit_stub_creations(map_nums_for_stubs, ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
