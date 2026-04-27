"""render-headless 커맨드 테스트.

실제 ffmpeg 렌더는 ffmpeg 설치 여부에 따라 스킵.
분석/빌드 로직은 ffmpeg 없어도 검증 가능.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.commands.render_headless import (
    SUPPORTED_OPS,
    UNSUPPORTED_OPS,
    analyze_session_for_render,
    build_ffmpeg_command,
    render_headless,
    _us_to_srt_ts,
    _write_srt_for_text_segments,
)
from cli_anything.capcut.core.session import Session


FFMPEG_BIN = shutil.which("ffmpeg")
HAS_FFMPEG = FFMPEG_BIN is not None


# =========================================================================
# fixtures
# =========================================================================


@pytest.fixture
def tmp_session(tmp_path):
    return Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="headless-test",
        width=1280,
        height=720,
        fps=30,
        output=tmp_path / "test.session.json",
    )


def _make_short_video(path: Path, duration: float = 1.0, color: str = "red") -> Path:
    """ffmpeg으로 짧은 테스트 mp4 생성."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:s=320x240:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30",
            str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def _make_short_audio(path: Path, duration: float = 1.0, freq: int = 1000) -> Path:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={duration}",
            "-c:a", "libmp3lame",
            str(path),
        ],
        check=True, capture_output=True,
    )
    return path


# =========================================================================
# SRT 생성
# =========================================================================


class TestSrtHelpers:
    def test_us_to_srt_ts_zero(self):
        assert _us_to_srt_ts(0) == "00:00:00,000"

    def test_us_to_srt_ts_ms(self):
        assert _us_to_srt_ts(1_500_000) == "00:00:01,500"

    def test_us_to_srt_ts_hours(self):
        # 1h 2m 3.456s
        us = (3600 + 120 + 3) * 1_000_000 + 456_000
        assert _us_to_srt_ts(us) == "01:02:03,456"

    def test_write_srt(self, tmp_path):
        text_segs = [
            {"start_us": 0, "duration_us": 2_000_000, "text": "첫번째"},
            {"start_us": 2_000_000, "duration_us": 1_500_000, "text": "두번째\n줄바꿈"},
        ]
        p = tmp_path / "subs.srt"
        count = _write_srt_for_text_segments(text_segs, p)
        assert count == 2
        content = p.read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:02,000" in content
        assert "첫번째" in content
        assert "두번째\n줄바꿈" in content


# =========================================================================
# analyze_session_for_render
# =========================================================================


class TestAnalyzeSession:
    def test_empty_session(self, tmp_session):
        a = analyze_session_for_render(tmp_session)
        assert a["supported_segments"] == []
        assert a["unsupported_ops"] == []
        assert a["total_duration_us"] == 0

    def test_classifies_supported_video(self, tmp_session, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"fake")  # 내용 상관없음 — analyze는 존재만 확인
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V1"
        })
        a = analyze_session_for_render(tmp_session)
        assert len(a["supported_segments"]) == 2  # add_track도 SUPPORTED에 포함
        assert a["total_duration_us"] == 2_000_000
        assert a["video_tracks"] == ["V1"]
        assert a["missing_files"] == []

    def test_missing_file_detected(self, tmp_session):
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": "/nope/missing.mp4", "start": "0s", "duration": "2s", "track": "V1"
        })
        a = analyze_session_for_render(tmp_session)
        assert "/nope/missing.mp4" in a["missing_files"]

    def test_unsupported_op_detected(self, tmp_session, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V1"
        })
        # filter는 UNSUPPORTED
        tmp_session.append_operation("add_filter", {
            "name": "vignette", "start": "0s", "duration": "2s", "track": "F1"
        })
        a = analyze_session_for_render(tmp_session)
        ops_seen = [u["op"] for u in a["unsupported_ops"]]
        assert "add_filter" in ops_seen

    def test_transition_unsupported_name_warns(self, tmp_session, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V1"
        })
        # 매핑 없는 transition 이름 → fade 폴백 + 경고
        op = tmp_session.append_operation("add_video_transition", {
            "name": "unknown_fx", "segment_ref": "op_2", "track": "V1",
            "duration": "500ms",
        })
        a = analyze_session_for_render(tmp_session)
        # 경고 있어야
        assert any("unknown_fx" in w for w in a["warnings"])
        # supported 목록엔 들어감 (fade로 폴백되므로)
        ops = [s["op"] for s in a["supported_segments"]]
        assert "add_video_transition" in ops

    def test_multiple_video_tracks_warn(self, tmp_session, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V2"
        })
        a = analyze_session_for_render(tmp_session)
        assert a["primary_video_track"] == "V1"
        assert any("V2" in w for w in a["warnings"])

    def test_clip_settings_warning(self, tmp_session, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(f), "start": "0s", "duration": "2s", "track": "V1",
            "clip_settings": {"scale_x": 0.5, "scale_y": 0.5},
        })
        a = analyze_session_for_render(tmp_session)
        assert any("clip_settings" in w for w in a["warnings"])


# =========================================================================
# build_ffmpeg_command
# =========================================================================


class TestBuildFfmpegCommand:
    def test_basic_video_audio(self, tmp_session, tmp_path):
        # 파일 경로만 있으면 analyze가 넘어감 (OS fs 존재 확인)
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        a = tmp_path / "a.mp3"; a.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "audio", "name": "A1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_audio", {
            "file": str(a), "start": "0s", "duration": "2s", "track": "A1"
        })
        out = str(tmp_path / "out.mp4")
        cmd, info = build_ffmpeg_command(tmp_session, out, crf=22, preset="ultrafast")
        # 기본 토큰
        assert cmd[0] == "ffmpeg"
        assert "-filter_complex" in cmd
        assert "-c:v" in cmd and "libx264" in cmd
        assert "-crf" in cmd and "22" in cmd
        assert "-preset" in cmd and "ultrafast" in cmd
        assert "-c:a" in cmd and "aac" in cmd
        assert out == cmd[-1]
        assert info["video_segments"] == 1
        assert info["audio_segments"] == 1

    def test_no_audio_skips_audio_codec(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        out = str(tmp_path / "out.mp4")
        cmd, info = build_ffmpeg_command(tmp_session, out)
        assert "-c:a" not in cmd
        # 단일 비디오 세그먼트
        assert info["video_segments"] == 1

    def test_gap_padding_injects_black(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        # 0~1s
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        # 3s~4s (2s gap)
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "3s", "duration": "1s", "track": "V1"
        })
        out = str(tmp_path / "out.mp4")
        cmd, info = build_ffmpeg_command(tmp_session, out)
        # lavfi color 입력이 최소 한 번 있어야 (gap용)
        joined = " ".join(cmd)
        assert "color=c=black" in joined

    def test_text_segment_creates_srt(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "text", "name": "T1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "3s", "track": "V1"
        })
        tmp_session.append_operation("add_text", {
            "text": "안녕하세요", "start": "0s", "duration": "2s", "track": "T1"
        })
        srt_path = tmp_path / "subs.srt"
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"),
                                          srt_path=srt_path)
        assert info["text_segments"] == 1
        assert srt_path.exists()
        assert "안녕하세요" in srt_path.read_text(encoding="utf-8")
        # filter_complex에 subtitles 필터 들어가야
        assert "subtitles=" in info["filter_complex"]

    def test_fade_added_to_filter(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "3s", "track": "V1"
        })
        tmp_session.append_operation("add_video_fade", {
            "segment_ref": seg["id"], "track": "V1",
            "fade_in": "500ms", "fade_out": "500ms",
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        assert "fade=t=in" in info["filter_complex"]
        assert "fade=t=out" in info["filter_complex"]


# =========================================================================
# render_headless (고수준)
# =========================================================================


class TestRenderHeadlessFunction:
    def test_missing_ffmpeg_raises(self, tmp_session, tmp_path, monkeypatch):
        # shutil.which가 None 반환하도록 패치
        monkeypatch.setattr(
            "cli_anything.capcut.commands.render_headless.shutil.which",
            lambda name: None,
        )
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        import click
        with pytest.raises(click.ClickException) as exc:
            render_headless(tmp_session, str(tmp_path / "out.mp4"))
        assert "ffmpeg" in str(exc.value.message).lower()

    def test_missing_file_raises(self, tmp_session, tmp_path):
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": "/does/not/exist.mp4", "start": "0s", "duration": "1s", "track": "V1"
        })
        import click
        with pytest.raises(click.ClickException) as exc:
            render_headless(tmp_session, str(tmp_path / "out.mp4"), dry_run=True)
        assert "누락" in str(exc.value.message) or "missing" in str(exc.value.message).lower()

    def test_unsupported_without_allow_raises(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        tmp_session.append_operation("add_filter", {
            "name": "vignette", "start": "0s", "duration": "1s", "track": "F1"
        })
        import click
        with pytest.raises(click.ClickException) as exc:
            render_headless(tmp_session, str(tmp_path / "out.mp4"), dry_run=True)
        assert "unsupported" in str(exc.value.message).lower() or "미지원" in str(exc.value.message)

    def test_unsupported_with_allow_ok_dry_run(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        tmp_session.append_operation("add_filter", {
            "name": "vignette", "start": "0s", "duration": "1s", "track": "F1"
        })
        result = render_headless(
            tmp_session, str(tmp_path / "out.mp4"),
            allow_unsupported=True, dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert any(u["op"] == "add_filter" for u in result["unsupported_ops"])

    def test_dry_run_does_not_create_output(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        out = tmp_path / "out.mp4"
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        result = render_headless(tmp_session, str(out), dry_run=True)
        assert result["status"] == "dry_run"
        assert result["ffmpeg_command"][0] == "ffmpeg"
        assert not out.exists()


# =========================================================================
# CLI 통합
# =========================================================================


class TestCli:
    def test_cli_dry_run(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        runner = CliRunner()
        out = tmp_path / "out.mp4"
        result = runner.invoke(
            cli,
            ["render-headless",
             "-p", str(tmp_session.path),
             "-o", str(out),
             "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert not out.exists()

    def test_cli_missing_file_errors(self, tmp_session, tmp_path):
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": "/nope.mp4", "start": "0s", "duration": "1s", "track": "V1"
        })
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["render-headless",
             "-p", str(tmp_session.path),
             "-o", str(tmp_path / "out.mp4"),
             "--dry-run"],
        )
        assert result.exit_code != 0


# =========================================================================
# 실렌더 통합 (ffmpeg 있을 때만)
# =========================================================================


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
class TestRealRender:
    def test_real_render_video_only(self, tmp_session, tmp_path):
        v = _make_short_video(tmp_path / "v.mp4", duration=1.0)
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        out = tmp_path / "out.mp4"
        result = render_headless(
            tmp_session, str(out),
            crf=28, preset="ultrafast",
        )
        assert result["status"] == "rendered"
        assert out.exists()
        assert out.stat().st_size > 0

    def test_real_render_video_plus_audio(self, tmp_session, tmp_path):
        v = _make_short_video(tmp_path / "v.mp4", duration=1.0)
        a = _make_short_audio(tmp_path / "a.mp3", duration=1.0)
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "audio", "name": "A1"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V1"
        })
        tmp_session.append_operation("add_audio", {
            "file": str(a), "start": "0s", "duration": "1s", "track": "A1",
            "volume": 0.5,
        })
        out = tmp_path / "out.mp4"
        result = render_headless(
            tmp_session, str(out),
            crf=28, preset="ultrafast",
        )
        assert result["status"] == "rendered"
        assert out.exists()
        assert out.stat().st_size > 0
