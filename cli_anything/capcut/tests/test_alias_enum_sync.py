"""alias 테이블과 pycapcut enum/결산 manifest의 동기화 회귀 테스트."""

from __future__ import annotations

from collections import Counter
from enum import Enum
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core import alias_map


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "scripts" / "alias_manifest.json"
DISPOSITIONS = {"remapped", "removed", "kept", "deferred"}


def _load_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), f"결산 manifest가 없음: {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_non_font_alias_targets_exist_in_corresponding_enums() -> None:
    dead: list[str] = []
    for enum_class, (enum_cls, aliases) in alias_map._ALIAS_REGISTRY.items():
        if enum_class == "FontType":
            continue
        member_names = set(enum_cls.__members__)
        dead.extend(
            f"{enum_class}.{alias} -> {target}"
            for alias, target in aliases.items()
            if target not in member_names
        )

    assert dead == [], "enum에 없는 alias 대상:\n" + "\n".join(dead)


def test_manifest_has_exactly_107_classified_entries() -> None:
    manifest = _load_manifest()
    entries = manifest["entries"]
    actual_counts = Counter(entry["disposition"] for entry in entries)

    assert manifest["total"] == 107
    assert len(entries) == 107
    assert set(manifest["counts"]) == DISPOSITIONS
    assert sum(manifest["counts"].values()) == 107
    assert dict(actual_counts) == {
        disposition: manifest["counts"][disposition]
        for disposition in DISPOSITIONS
        if manifest["counts"][disposition]
    }

    identities: set[tuple[str, str]] = set()
    for entry in entries:
        assert {
            "alias_dict",
            "enum_class",
            "alias",
            "old_target",
            "disposition",
            "reason_ko",
        } <= set(entry)
        assert entry["disposition"] in DISPOSITIONS
        assert entry["reason_ko"].strip()
        if entry["disposition"] == "remapped":
            assert entry.get("new_target")

        identity = (entry["alias_dict"], entry["alias"])
        assert identity not in identities, f"manifest 중복 항목: {identity}"
        identities.add(identity)


def test_manifest_dispositions_match_alias_map() -> None:
    manifest = _load_manifest()

    for entry in manifest["entries"]:
        aliases = getattr(alias_map, entry["alias_dict"])
        alias = entry["alias"]
        disposition = entry["disposition"]

        if disposition == "remapped":
            assert aliases.get(alias) == entry["new_target"]
        elif disposition in {"removed", "deferred"}:
            assert alias not in aliases
        elif disposition == "kept":
            assert aliases.get(alias) == entry["old_target"]


def test_alias_audit_script_reports_version_time_and_per_dict_counts() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "alias_audit.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "pycapcut version: 0.0.3" in result.stdout
    assert re.search(r"audit time: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", result.stdout)
    assert "FONT_ALIASES: excluded" in result.stdout
    assert "OUTRO_ALIASES (OutroType): total=9 alive=9 dead=0" in result.stdout
    assert "VIDEO_CHARACTER_EFFECT_ALIASES (VideoCharacterEffectType): total=0 alive=0 dead=0" in result.stdout


def test_alias_audit_candidate_search_suggests_existing_enum_members() -> None:
    script_path = REPO_ROOT / "scripts" / "alias_audit.py"
    assert script_path.is_file()
    spec = importlib.util.spec_from_file_location("alias_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class ExampleEnum(Enum):
        向左擦除 = "wipe-left"
        闪黑 = "black-flash"

    candidates = module._candidate_replacements("左擦除", ExampleEnum)

    assert candidates[0] == "向左擦除"
    assert set(candidates) <= set(ExampleEnum.__members__)


def test_command_help_uses_only_live_alias_examples() -> None:
    runner = CliRunner()

    audio_help = runner.invoke(cli, ["audio", "add-effect", "--help"])
    assert audio_help.exit_code == 0
    assert "concert_hall, underwater" in audio_help.output
    assert "echo, reverb" not in audio_help.output

    filter_help = runner.invoke(cli, ["effect", "add-filter", "--help"])
    assert filter_help.exit_code == 0
    assert "warm, golden_hour, bw_2" in filter_help.output
    assert "cinematic" not in filter_help.output

    style_help = runner.invoke(cli, ["style", "save", "--help"])
    assert style_help.exit_code == 0
    assert '"name":"golden_hour"' in style_help.output
    assert '"name":"cinematic"' not in style_help.output
