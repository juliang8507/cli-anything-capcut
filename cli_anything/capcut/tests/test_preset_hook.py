"""Regression tests for ``preset hook`` dedicated tracks and aliases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pycapcut as cc
import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.alias_map import list_aliases, resolve_alias
from cli_anything.capcut.core.session import Session


HOOK_CATEGORIES = [
    "curiosity",
    "number",
    "pattern-interrupt",
    "promise",
    "contrarian",
    "fear",
    "question",
    "authority",
    "pov",
    "shock",
]
BOUNCE_CATEGORIES = {"pattern-interrupt", "promise", "shock"}


def _invoke_json(runner: CliRunner, args: list[str]) -> dict[str, Any]:
    result = runner.invoke(
        cli,
        ["--json", *args],
        env={"CAPCUT_NO_STAGING": "1"},
    )
    assert result.exit_code == 0, (
        f"CLI failed for {args!r} (exit={result.exit_code}):\n{result.output}"
    )
    return json.loads(result.output)


def _create_hook_draft(
    tmp_path: Path,
    *,
    category: str,
    option_flags: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    runner = CliRunner()
    drafts = (tmp_path / "drafts").resolve()
    session_path = (tmp_path / "hook.session.json").resolve()

    _invoke_json(
        runner,
        [
            "project",
            "new",
            "--name",
            f"hook-{category}",
            "--draft-folder",
            str(drafts),
            "--output",
            str(session_path),
        ],
    )
    _invoke_json(
        runner,
        [
            "preset",
            "hook",
            "-p",
            str(session_path),
            "-t",
            "훅",
            "--category",
            category,
            *(option_flags or []),
        ],
    )

    validation = _invoke_json(runner, ["validate", "-p", str(session_path)])
    assert validation["valid"] is True

    save_result = _invoke_json(runner, ["save", "-p", str(session_path)])
    draft_path = Path(save_result["draft_content_json"]).resolve()
    assert drafts == draft_path or drafts in draft_path.parents, (
        f"draft escaped tmp_path isolation: {draft_path}"
    )

    session_data = json.loads(session_path.read_text(encoding="utf-8"))
    draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
    return session_data, draft_data


def _assert_text_and_intro(
    session_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    expected_alias: str,
) -> None:
    text_track = next(track for track in draft["tracks"] if track.get("name") == "T_HOOK")
    assert text_track["type"] == "text"
    assert len(text_track["segments"]) == 1

    text_material_id = text_track["segments"][0]["material_id"]
    text_material = next(
        material
        for material in draft["materials"]["texts"]
        if material["id"] == text_material_id
    )
    assert json.loads(text_material["content"])["text"] == "훅"

    intro_op = next(
        operation
        for operation in session_data["operations"]
        if operation["op"] == "add_text_animation"
        and operation["args"].get("role") == "intro"
    )
    intro_name = intro_op["args"]["name"]
    assert intro_name == expected_alias
    assert intro_name in list_aliases("TextIntro")
    assert resolve_alias("TextIntro", intro_name) in cc.TextIntro.__members__


def _assert_effects(
    session_data: dict[str, Any],
    draft: dict[str, Any],
    *,
    expected_aliases: set[str],
) -> None:
    effect_ops = [
        operation for operation in session_data["operations"] if operation["op"] == "add_effect"
    ]
    assert {operation["args"]["name"] for operation in effect_ops} == expected_aliases

    track_ops = {
        operation["args"]["name"]: operation["args"]["type"]
        for operation in session_data["operations"]
        if operation["op"] == "add_track"
    }
    op_track_names = {operation["args"]["track"] for operation in effect_ops}
    assert len(op_track_names) == len(effect_ops)
    assert all(track_ops.get(name) == "effect" for name in op_track_names)

    effect_tracks = [track for track in draft["tracks"] if track.get("type") == "effect"]
    assert {track["name"] for track in effect_tracks} == op_track_names
    assert all(len(track["segments"]) == 1 for track in effect_tracks)

    effect_materials = draft["materials"]["video_effects"]
    material_ids = {material["id"] for material in effect_materials}
    segment_material_ids = {
        segment["material_id"]
        for track in effect_tracks
        for segment in track["segments"]
    }
    assert segment_material_ids == material_ids
    assert {material["name"] for material in effect_materials} == {
        resolve_alias("VideoSceneEffectType", alias) for alias in expected_aliases
    }


@pytest.mark.parametrize("category", HOOK_CATEGORIES)
def test_hook_default_call_saves_text_effect_tracks_and_effects(
    tmp_path: Path,
    category: str,
) -> None:
    session_data, draft = _create_hook_draft(tmp_path, category=category)

    expected_intro = "bounce" if category in BOUNCE_CATEGORIES else "fade_in"
    expected_effects = {"shake"} if category == "authority" else {"shake", "glow"}
    _assert_text_and_intro(session_data, draft, expected_alias=expected_intro)
    _assert_effects(session_data, draft, expected_aliases=expected_effects)


@pytest.mark.parametrize(
    "option_flags,expected_effects",
    [
        pytest.param(["--shake", "--flash"], {"shake", "glow"}, id="shake-flash"),
        pytest.param(["--shake", "--no-flash"], {"shake"}, id="shake-no-flash"),
        pytest.param(["--no-shake", "--flash"], {"glow"}, id="no-shake-flash"),
        pytest.param(["--no-shake", "--no-flash"], set(), id="no-shake-no-flash"),
    ],
)
def test_hook_shake_flash_option_combinations_are_independent(
    tmp_path: Path,
    option_flags: list[str],
    expected_effects: set[str],
) -> None:
    session_data, draft = _create_hook_draft(
        tmp_path,
        category="curiosity",
        option_flags=option_flags,
    )

    _assert_text_and_intro(session_data, draft, expected_alias="fade_in")
    _assert_effects(session_data, draft, expected_aliases=expected_effects)


@pytest.mark.parametrize(
    "op,args,track_type",
    [
        pytest.param(
            "add_effect",
            {"name": "shake", "start": "0s", "duration": "1s"},
            "effect",
            id="effect",
        ),
        pytest.param(
            "add_filter",
            {"name": "warm", "start": "0s", "duration": "1s"},
            "filter",
            id="filter",
        ),
    ],
)
def test_session_auto_creates_dedicated_track(
    tmp_path: Path,
    op: str,
    args: dict[str, Any],
    track_type: str,
) -> None:
    session = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name=f"auto-{track_type}",
        output=tmp_path / "auto.session.json",
    )

    result = session.append_operation(op, args)

    assert [operation["op"] for operation in session.data["operations"]] == [
        "add_track",
        op,
    ]
    track_op, segment_op = session.data["operations"]
    assert track_op["args"]["type"] == track_type
    assert segment_op["args"]["track"] == track_op["args"]["name"]
    assert result["track"] == track_op["args"]["name"]
    assert session.validate()["valid"] is True
