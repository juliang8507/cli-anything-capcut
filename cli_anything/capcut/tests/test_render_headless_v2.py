"""render-headless v0.4.1 확장 테스트.

- V2+ 오버레이 (PIP)
- clip_settings transform/scale 좌표 변환
- 실제 xfade 트랜지션
- add_keyframe 근사 (uniform_scale, alpha, transform_*)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cli_anything.capcut.commands.render_headless import (
    KEYFRAME_SUPPORTED_PROPS,
    TRANSITION_NAME_MAP,
    _build_keyframe_alpha_expr,
    _build_keyframe_scale_expr,
    _capcut_to_ffmpeg_xy,
    _map_transition_name,
    analyze_session_for_render,
    build_ffmpeg_command,
    render_headless,
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
        draft_name="headless-v2-test",
        width=1920,
        height=1080,
        fps=30,
        output=tmp_path / "test.session.json",
    )


def _make_short_video(path: Path, duration: float = 1.0, color: str = "red") -> Path:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:s=640x360:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30",
            str(path),
        ],
        check=True, capture_output=True,
    )
    return path


# =========================================================================
# 좌표 변환 헬퍼 단위 테스트
# =========================================================================


class TestCapcutToFfmpegXy:
    def test_center_maps_to_center(self):
        # (0,0) CapCut → main 중앙 - overlay/2
        x, y = _capcut_to_ffmpeg_xy(0.0, 0.0, 1920, 1080, 960, 540)
        # (0*0.5+0.5)*1920 - 960*0.5 = 960 - 480 = 480
        assert x == pytest.approx(480.0)
        # (1 - (0*0.5+0.5))*1080 - 540*0.5 = 540 - 270 = 270
        assert y == pytest.approx(270.0)

    def test_top_left_corner(self):
        # CapCut (-1, +1) = 좌상단 코너 (오버레이의 좌상단이 그 지점)
        x, y = _capcut_to_ffmpeg_xy(-1.0, 1.0, 1920, 1080, 0, 0)
        # x = ( -1*0.5+0.5 )*1920 - 0 = 0
        assert x == pytest.approx(0.0)
        # y = (1 - (1*0.5+0.5))*1080 - 0 = 0
        assert y == pytest.approx(0.0)

    def test_bottom_right_corner(self):
        x, y = _capcut_to_ffmpeg_xy(1.0, -1.0, 1920, 1080, 0, 0)
        assert x == pytest.approx(1920.0)
        assert y == pytest.approx(1080.0)

    def test_overlay_centered_with_size(self):
        # overlay 960x540가 main 1920x1080 센터에 놓이면 x=480, y=270
        x, y = _capcut_to_ffmpeg_xy(0.0, 0.0, 1920, 1080, 960, 540)
        assert x == pytest.approx(480.0)
        assert y == pytest.approx(270.0)


# =========================================================================
# transition name 매핑
# =========================================================================


class TestTransitionMapping:
    def test_dissolve_maps_to_dissolve(self):
        name, warn = _map_transition_name("dissolve")
        assert name == "dissolve"
        assert warn is None

    def test_slide_left_maps_to_slideleft(self):
        name, warn = _map_transition_name("slide_left")
        assert name == "slideleft"
        assert warn is None

    def test_slide_right_maps_to_slideright(self):
        name, warn = _map_transition_name("slide_right")
        assert name == "slideright"
        assert warn is None

    def test_wipe_left_maps_to_wipeleft(self):
        name, _ = _map_transition_name("wipe_left")
        assert name == "wipeleft"

    def test_circle_maps_to_circleopen(self):
        name, _ = _map_transition_name("circle")
        assert name == "circleopen"

    def test_all_documented_mappings_exist(self):
        """문서에 나열된 모든 매핑 확인."""
        expected = {
            "dissolve": "dissolve",
            "fade": "fade",
            "slide_left": "slideleft",
            "slide_right": "slideright",
            "slide_up": "slideup",
            "slide_down": "slidedown",
            "wipe_left": "wipeleft",
            "wipe_right": "wiperight",
            "circle": "circleopen",
        }
        assert TRANSITION_NAME_MAP == expected

    def test_unknown_falls_back_to_fade(self):
        name, warn = _map_transition_name("asdf_xyz")
        assert name == "fade"
        assert warn is not None
        assert "asdf_xyz" in warn


# =========================================================================
# V2 오버레이
# =========================================================================


class TestV2Overlay:
    def test_v2_segment_detected_as_overlay(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V2",
            "clip_settings": {"scale_x": 0.5, "scale_y": 0.5,
                              "transform_x": 0.5, "transform_y": 0.5},
        })
        a = analyze_session_for_render(tmp_session)
        assert a["primary_video_track"] == "V1"
        assert a["overlay_video_tracks"] == ["V2"]

    def test_ffmpeg_command_contains_overlay_filter(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V2",
            "clip_settings": {"scale_x": 0.5, "scale_y": 0.5,
                              "transform_x": 0.5, "transform_y": -0.5},
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        fc = info["filter_complex"]
        assert "overlay=" in fc
        assert info["overlay_segments"] == 1

    def test_overlay_scale_and_position(self, tmp_session, tmp_path):
        """scale_x=0.5 이면 ov_w=main_w*0.5; transform_x=0 이면 x_px=main_w*0.25"""
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        # 1920x1080 세션
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V2",
            "clip_settings": {"scale_x": 0.5, "scale_y": 0.5,
                              "transform_x": 0.0, "transform_y": 0.0},
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        fc = info["filter_complex"]
        # overlay 크기 scale 필터
        assert "scale=960:540" in fc
        # 센터 배치: x = (0*0.5+0.5)*1920 - 960*0.5 = 480
        # y = (1 - (0*0.5+0.5))*1080 - 540*0.5 = 270
        assert "480.00" in fc or "x='480.00'" in fc or "480" in fc
        assert "270.00" in fc or "y='270.00'" in fc or "270" in fc

    def test_multiple_overlay_tracks(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V3"})
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "3s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "1s", "track": "V2",
            "clip_settings": {"scale_x": 0.4, "scale_y": 0.4,
                              "transform_x": -0.5, "transform_y": 0.5},
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "1s", "duration": "1s", "track": "V3",
            "clip_settings": {"scale_x": 0.3, "scale_y": 0.3,
                              "transform_x": 0.5, "transform_y": -0.5},
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        fc = info["filter_complex"]
        # 오버레이 체인 2단
        assert fc.count("overlay=") >= 2
        assert info["overlay_segments"] == 2


# =========================================================================
# xfade 트랜지션
# =========================================================================


class TestXfadeTransition:
    def test_xfade_used_when_transition_present(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg1 = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        seg2 = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "2s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video_transition", {
            "name": "dissolve", "segment_ref": seg1["id"], "track": "V1",
            "duration": "500ms",
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        assert info["xfade_used"] is True
        assert "xfade=" in info["filter_complex"]
        assert "transition=dissolve" in info["filter_complex"]

    def test_xfade_slide_left(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg1 = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "2s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video_transition", {
            "name": "slide_left", "segment_ref": seg1["id"], "track": "V1",
            "duration": "800ms",
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        assert "transition=slideleft" in info["filter_complex"]
        assert "duration=0.800" in info["filter_complex"]

    def test_xfade_fallback_to_fade_on_unknown(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg1 = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "2s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_video_transition", {
            "name": "weird_fx", "segment_ref": seg1["id"], "track": "V1",
            "duration": "500ms",
        })
        a = analyze_session_for_render(tmp_session)
        # 경고 있고
        assert any("weird_fx" in w for w in a["warnings"])
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        # fade로 폴백
        assert "transition=fade" in info["filter_complex"]

    def test_xfade_offset_is_duration_minus_transition(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg1 = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "3s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v), "start": "3s", "duration": "3s", "track": "V1"
        })
        tmp_session.append_operation("add_video_transition", {
            "name": "dissolve", "segment_ref": seg1["id"], "track": "V1",
            "duration": "1s",
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        # offset = 3 - 1 = 2.000
        assert "offset=2.000" in info["filter_complex"]


# =========================================================================
# keyframe 근사
# =========================================================================


class TestKeyframeApprox:
    def test_supported_properties_constant(self):
        assert KEYFRAME_SUPPORTED_PROPS == {
            "uniform_scale", "alpha", "transform_x", "transform_y"
        }

    def test_scale_expr_single_kf_is_static(self):
        expr, s0, s1 = _build_keyframe_scale_expr(
            2_000_000,
            [{"time_us": 0, "value": 1.5}],
            1920, 1080,
        )
        # 단일 kf = 정적 scale
        assert "eval=frame" not in expr
        assert s0 == 1.5

    def test_scale_expr_two_kf_is_dynamic(self):
        expr, s0, s1 = _build_keyframe_scale_expr(
            2_000_000,
            [
                {"time_us": 0, "value": 1.0},
                {"time_us": 2_000_000, "value": 1.5},
            ],
            1920, 1080,
        )
        assert "eval=frame" in expr
        assert s0 == 1.0 and s1 == 1.5

    def test_alpha_fade_in_uses_fade_filter(self):
        expr = _build_keyframe_alpha_expr(
            2_000_000,
            [
                {"time_us": 0, "value": 0.0},
                {"time_us": 2_000_000, "value": 1.0},
            ],
        )
        assert expr is not None
        assert "fade=t=in" in expr

    def test_alpha_fade_out_uses_fade_filter(self):
        expr = _build_keyframe_alpha_expr(
            2_000_000,
            [
                {"time_us": 0, "value": 1.0},
                {"time_us": 2_000_000, "value": 0.0},
            ],
        )
        assert expr is not None
        assert "fade=t=out" in expr

    def test_uniform_scale_kf_detected_in_analyze(self, tmp_session, tmp_path):
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "uniform_scale", "time": "0s", "value": 1.0,
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "uniform_scale", "time": "2s", "value": 1.5,
        })
        a = analyze_session_for_render(tmp_session)
        assert a["unsupported_ops"] == []
        kfs = a["keyframes_by_segment"].get(seg["id"], [])
        assert len(kfs) == 2

    def test_uniform_scale_kf_in_filter_complex(self, tmp_session, tmp_path):
        """keyframe uniform_scale 2개 (줌인) → scale 표현식 포함."""
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "uniform_scale", "time": "0s", "value": 1.0,
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "uniform_scale", "time": "2s", "value": 1.5,
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        fc = info["filter_complex"]
        # Ken Burns: scale=w='...eval=frame 또는 expr 포함
        assert "eval=frame" in fc

    def test_alpha_kf_fadein_in_filter_complex(self, tmp_session, tmp_path):
        """keyframe alpha 2개 (0→1 페이드인) → fade=t=in 포함."""
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "alpha", "time": "0s", "value": 0.0,
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "alpha", "time": "2s", "value": 1.0,
        })
        cmd, info = build_ffmpeg_command(tmp_session, str(tmp_path / "out.mp4"))
        fc = info["filter_complex"]
        assert "fade=t=in" in fc and "alpha=1" in fc

    def test_3plus_keyframes_warning(self, tmp_session, tmp_path):
        """keyframe 3개 이상 → 경고만 (선형 보간)"""
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "3s", "track": "V1"
        })
        for i, val in enumerate([1.0, 1.3, 1.5]):
            tmp_session.append_operation("add_keyframe", {
                "segment_ref": seg["id"], "track": "V1",
                "property": "uniform_scale", "time": f"{i}s", "value": val,
            })
        a = analyze_session_for_render(tmp_session)
        # 경고 있음
        assert any(
            "keyframe" in w and ("3" in w or "개" in w) for w in a["warnings"]
        )

    def test_unsupported_keyframe_property(self, tmp_session, tmp_path):
        """rotation 같은 미지원 property는 unsupported로 분류."""
        v = tmp_path / "v.mp4"; v.write_bytes(b"x")
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        seg = tmp_session.append_operation("add_video", {
            "file": str(v), "start": "0s", "duration": "2s", "track": "V1"
        })
        tmp_session.append_operation("add_keyframe", {
            "segment_ref": seg["id"], "track": "V1",
            "property": "rotation", "time": "0s", "value": 0.0,
        })
        a = analyze_session_for_render(tmp_session)
        ops = [u["op"] for u in a["unsupported_ops"]]
        assert "add_keyframe" in ops


# =========================================================================
# 실렌더 통합 (ffmpeg 있을 때만, V1 + V2 PIP + xfade)
# =========================================================================


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
class TestRealRenderV2:
    def test_real_render_v1_plus_v2_overlay_and_xfade(self, tmp_session, tmp_path):
        v1a = _make_short_video(tmp_path / "v1a.mp4", duration=1.0, color="red")
        v1b = _make_short_video(tmp_path / "v1b.mp4", duration=1.0, color="blue")
        v2 = _make_short_video(tmp_path / "v2.mp4", duration=1.0, color="green")

        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "video", "name": "V2"})
        seg1 = tmp_session.append_operation("add_video", {
            "file": str(v1a), "start": "0s", "duration": "1s", "track": "V1"
        })
        tmp_session.append_operation("add_video", {
            "file": str(v1b), "start": "1s", "duration": "1s", "track": "V1"
        })
        # V2 overlay: 우하단 1/4 크기
        tmp_session.append_operation("add_video", {
            "file": str(v2), "start": "0s", "duration": "1.5s", "track": "V2",
            "clip_settings": {"scale_x": 0.25, "scale_y": 0.25,
                              "transform_x": 0.6, "transform_y": -0.6},
        })
        # xfade 300ms
        tmp_session.append_operation("add_video_transition", {
            "name": "dissolve", "segment_ref": seg1["id"], "track": "V1",
            "duration": "300ms",
        })

        out = tmp_path / "out.mp4"
        result = render_headless(
            tmp_session, str(out),
            crf=28, preset="ultrafast",
        )
        assert result["status"] == "rendered"
        assert out.exists()
        assert out.stat().st_size > 0

        # duration 확인 (ffprobe)
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                capture_output=True, text=True, check=True,
            )
            dur = float(proc.stdout.strip())
            # 기대 duration: 1 + 1 - 0.3 = 1.7s (xfade 겹침)
            assert 1.3 < dur < 2.2, f"duration {dur}s 범위 밖"
