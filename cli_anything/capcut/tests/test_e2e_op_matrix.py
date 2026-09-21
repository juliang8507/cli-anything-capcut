"""CLI -> replay -> save op wiring matrix.

Each case saves the same six-op baseline first, appends exactly one operation
through Click's real CLI entry point, saves again, and compares the resulting
``draft_content.json`` values.
"""

from __future__ import annotations

import json
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import cli_anything
import cli_anything.capcut as capcut_package
from cli_anything.capcut.capcut_cli import cli


Draft = dict[str, Any]
DeltaAssertion = Callable[[Draft, Draft, Path], None]


class UnsupportedReplayWiring(AssertionError):
    """The known R1 failure: replay has no handler for a postprocess op."""


@pytest.fixture(scope="session", autouse=True)
def _assert_testing_this_checkout() -> None:
    """Fail before any E2E work if imports resolve outside this checkout."""
    repository_root = Path(__file__).resolve().parents[3]
    # cli_anything is a PEP 420 namespace package in this repository, so
    # __file__ is None on supported Python versions.  In that case the concrete
    # capcut package file is the equivalent import fingerprint.
    package_file = cli_anything.__file__ or capcut_package.__file__
    assert package_file is not None
    resolved_package_file = Path(package_file).resolve()
    assert repository_root == resolved_package_file or repository_root in resolved_package_file.parents, (
        "cli_anything was imported from a different checkout: "
        f"{resolved_package_file} (expected under {repository_root})"
    )


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


def _write_media_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create parser-valid tiny media without invoking ffmpeg."""
    pymediainfo = pytest.importorskip("pymediainfo")
    if not pymediainfo.MediaInfo.can_parse():
        pytest.skip("pymediainfo cannot load its native MediaInfo library")

    # MediaInfo recognizes the content as a still image; VideoMaterial accepts
    # it, while the .mp4 name keeps this on the requested `video add` CLI path.
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
            "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
            "49454e44ae426082"
        )
    )

    # MediaInfo detects the WAV container by content despite the requested
    # .mp3 filename.  Five seconds of silence is only 80 KiB.
    audio_path = tmp_path / "audio.mp3"
    with wave.open(str(audio_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        wav_file.writeframes(b"\x00\x00" * 40_000)

    return video_path, audio_path


def _build_baseline(runner: CliRunner, tmp_path: Path, name: str) -> tuple[Path, Path]:
    drafts = (tmp_path / "drafts").resolve()
    session_path = (tmp_path / "s.json").resolve()
    video_path, audio_path = _write_media_files(tmp_path)

    _invoke_json(
        runner,
        [
            "project",
            "new",
            "--name",
            name,
            "--preset",
            "9x16",
            "--draft-folder",
            str(drafts),
            "-o",
            str(session_path),
        ],
    )

    commands_and_ids = [
        (["track", "add", "--type", "video", "--name", "V1"], "op_1"),
        (["track", "add", "--type", "audio", "--name", "A1"], "op_2"),
        (["track", "add", "--type", "text", "--name", "T1"], "op_3"),
        (
            [
                "video",
                "add",
                "-f",
                str(video_path),
                "-s",
                "0s",
                "-d",
                "5s",
                "--track",
                "V1",
            ],
            "op_4",
        ),
        (
            [
                "audio",
                "add",
                "-f",
                str(audio_path),
                "-s",
                "0s",
                "-d",
                "5s",
                "--track",
                "A1",
            ],
            "op_5",
        ),
        (
            [
                "text",
                "add",
                "-t",
                "감사",
                "-s",
                "0s",
                "-d",
                "3s",
                "--track",
                "T1",
            ],
            "op_6",
        ),
    ]
    for command, expected_id in commands_and_ids:
        result = _invoke_json(
            runner,
            [*command[:2], "-p", str(session_path), *command[2:]],
        )
        assert result["id"] == expected_id

    return session_path, drafts


def _save_draft(
    runner: CliRunner,
    session_path: Path,
    drafts: Path,
    *,
    unsupported_op: str | None = None,
) -> Draft:
    result = runner.invoke(
        cli,
        ["--json", "save", "-p", str(session_path)],
        env={"CAPCUT_NO_STAGING": "1"},
    )
    if result.exit_code != 0 and unsupported_op is not None:
        expected_error = f"지원하지 않는 op: {unsupported_op}"
        if expected_error in result.output:
            raise UnsupportedReplayWiring(result.output)
    assert result.exit_code == 0, (
        f"save failed (exit={result.exit_code}):\n{result.output}"
    )

    draft_content_path = Path(json.loads(result.output)["draft_content_json"]).resolve()
    assert drafts == draft_content_path or drafts in draft_content_path.parents, (
        f"draft escaped tmp_path isolation: {draft_content_path}"
    )
    return json.loads(draft_content_path.read_text(encoding="utf-8"))


def _video_segment(draft: Draft) -> dict[str, Any]:
    track = next(track for track in draft["tracks"] if track.get("name") == "V1")
    return track["segments"][0]


def _linked_speed_material(draft: Draft) -> dict[str, Any]:
    refs = set(_video_segment(draft).get("extra_material_refs", []))
    return next(material for material in draft["materials"]["speeds"] if material["id"] in refs)


def _assert_color_adjust(before: Draft, after: Draft, _: Path) -> None:
    before_value = _video_segment(before).get("color_adjust", {}).get("brightness")
    after_value = _video_segment(after)["color_adjust"]["brightness"]
    assert after_value == pytest.approx(0.3)
    assert after_value != before_value


def _assert_text_style_patch(before: Draft, after: Draft, _: Path) -> None:
    expected = "7044878305576620546"
    before_value = before["materials"]["texts"][0].get("font_resource_id")
    after_value = after["materials"]["texts"][0]["font_resource_id"]
    assert after_value == expected
    assert after_value != before_value


def _assert_keyframe_added(before: Draft, after: Draft, _: Path) -> None:
    before_keyframes = _video_segment(before).get("common_keyframes", [])
    after_keyframes = _video_segment(after).get("common_keyframes", [])
    assert len(after_keyframes) > len(before_keyframes)
    alpha = next(item for item in after_keyframes if item["property_type"] == "KFTypeAlpha")
    keyframe = alpha["keyframe_list"][0]
    assert keyframe["time_offset"] == 1_000_000
    assert keyframe["values"][0] == pytest.approx(0.5)


def _assert_reverse(before: Draft, after: Draft, _: Path) -> None:
    assert _video_segment(before).get("reverse") is not True
    assert _video_segment(after)["reverse"] is True


def _assert_freeze_frame(before: Draft, after: Draft, _: Path) -> None:
    assert _linked_speed_material(before).get("mode") != "freeze"
    after_speed = _linked_speed_material(after)
    assert after_speed["mode"] == "freeze"
    assert after_speed["speed"] == pytest.approx(0.0)


def _assert_blend_mode(before: Draft, after: Draft, _: Path) -> None:
    # pycapcut은 새 세그먼트의 track_attribute를 dict가 아니라 int로 만든다.
    # 그래서 before 쪽은 dict라고 가정하고 읽으면 AttributeError가 난다 —
    # postprocess가 고쳐야 했던 것과 똑같은 함정이므로 여기서도 타입을 확인한다.
    before_attribute = _video_segment(before).get("track_attribute")
    before_value = (
        before_attribute.get("blend_mode")
        if isinstance(before_attribute, dict)
        else before_attribute
    )
    after_value = _video_segment(after)["track_attribute"]["blend_mode"]
    assert isinstance(after_value, int)
    assert after_value == 2  # screen
    assert after_value != before_value


def _assert_chroma_key(before: Draft, after: Draft, _: Path) -> None:
    before_materials = before["materials"].get("video_chromakeys", [])
    after_materials = after["materials"]["video_chromakeys"]
    assert len(after_materials) == len(before_materials) + 1
    assert after_materials[0]["color"] == "#00FF00"
    assert after_materials[0]["intensity"] == pytest.approx(0.5)


def _assert_lut(before: Draft, after: Draft, lut_file: Path) -> None:
    before_materials = before["materials"].get("video_luts", [])
    after_materials = after["materials"]["video_luts"]
    assert len(after_materials) == len(before_materials) + 1
    lut = after_materials[0]
    assert lut["file"] == str(lut_file)
    assert lut["intensity"] == pytest.approx(1.0)
    assert lut["name"] == "Custom LUT"
    assert lut["type"] == "lut"


def _assert_speed_curve(before: Draft, after: Draft, _: Path) -> None:
    assert _linked_speed_material(before).get("mode") != "curve"
    speed = _linked_speed_material(after)
    assert speed["mode"] == "curve"
    assert speed["curve_speed"]["points"] == [
        {"x": 0.0, "y": 1.0},
        {"x": 0.5, "y": 2.0},
        {"x": 1.0, "y": 1.0},
    ]


def _assert_color_curves(before: Draft, after: Draft, _: Path) -> None:
    before_materials = before["materials"].get("color_curves", [])
    after_materials = after["materials"]["color_curves"]
    assert len(after_materials) == len(before_materials) + 1
    assert after_materials[0]["rgb_points"] == [
        {"x": 0.0, "y": 0.0},
        {"x": 0.5, "y": 0.7},
        {"x": 1.0, "y": 1.0},
    ]


def _assert_hsl_adjust(before: Draft, after: Draft, _: Path) -> None:
    before_materials = before["materials"].get("material_colors", [])
    after_materials = after["materials"]["material_colors"]
    assert len(after_materials) == len(before_materials) + 1
    red = after_materials[0]["adjusts"]["red"]
    assert red["hue"] == pytest.approx(0.1)
    assert red["saturation"] == pytest.approx(-0.2)


SUPPORTED_CASES = [
    (
        "color_adjust",
        ["color", "adjust", "--track", "V1", "--segment-ref", "op_4", "--brightness", "0.3"],
        _assert_color_adjust,
    ),
    (
        "text_style_patch",
        [
            "text",
            "style-patch",
            "--track",
            "T1",
            "--segment-ref",
            "op_6",
            "--font-resource-id",
            "7044878305576620546",
        ],
        _assert_text_style_patch,
    ),
    (
        "add_keyframe",
        [
            "keyframe",
            "add",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--property",
            "alpha",
            "--time",
            "1s",
            "--value",
            "0.5",
        ],
        _assert_keyframe_added,
    ),
]


@pytest.mark.parametrize("op_name,command,assert_delta", SUPPORTED_CASES, ids=lambda value: value if isinstance(value, str) else None)
def test_supported_op_changes_saved_draft(
    tmp_path: Path,
    op_name: str,
    command: list[str],
    assert_delta: DeltaAssertion,
) -> None:
    runner = CliRunner()
    session_path, drafts = _build_baseline(runner, tmp_path, f"e2e-{op_name}")
    before = _save_draft(runner, session_path, drafts)

    _invoke_json(runner, [*command[:2], "-p", str(session_path), *command[2:]])
    after = _save_draft(runner, session_path, drafts)

    assert_delta(before, after, tmp_path / "unused.cube")


MISSING_WIRING_CASES = [
    ("set_reverse", ["video", "reverse", "--track", "V1", "--segment-ref", "op_4"], _assert_reverse),
    (
        "set_freeze_frame",
        [
            "video",
            "freeze-frame",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--duration",
            "1s",
        ],
        _assert_freeze_frame,
    ),
    (
        "set_blend_mode",
        ["video", "blend-mode", "--track", "V1", "--segment-ref", "op_4", "--mode", "screen"],
        _assert_blend_mode,
    ),
    (
        "set_chroma_key",
        [
            "video",
            "chroma-key",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--color",
            "#00FF00",
            "--intensity",
            "0.5",
        ],
        _assert_chroma_key,
    ),
    (
        "add_lut",
        ["video", "lut", "--track", "V1", "--segment-ref", "op_4", "--file", "{lut_file}"],
        _assert_lut,
    ),
    (
        "set_speed_curve",
        [
            "video",
            "speed-curve",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--points",
            "0,1;0.5,2;1,1",
        ],
        _assert_speed_curve,
    ),
    (
        "add_color_curves",
        [
            "color",
            "curves",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--rgb",
            "0,0;0.5,0.7;1,1",
        ],
        _assert_color_curves,
    ),
    (
        "add_hsl_adjust",
        [
            "color",
            "hsl",
            "--track",
            "V1",
            "--segment-ref",
            "op_4",
            "--target",
            "red",
            "--hue",
            "10",
            "--saturation",
            "-20",
        ],
        _assert_hsl_adjust,
    ),
]


@pytest.mark.parametrize(
    "op_name,command,assert_delta",
    [
        pytest.param(op_name, command, assertion, id=op_name)
        for op_name, command, assertion in MISSING_WIRING_CASES
    ],
)
def test_postprocess_op_changes_saved_draft_after_replay_wiring(
    tmp_path: Path,
    op_name: str,
    command: list[str],
    assert_delta: DeltaAssertion,
) -> None:
    runner = CliRunner()
    session_path, drafts = _build_baseline(runner, tmp_path, f"e2e-{op_name}")
    before = _save_draft(runner, session_path, drafts)

    lut_file = (tmp_path / "identity.cube").resolve()
    lut_file.write_text(
        'TITLE "identity"\nLUT_3D_SIZE 2\n0 0 0\n0 0 1\n0 1 0\n0 1 1\n'
        "1 0 0\n1 0 1\n1 1 0\n1 1 1\n",
        encoding="ascii",
    )
    resolved_command = [part.format(lut_file=str(lut_file)) for part in command]
    _invoke_json(
        runner,
        [*resolved_command[:2], "-p", str(session_path), *resolved_command[2:]],
    )
    after = _save_draft(
        runner,
        session_path,
        drafts,
        unsupported_op=op_name,
    )

    assert_delta(before, after, lut_file)
