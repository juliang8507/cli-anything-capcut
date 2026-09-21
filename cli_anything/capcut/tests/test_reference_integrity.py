"""Saved-draft ``extra_material_refs`` integrity characterization."""

from __future__ import annotations

import json
from typing import Any

import pycapcut as cc
import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.session import Session
from cli_anything.capcut.tests.test_e2e_op_matrix import (
    _build_baseline,
    _save_draft,
)


def _dangling_extra_material_refs(draft: dict[str, Any]) -> list[dict[str, str]]:
    """Return segment refs whose ids do not occur anywhere else in the draft."""
    ids: set[str] = set()

    def collect_ids(value: Any) -> None:
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str):
                ids.add(identifier)
            for child in value.values():
                collect_ids(child)
        elif isinstance(value, list):
            for child in value:
                collect_ids(child)

    collect_ids(draft)

    dangling: list[dict[str, str]] = []
    for track in draft.get("tracks", []):
        for segment in track.get("segments", []):
            for ref_id in segment.get("extra_material_refs", []):
                if ref_id not in ids:
                    dangling.append(
                        {
                            "track": track.get("name", ""),
                            "segment_id": segment.get("id", ""),
                            "ref_id": ref_id,
                        }
                    )
    return dangling


REFERENCE_CASES = [
    pytest.param(None, None, id="baseline"),
    pytest.param(
        "add_mask",
        {"track": "V1", "segment_ref": "op_4", "name": next(iter(cc.MaskType)).name},
        id="add_mask",
    ),
    pytest.param(
        "add_video_fade",
        {"track": "V1", "segment_ref": "op_4", "fade_in": "100ms", "fade_out": "100ms"},
        id="add_video_fade",
    ),
    pytest.param(
        "add_video_animation",
        {
            "track": "V1",
            "segment_ref": "op_4",
            "role": "intro",
            "name": next(iter(cc.IntroType)).name,
            "duration": "100ms",
        },
        id="add_video_animation",
    ),
    pytest.param(
        "add_video_transition",
        {
            "track": "V1",
            "segment_ref": "op_4",
            "name": next(iter(cc.TransitionType)).name,
            "duration": "100ms",
        },
        id="add_video_transition",
    ),
    pytest.param(
        "add_background",
        {"track": "V1", "segment_ref": "op_4", "fill_type": "blur"},
        id="add_background",
    ),
    pytest.param(
        "add_audio_fade",
        {"track": "A1", "segment_ref": "op_5", "fade_in": "100ms", "fade_out": "100ms"},
        id="add_audio_fade",
    ),
    pytest.param(
        "add_audio_effect",
        {
            "track": "A1",
            "segment_ref": "op_5",
            "name": next(iter(cc.AudioSceneEffectType)).name,
        },
        id="add_audio_effect",
    ),
    pytest.param(
        "add_text_animation",
        {
            "track": "T1",
            "segment_ref": "op_6",
            "role": "intro",
            "name": next(iter(cc.TextIntro)).name,
            "duration": "100ms",
        },
        id="add_text_animation",
    ),
]


@pytest.mark.parametrize("op_name,args", REFERENCE_CASES)
def test_saved_draft_has_only_the_known_text_speed_dangling_ref(
    tmp_path, op_name: str | None, args: dict[str, Any] | None
) -> None:
    """The upstream text speed ref remains; modifier ops must not add another."""
    runner = CliRunner()
    session_path, drafts = _build_baseline(runner, tmp_path, f"refs-{op_name or 'baseline'}")
    if op_name is not None:
        Session.load(session_path).append_operation(op_name, args or {})

    draft = _save_draft(runner, session_path, drafts)

    assert len(_dangling_extra_material_refs(draft)) == 1


def test_review_reports_dangling_extra_material_ref(tmp_path) -> None:
    runner = CliRunner()
    session_path, _ = _build_baseline(runner, tmp_path, "refs-review")

    result = runner.invoke(
        cli,
        ["--json", "review", "-p", str(session_path), "--only", "references"],
        env={"CAPCUT_NO_STAGING": "1"},
    )

    assert result.exit_code == 0, result.output
    findings = json.loads(result.output)["findings"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["check"] == "references"
    assert finding["severity"] == "warning"
    assert "extra_material_refs" in finding["message"]
    assert finding["location"]["track"] == "T1"
    assert finding["location"]["ref_id"]
