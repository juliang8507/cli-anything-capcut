"""CapCut draft_content.json -> 분석용 session JSON 역변환 테스트."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.time_utils import parse_time_value


_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
    "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
    "49454e44ae426082"
)


def _invoke_json(
    runner: CliRunner,
    args: list[str],
    *,
    expected_codes: tuple[int, ...] = (0,),
) -> dict:
    result = runner.invoke(
        cli,
        ["--json", *args],
        obj={},
        env={"CAPCUT_NO_STAGING": "1"},
    )
    assert result.exit_code in expected_codes, result.output
    assert result.exception is None or result.exit_code in expected_codes[1:], result.output
    return json.loads(result.output)


def _make_video(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("round-trip video fixture requires ffmpeg")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=3",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        pytest.skip(f"ffmpeg video fixture failed: {completed.stderr[-500:]}")
    return path


def _make_audio(path: Path) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\x00\x00" * 8_000 * 3)
    return path


def _segment_ops(data: dict) -> list[dict]:
    supported = {"add_video", "add_image", "add_audio", "add_text"}
    return [operation for operation in data["operations"] if operation["op"] in supported]


def test_session_draft_session_round_trip_and_analysis_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    draft_root = tmp_path / "drafts"
    draft_root.mkdir()
    source_session_path = tmp_path / "source.session.json"
    imported_session_path = tmp_path / "imported.session.json"

    video = _make_video(tmp_path / "clip.mp4")
    image = tmp_path / "still.png"
    image.write_bytes(_PNG_BYTES)
    audio = _make_audio(tmp_path / "music.wav")

    _invoke_json(
        runner,
        [
            "project",
            "new",
            "--name",
            "source-mv",
            "--width",
            "1280",
            "--height",
            "720",
            "--fps",
            "30",
            "--draft-folder",
            str(draft_root),
            "--output",
            str(source_session_path),
        ],
    )
    for track_type, name in (("video", "V1"), ("audio", "A1"), ("text", "lyrics")):
        _invoke_json(
            runner,
            ["track", "add", "-p", str(source_session_path), "--type", track_type, "--name", name],
        )

    _invoke_json(
        runner,
        [
            "video",
            "add",
            "-p",
            str(source_session_path),
            "-f",
            str(video),
            "--start",
            "0s",
            "--duration",
            "1s",
            "--track",
            "V1",
            "--volume",
            "0.8",
        ],
    )
    _invoke_json(
        runner,
        [
            "image",
            "add",
            "-p",
            str(source_session_path),
            "-f",
            str(image),
            "--start",
            "1s",
            "--duration",
            "1.5s",
            "--track",
            "V1",
        ],
    )
    _invoke_json(
        runner,
        [
            "audio",
            "add",
            "-p",
            str(source_session_path),
            "-f",
            str(audio),
            "--start",
            "0s",
            "--duration",
            "2.5s",
            "--track",
            "A1",
            "--volume",
            "0.6",
        ],
    )
    _invoke_json(
        runner,
        [
            "text",
            "add",
            "-p",
            str(source_session_path),
            "--text",
            "한글 가사 보존",
            "--start",
            "500ms",
            "--duration",
            "1.25s",
            "--track",
            "lyrics",
            "--size",
            "12",
            "--color",
            "0.2,0.4,0.6",
        ],
    )

    saved = _invoke_json(runner, ["save", "-p", str(source_session_path)])
    draft_json = Path(saved["draft_content_json"])
    imported = _invoke_json(
        runner,
        ["import-draft", "--from", str(draft_json.parent), "-o", str(imported_session_path)],
    )

    source_data = json.loads(source_session_path.read_text(encoding="utf-8"))
    imported_data = json.loads(imported_session_path.read_text(encoding="utf-8"))

    source_tracks = [op for op in source_data["operations"] if op["op"] == "add_track"]
    imported_tracks = [op for op in imported_data["operations"] if op["op"] == "add_track"]
    assert [op["args"] for op in imported_tracks] == [op["args"] for op in source_tracks]
    assert imported_data["operations"][: len(imported_tracks)] == imported_tracks

    source_segments = _segment_ops(source_data)
    imported_segments = _segment_ops(imported_data)
    assert [op["op"] for op in imported_segments] == [op["op"] for op in source_segments]
    assert len(imported_segments) == 4
    for source_op, imported_op in zip(source_segments, imported_segments):
        source_args = source_op["args"]
        imported_args = imported_op["args"]
        assert imported_args["file"] == source_args["file"] if "file" in source_args else True
        assert imported_args["track"] == source_args["track"]
        assert parse_time_value(imported_args["start"]) == parse_time_value(source_args["start"])
        assert parse_time_value(imported_args["duration"]) == parse_time_value(source_args["duration"])

    imported_video = next(op for op in imported_segments if op["op"] == "add_video")
    assert imported_video["args"]["speed"] == pytest.approx(1.0)
    assert imported_video["args"]["volume"] == pytest.approx(0.8)
    imported_audio = next(op for op in imported_segments if op["op"] == "add_audio")
    assert imported_audio["args"]["volume"] == pytest.approx(0.6)
    imported_text = next(op for op in imported_segments if op["op"] == "add_text")
    assert imported_text["args"]["text"] == "한글 가사 보존"
    assert imported_text["args"]["size"] == pytest.approx(12.0)
    assert imported_text["args"]["color"] == pytest.approx([0.2, 0.4, 0.6])

    assert imported_data["width"] == 1280
    assert imported_data["height"] == 720
    assert imported_data["fps"] == 30
    assert imported_data["lossy"] is True
    assert imported_data["imported_from"] == str(draft_json.resolve())
    assert "분석용" in imported_data["import_note_ko"]
    assert Path(imported_data["draft_folder"]) == imported_session_path.parent / "imported_drafts"
    assert imported_data["draft_name"] == "source-mv-imported"
    assert "분석용" in imported["notice_ko"]
    assert "save" in imported["notice_ko"]
    assert imported["track_count"] == 3
    assert imported["segment_count"] == 4

    stats = _invoke_json(runner, ["stats", "-p", str(imported_session_path)])
    timeline = _invoke_json(runner, ["timeline", "-p", str(imported_session_path)])
    review = _invoke_json(runner, ["review", "-p", str(imported_session_path)])
    assert stats["operation_count"] == 7
    assert "timeline_text" in timeline
    assert "status" in review


def test_missing_material_and_unrestored_features_are_reported(tmp_path: Path) -> None:
    runner = CliRunner()
    image = tmp_path / "still.png"
    image.write_bytes(_PNG_BYTES)
    draft_folder = tmp_path / "existing-mv"
    draft_folder.mkdir()
    draft_json = draft_folder / "draft_content.json"
    draft_json.write_text(
        json.dumps(
            {
                "canvas_config": {"width": 1080, "height": 1920, "ratio": "9:16"},
                "fps": 30.0,
                "duration": 2_000_000,
                "tracks": [
                    {
                        "type": "video",
                        "name": "V1",
                        "segments": [
                            {
                                "id": "seg-photo",
                                "material_id": "photo-1",
                                "target_timerange": {"start": 0, "duration": 2_000_000},
                                "source_timerange": {"start": 0, "duration": 2_000_000},
                                "extra_material_refs": ["speed-1", "mask-1"],
                            },
                            {
                                "id": "seg-video",
                                "material_id": "video-1",
                                "target_timerange": {"start": 2_000_000, "duration": 800_000},
                                "source_timerange": {"start": 0, "duration": 1_000_000},
                                "speed": 1.25,
                                "volume": 0.75,
                                "extra_material_refs": ["speed-2"],
                            },
                            {
                                "id": "seg-missing",
                                "material_id": "does-not-exist",
                                "target_timerange": {"start": 3_000_000, "duration": 1_000_000},
                                "extra_material_refs": [],
                            },
                        ],
                    },
                    {
                        "type": "effect",
                        "name": "FX1",
                        "segments": [
                            {
                                "id": "seg-effect",
                                "material_id": "effect-1",
                                "target_timerange": {"start": 0, "duration": 1_000_000},
                                "extra_material_refs": [],
                            }
                        ],
                    },
                ],
                "materials": {
                    "videos": [
                        {"id": "photo-1", "path": str(image), "type": "photo", "duration": 2_000_000},
                        {"id": "video-1", "path": str(tmp_path / "clip.mp4"), "type": "video", "duration": 1_000_000},
                    ],
                    "audios": [],
                    "texts": [],
                    "speeds": [
                        {"id": "speed-1", "speed": 1.0},
                        {"id": "speed-2", "speed": 1.25},
                    ],
                    "masks": [{"id": "mask-1", "type": "mask"}],
                    "video_effects": [{"id": "effect-1", "type": "video_effect"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = tmp_path / "result.session.json"
    explicit_draft_folder = tmp_path / "chosen-drafts"
    result = _invoke_json(
        runner,
        [
            "import-draft",
            "--from",
            str(draft_json),
            "-o",
            str(output),
            "--draft-folder",
            str(explicit_draft_folder),
        ],
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["draft_folder"] == str(explicit_draft_folder)
    assert data["draft_name"] == "existing-mv-imported"
    assert [op["op"] for op in data["operations"]] == [
        "add_track",
        "add_track",
        "add_image",
        "add_video",
    ]
    imported_video = data["operations"][-1]
    assert imported_video["args"]["speed"] == pytest.approx(1.25)
    assert imported_video["args"]["volume"] == pytest.approx(0.75)
    assert any("does-not-exist" in warning for warning in result["warnings"])
    assert result["unsupported_segments"] == {"effect": 1}

    refs = result["extra_material_refs"]
    assert refs["segment_count"] == 2
    assert refs["reference_count"] == 3
    assert refs["unrestored_reference_count"] == 1
    assert refs["segments"][0]["track"] == "V1"
    assert refs["segments"][0]["reference_count"] == 2
    assert refs["segments"][0]["material_types"] == ["masks", "speeds"]


def test_gui_draft_empty_track_names_are_generated_by_type_in_draft_order(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    image = tmp_path / "still.png"
    image.write_bytes(_PNG_BYTES)
    audio = _make_audio(tmp_path / "music.wav")
    draft_folder = tmp_path / "gui-project"
    draft_folder.mkdir()
    (draft_folder / "draft_content.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "type": "video",
                        "name": "",
                        "segments": [
                            {
                                "id": "seg-video-1",
                                "material_id": "photo-1",
                                "target_timerange": {"start": 0, "duration": 1_000_000},
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "name": "",
                        "segments": [
                            {
                                "id": "seg-text-1",
                                "material_id": "text-1",
                                "target_timerange": {"start": 0, "duration": 1_000_000},
                            }
                        ],
                    },
                    {
                        "type": "video",
                        "name": "",
                        "segments": [
                            {
                                "id": "seg-video-2",
                                "material_id": "photo-1",
                                "target_timerange": {"start": 1_000_000, "duration": 1_000_000},
                            }
                        ],
                    },
                    {
                        "type": "audio",
                        "name": "music",
                        "segments": [
                            {
                                "id": "seg-audio-1",
                                "material_id": "audio-1",
                                "target_timerange": {"start": 0, "duration": 2_000_000},
                            }
                        ],
                    },
                    {"type": "effect", "name": "", "segments": []},
                    {"type": "sticker", "name": "", "segments": []},
                    {"type": "filter", "name": "", "segments": []},
                    {"type": "video", "name": "hero", "segments": []},
                ],
                "materials": {
                    "videos": [
                        {"id": "photo-1", "path": str(image), "type": "photo"},
                    ],
                    "audios": [{"id": "audio-1", "path": str(audio)}],
                    "texts": [{"id": "text-1", "content": {"text": "가사"}}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = tmp_path / "named.session.json"
    result = _invoke_json(
        runner,
        ["import-draft", "--from", str(draft_folder), "-o", str(output)],
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    track_names = [
        operation["args"]["name"]
        for operation in data["operations"]
        if operation["op"] == "add_track"
    ]

    assert track_names == ["V1", "T1", "V2", "music", "E1", "S1", "F1", "hero"]
    assert result["auto_named_track_count"] == 6
    assert result["track_name_notice_ko"] == "트랙 이름이 없어 6개를 자동 명명했습니다."
    stats = _invoke_json(runner, ["stats", "-p", str(output)])
    assert stats["tracks"] == {"V1": 1, "T1": 1, "V2": 1, "music": 1}
    assert "_default_" not in stats["tracks"]


def test_gui_draft_placeholder_media_paths_are_resolved_and_missing_files_warn(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    draft_folder = tmp_path / "gui-project"
    local_media = draft_folder / "materials" / "video" / "우리의 Sunny Day 앨범 커버.png"
    local_media.parent.mkdir(parents=True)
    local_media.write_bytes(_PNG_BYTES)
    missing_media = draft_folder / "materials" / "video" / "missing.png"
    absolute_media = "C:/Users/test/Cache/music/song.mp3"
    placeholder = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"
    (draft_folder / "draft_content.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "type": "video",
                        "name": "V1",
                        "segments": [
                            {
                                "id": "seg-local",
                                "material_id": "photo-local",
                                "target_timerange": {"start": 0, "duration": 1_000_000},
                            },
                            {
                                "id": "seg-missing",
                                "material_id": "photo-missing",
                                "target_timerange": {"start": 1_000_000, "duration": 1_000_000},
                            },
                        ],
                    },
                    {
                        "type": "audio",
                        "name": "A1",
                        "segments": [
                            {
                                "id": "seg-absolute",
                                "material_id": "audio-absolute",
                                "target_timerange": {"start": 0, "duration": 2_000_000},
                            }
                        ],
                    },
                ],
                "materials": {
                    "videos": [
                        {
                            "id": "photo-local",
                            "path": f"{placeholder}/materials/video/{local_media.name}",
                            "type": "photo",
                        },
                        {
                            "id": "photo-missing",
                            "path": f"{placeholder}/materials/video/{missing_media.name}",
                            "type": "photo",
                        },
                    ],
                    "audios": [{"id": "audio-absolute", "path": absolute_media}],
                    "texts": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = tmp_path / "resolved.session.json"
    result = _invoke_json(
        runner,
        ["import-draft", "--from", str(draft_folder), "-o", str(output)],
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    media_files = [
        operation["args"]["file"]
        for operation in data["operations"]
        if "file" in operation["args"]
    ]

    assert media_files == [str(local_media.resolve()), str(missing_media.resolve()), absolute_media]
    assert all("##_draftpath_placeholder_" not in path for path in media_files)
    assert any(str(missing_media.resolve()) in warning for warning in result["warnings"])
    assert not any(absolute_media in warning for warning in result["warnings"])
