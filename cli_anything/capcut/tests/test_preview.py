"""preview 커맨드 유닛 테스트.

pytest로 실행::

    python -m pytest cli_anything/capcut/tests/test_preview.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cli_anything.capcut.commands import preview as _pv
from cli_anything.capcut.commands.preview import (
    _collect_segments,
    _compute_gaps_overlaps,
    _render_gantt_svg,
    build_preview_html,
)
from cli_anything.capcut.core.session import Session


# =========================================================================
# fixtures
# =========================================================================


@pytest.fixture
def empty_session(tmp_path):
    return Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="empty",
        width=1920,
        height=1080,
        fps=30,
        output=tmp_path / "empty.session.json",
    )


@pytest.fixture
def sample_session(tmp_path):
    """V1 비디오 트랙에 세그먼트 3개가 들어간 세션."""
    s = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="sample",
        width=1920,
        height=1080,
        fps=30,
        output=tmp_path / "sample.session.json",
    )
    s.append_operation("add_track", {"type": "video", "name": "V1"})
    s.append_operation("add_track", {"type": "audio", "name": "A1"})
    # V1: 3개 세그먼트, 가운데에 갭 하나
    s.append_operation(
        "add_image",
        {"file": "clip_a.png", "start": "0s", "duration": "2s", "track": "V1"},
    )
    s.append_operation(
        "add_image",
        {"file": "clip_b.png", "start": "3s", "duration": "2s", "track": "V1"},
    )
    s.append_operation(
        "add_image",
        {"file": "clip_c.png", "start": "5s", "duration": "2s", "track": "V1"},
    )
    # A1: 하나
    s.append_operation(
        "add_audio",
        {"file": "bgm.mp3", "start": "0s", "duration": "7s", "track": "A1"},
    )
    return s


@pytest.fixture
def overlap_session(tmp_path):
    """V1에 겹치는 세그먼트 2개."""
    s = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="olap",
        width=1920,
        height=1080,
        fps=30,
        output=tmp_path / "olap.session.json",
    )
    s.append_operation("add_track", {"type": "video", "name": "V1"})
    s.append_operation(
        "add_image",
        {"file": "a.png", "start": "0s", "duration": "5s", "track": "V1"},
    )
    s.append_operation(
        "add_image",
        {"file": "b.png", "start": "3s", "duration": "4s", "track": "V1"},
    )
    return s


# =========================================================================
# _collect_segments
# =========================================================================


class TestCollectSegments:
    def test_empty_session_returns_empty(self, empty_session):
        assert _collect_segments(empty_session) == []

    def test_sample_session_three_v1_and_one_a1(self, sample_session):
        segs = _collect_segments(sample_session)
        assert len(segs) == 4
        v1 = [s for s in segs if s["track"] == "V1"]
        a1 = [s for s in segs if s["track"] == "A1"]
        assert len(v1) == 3
        assert len(a1) == 1

    def test_segment_has_expected_keys(self, sample_session):
        seg = _collect_segments(sample_session)[0]
        for key in ("op", "op_id", "track", "type", "color", "start_us", "end_us", "duration_us", "file"):
            assert key in seg

    def test_skips_non_creation_ops(self, sample_session):
        # add_track은 CREATION_OPS 가 아님
        ops = sample_session.data["operations"]
        track_ops = [o for o in ops if o["op"] == "add_track"]
        assert len(track_ops) == 2  # 세션에 두 개 기록됨
        segs = _collect_segments(sample_session)
        assert not any(s["op"] == "add_track" for s in segs)


# =========================================================================
# _compute_gaps_overlaps
# =========================================================================


class TestGapsOverlaps:
    def test_sample_gap_detected(self, sample_session):
        segs = _collect_segments(sample_session)
        gaps, overlaps = _compute_gaps_overlaps(segs)
        # V1에 2s~3s 갭이 있음
        assert any(g["track"] == "V1" and g["gap_us"] == 1_000_000 for g in gaps)
        assert overlaps == []
        # segments에 overlap flag 주입되었지만 전부 False여야
        assert all(not s["overlap"] for s in segs)

    def test_overlap_detected(self, overlap_session):
        segs = _collect_segments(overlap_session)
        gaps, overlaps = _compute_gaps_overlaps(segs)
        assert len(overlaps) == 1
        assert overlaps[0]["overlap_us"] == 2_000_000
        # 두 세그 모두 overlap 플래그
        v1_segs = [s for s in segs if s["track"] == "V1"]
        assert all(s["overlap"] for s in v1_segs)


# =========================================================================
# _render_gantt_svg
# =========================================================================


class TestRenderGantt:
    def test_empty_still_produces_svg(self):
        svg = _render_gantt_svg([], total_us=0, tracks=[])
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_three_segments_produce_three_plus_rects(self, sample_session):
        segs = _collect_segments(sample_session)
        _compute_gaps_overlaps(segs)
        tracks = sorted({s["track"] for s in segs})
        total = max(s["end_us"] for s in segs)
        svg = _render_gantt_svg(segs, total, tracks)
        # 세그먼트마다 <rect> 하나 이상 — 배경/트랙 행/갭 빗금도 rect를 쓰므로 총 개수는
        # 세그 수보다 많음. 세그먼트가 4개 이상이면 rect 4개 이상.
        n_rects = svg.count("<rect")
        assert n_rects >= 4
        # 세그먼트 <g class="seg"> 는 정확히 세그 수만큼
        assert svg.count('class="seg"') == len(segs)

    def test_overlap_gets_red_stroke(self, overlap_session):
        segs = _collect_segments(overlap_session)
        _compute_gaps_overlaps(segs)
        total = max(s["end_us"] for s in segs)
        svg = _render_gantt_svg(segs, total, ["V1"])
        # 빨간 stroke가 있어야
        assert "#ef4444" in svg


# =========================================================================
# build_preview_html
# =========================================================================


class TestBuildPreviewHtml:
    def test_empty_session_still_valid_html(self, empty_session):
        html = build_preview_html(empty_session, include_thumbs=False)
        assert html.startswith("<!DOCTYPE html>")
        assert "<svg" in html
        assert "</html>" in html.rstrip()
        # 외부 CDN/리소스가 없어야 — script src / link href / img src 로 http(s) 참조 금지.
        # SVG xmlns 속성(http://www.w3.org/...)은 정상이므로 속성 패턴 기반으로 검사.
        for forbidden in ('src="http', "src='http", 'href="http', "href='http"):
            assert forbidden not in html, f"external resource found: {forbidden}"

    def test_sample_html_mentions_file_names(self, sample_session):
        html = build_preview_html(sample_session, include_thumbs=False)
        # 파일명이 세그먼트 테이블에 그대로 등장
        assert "clip_a.png" in html
        assert "clip_b.png" in html
        assert "clip_c.png" in html
        assert "bgm.mp3" in html

    def test_thumbs_false_does_not_call_ffmpeg(self, sample_session, monkeypatch):
        called = {"n": 0}

        def fake_run(*args, **kwargs):  # pragma: no cover - should not be called
            called["n"] += 1
            raise AssertionError("subprocess.run should not be called when thumbs=False")

        monkeypatch.setattr(_pv.subprocess, "run", fake_run)
        # shutil.which도 건드려서 우연히 호출되는 것을 잡음
        monkeypatch.setattr(_pv.shutil, "which", lambda *_a, **_k: None)
        html = build_preview_html(sample_session, include_thumbs=False)
        assert called["n"] == 0
        assert html

    def test_overlap_session_marks_overlap_in_table(self, overlap_session):
        html = build_preview_html(overlap_session, include_thumbs=False)
        assert "OVERLAP" in html

    def test_header_shows_resolution_and_fps(self, sample_session):
        html = build_preview_html(sample_session, include_thumbs=False)
        assert "1920" in html and "1080" in html
        assert "30" in html  # fps


# =========================================================================
# preview 파일 저장 (click 커맨드 경유 없이 HTML 출력 검증)
# =========================================================================


class TestPreviewFileOutput:
    def test_written_file_is_nonempty(self, sample_session, tmp_path):
        html = build_preview_html(sample_session, include_thumbs=False)
        out = tmp_path / "x.preview.html"
        out.write_text(html, encoding="utf-8")
        assert out.exists()
        assert out.stat().st_size > 0

    def test_thumbs_flag_ignored_when_ffmpeg_missing(self, sample_session, monkeypatch, capsys):
        """ffmpeg 없으면 --thumbs 켜도 경고 후 진행, stdout은 깨끗."""
        monkeypatch.setattr(_pv.shutil, "which", lambda *_a, **_k: None)
        html = build_preview_html(sample_session, include_thumbs=True)
        assert html
        # click.echo(..., err=True)이므로 stderr에만 경고가 나감
        captured = capsys.readouterr()
        assert "ffmpeg" in captured.err.lower()
        assert captured.out == ""


# =========================================================================
# Click 커맨드 통합 (CliRunner)
# =========================================================================


class TestPreviewCliCommand:
    def test_cli_runner_creates_html_file(self, sample_session, tmp_path):
        from click.testing import CliRunner

        out = tmp_path / "result.html"
        runner = CliRunner()
        # preview_cmd는 ctx.obj["json"]을 참조 — obj로 주입
        result = runner.invoke(
            _pv.preview_cmd,
            [
                "-p", str(sample_session.path),
                "-o", str(out),
                "--no-thumbs",
            ],
            obj={"json": False},
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "<svg" in content
