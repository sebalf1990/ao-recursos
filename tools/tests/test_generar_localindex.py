"""
Tests for generar_localindex.py (plan 21.005, step 5).

The client looks keys up case-insensitively (clsIniManager.GetValue upper-cases them and binary
searches), so two keys that differ only in case inside one section make the shown text depend on
the search order. Before this fix `Texto=` plus `en_texto=` produced both lines in en_localindex.

The client also reads DescAudio/DescFinalAudio from [QUEST#] (Recursos.bas ~1455), but the
generator never copied them, so quest voices never played.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generar_localindex as gen

OBJ_DAT = "\r\n".join([
    "[INIT]",
    "NumOBJs=3",
    "",
    "[OBJ1]",
    "Name=Manzana Roja",
    "Texto=Restaura 10 puntos de hambre",
    "en_name=Red Apple",
    "en_texto=Restores 10 hunger points",
    "",
    "[OBJ2]",
    "en_Name=Sword",
    "Name=Espada",
    "",
    "[OBJ3]",
    "Name=Escudo",
    "Texto=Defensa 5",
    "Esporas=3",
    "en_name=",
    "en_Texto=",
    "",
])

NPC_DAT = "\r\n".join([
    "[INIT]",
    "NumNPCs=1",
    "",
    "[NPC1]",
    "Name=McGlashan",
    "Desc=Compro lo que el mar puede ofrecer!",
    "en_desc=I buy what the sea can offer!",
    "DisabledInBattleServer=1",
    "",
])

QUESTS_DAT = "\r\n".join([
    "[INIT]",
    "NumQuests=1",
    "",
    "[QUEST1]",
    "Nombre=El aullido",
    "Desc=Caza lobos",
    "DescAudio=1048",
    "DescFinalAudio=1049",
    "en_Nombre=The Howl",
    "",
])

HECHIZOS_DAT = "\r\n".join([
    "[INIT]",
    "NumeroHechizos=1",
    "",
    "[HECHIZO1]",
    "Nombre=Dardo",
    "",
])


def sections(path: Path) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    current = None
    for line in path.read_text(encoding="latin-1").splitlines():
        if line.startswith("["):
            current = line.strip("[]")
            out[current] = []
        elif current and "=" in line:
            key, value = line.split("=", 1)
            out[current].append((key, value))
    return out


class GenerarLocalindexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        (base / "Dat").mkdir()
        (base / "init").mkdir()
        for name, text in [("obj.dat", OBJ_DAT), ("npcs.dat", NPC_DAT),
                           ("quests.dat", QUESTS_DAT), ("hechizos.dat", HECHIZOS_DAT)]:
            (base / "Dat" / name).write_bytes(text.encode("cp1252"))
        gen.main(str(base))
        self.base = base

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def out(self, lang: str) -> dict[str, list[tuple[str, str]]]:
        return sections(self.base / "init" / f"{lang}_localindex.dat")

    def keys_upper(self, lang: str, section: str) -> list[str]:
        return [k.upper() for k, _ in self.out(lang)[section]]

    def test_no_key_appears_twice_ignoring_case(self) -> None:
        for lang in ["sp", "en", "pt", "fr", "it"]:
            for section, pairs in self.out(lang).items():
                upper = [k.upper() for k, _ in pairs]
                self.assertEqual(len(upper), len(set(upper)), f"{lang} [{section}] {pairs}")

    def test_language_value_replaces_base_value_with_other_case(self) -> None:
        self.assertEqual(dict(self.out("en")["OBJ1"])["Texto"], "Restores 10 hunger points")
        self.assertEqual(dict(self.out("en")["OBJ1"])["Name"], "Red Apple")
        self.assertEqual(dict(self.out("en")["NPC1"])["Desc"], "I buy what the sea can offer!")

    def test_other_languages_keep_base_value(self) -> None:
        self.assertEqual(dict(self.out("sp")["OBJ1"])["Texto"], "Restaura 10 puntos de hambre")
        self.assertEqual(dict(self.out("pt")["OBJ1"])["Name"], "Manzana Roja")

    def test_language_value_wins_even_when_base_comes_later(self) -> None:
        self.assertEqual(dict(self.out("en")["OBJ2"])["Name"], "Sword")
        self.assertEqual(dict(self.out("sp")["OBJ2"])["Name"], "Espada")

    def test_empty_translation_falls_back_to_base_value(self) -> None:
        obj = dict(self.out("en")["OBJ3"])
        self.assertEqual(obj.get("Name"), "Escudo")
        self.assertEqual(obj.get("Texto"), "Defensa 5")

    def test_first_seen_key_casing_is_kept(self) -> None:
        self.assertIn("Texto", dict(self.out("en")["OBJ1"]))
        self.assertNotIn("texto", dict(self.out("en")["OBJ1"]))

    def test_quest_audio_keys_reach_every_language(self) -> None:
        for lang in ["sp", "en", "pt", "fr", "it"]:
            quest = dict(self.out(lang)["QUEST1"])
            self.assertEqual(quest.get("DescAudio"), "1048", lang)
            self.assertEqual(quest.get("DescFinalAudio"), "1049", lang)

    def test_npc_battle_server_flag_reaches_every_language(self) -> None:
        # The client reads it in Recursos.bas (~1396) for the world map; plan 22.002 Q5.
        for lang in ["sp", "en", "pt", "fr", "it"]:
            self.assertEqual(dict(self.out(lang)["NPC1"]).get("DisabledInBattleServer"), "1", lang)

    def test_obj_spores_ingredient_reaches_every_language(self) -> None:
        # frmAlqui.frm (~402) lists it as an alchemy ingredient; plan 22.002 Q5.
        for lang in ["sp", "en", "pt", "fr", "it"]:
            self.assertEqual(dict(self.out(lang)["OBJ3"]).get("Esporas"), "3", lang)

    def test_init_counters_and_crlf_are_kept(self) -> None:
        raw = (self.base / "init" / "sp_localindex.dat").read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\r\r\n", raw)
        init = dict(self.out("sp")["INIT"])
        self.assertEqual(init["NUMOBJS"], "3")
        self.assertEqual(init["NUMQUESTS"], "1")


if __name__ == "__main__":
    unittest.main()
