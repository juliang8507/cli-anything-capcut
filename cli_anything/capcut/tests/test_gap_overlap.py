"""gap-detect / overlap-detect 트랙 경계 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.session import Session


def _session_with_segments(tmp_path: Path, segments: list[dict[str, Any]]) -> Session:
    session = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="gap-overlap",
        output=tmp_path / "gap-overlap.session.json",
    )
    session.append_operation("add_track", {"type": "video", "name": "V1"})
    session.append_operation("add_track", {"type": "audio", "name": "A1"})
    for segment in segments:
        session.append_operation(segment["op"], segment["args"])
    return session


def _detect(session: Session, command: str, track: str | None = None) -> list[dict]:
    args = ["--json", command, "-p", str(session.path)]
    if track is not None:
        args.extend(["--track", track])
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_gap_detect_without_track_reports_each_tracks_gap(tmp_path: Path) -> None:
    session = _session_with_segments(
        tmp_path,
        [
            {
                "op": "add_video",
                "args": {"file": "v1.mp4", "start": "0s", "duration": "5s", "track": "V1"},
            },
            {
                "op": "add_audio",
                "args": {"file": "a1.mp3", "start": "0s", "duration": "11s", "track": "A1"},
            },
            {
                "op": "add_video",
                "args": {"file": "v2.mp4", "start": "7s", "duration": "4s", "track": "V1"},
            },
        ],
    )

    assert _detect(session, "gap-detect") == [
        {
            "track": "V1",
            "start_us": 5_000_000,
            "end_us": 7_000_000,
            "gap_us": 2_000_000,
            "gap_human": "2.00s",
        }
    ]


def test_gap_detect_with_track_reports_only_that_tracks_gap(tmp_path: Path) -> None:
    session = _session_with_segments(
        tmp_path,
        [
            {
                "op": "add_video",
                "args": {"file": "v1.mp4", "start": "0s", "duration": "5s", "track": "V1"},
            },
            {
                "op": "add_audio",
                "args": {"file": "a1.mp3", "start": "0s", "duration": "11s", "track": "A1"},
            },
            {
                "op": "add_video",
                "args": {"file": "v2.mp4", "start": "7s", "duration": "4s", "track": "V1"},
            },
        ],
    )

    assert _detect(session, "gap-detect", "V1") == [
        {
            "start_us": 5_000_000,
            "end_us": 7_000_000,
            "gap_us": 2_000_000,
            "gap_human": "2.00s",
        }
    ]


def test_overlap_detect_without_track_ignores_cross_track_playback(
    tmp_path: Path,
) -> None:
    session = _session_with_segments(
        tmp_path,
        [
            {
                "op": "add_video",
                "args": {"file": "v.mp4", "start": "0s", "duration": "11s", "track": "V1"},
            },
            {
                "op": "add_audio",
                "args": {"file": "a.mp3", "start": "0s", "duration": "11s", "track": "A1"},
            },
        ],
    )

    assert _detect(session, "overlap-detect") == []


def test_overlap_detect_with_track_ignores_other_tracks(tmp_path: Path) -> None:
    session = _session_with_segments(
        tmp_path,
        [
            {
                "op": "add_video",
                "args": {"file": "v.mp4", "start": "0s", "duration": "11s", "track": "V1"},
            },
            {
                "op": "add_audio",
                "args": {"file": "a.mp3", "start": "0s", "duration": "11s", "track": "A1"},
            },
        ],
    )

    assert _detect(session, "overlap-detect", "V1") == []
    assert _detect(session, "overlap-detect", "A1") == []


def test_overlap_detect_reports_real_same_track_overlap_with_and_without_track(
    tmp_path: Path,
) -> None:
    session = _session_with_segments(
        tmp_path,
        [
            {
                "op": "add_video",
                "args": {"file": "v1.mp4", "start": "0s", "duration": "7s", "track": "V1"},
            },
            {
                "op": "add_video",
                "args": {"file": "v2.mp4", "start": "5s", "duration": "6s", "track": "V1"},
            },
            {
                "op": "add_audio",
                "args": {"file": "a.mp3", "start": "0s", "duration": "11s", "track": "A1"},
            },
        ],
    )
    expected_overlap = {
        "a": {"index": 2, "id": "op_3", "start_us": 0, "end_us": 7_000_000},
        "b": {"index": 3, "id": "op_4", "start_us": 5_000_000, "end_us": 11_000_000},
        "overlap_us": 2_000_000,
    }

    assert _detect(session, "overlap-detect", "V1") == [expected_overlap]
    assert _detect(session, "overlap-detect") == [
        {"track": "V1", **expected_overlap}
    ]
