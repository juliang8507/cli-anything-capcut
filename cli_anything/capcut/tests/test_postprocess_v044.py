"""v0.4.4 복원 기능 테스트 — video lut / video speed-curve / color curves / color hsl.

각 기능마다 두 가지 검증:
1. CLI 커맨드가 op를 세션에 올바르게 기록하는지
2. apply_XXX_patch 핸들러가 draft_content.json을 올바르게 패치하는지
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

CLI = "cli-anything-capcut"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("CAPCUT_NO_STAGING", "1")
    return subprocess.run([CLI, *args], capture_output=True, text=True,
                          encoding="utf-8", env=env)


def _json(args: list[str]) -> dict:
    proc = _run(["--json", *args])
    if proc.returncode != 0:
        raise RuntimeError(
            f"CLI 실패 ({proc.returncode}):\n{proc.stdout}\n---\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def _png(tmp_path: Path) -> Path:
    """최소 유효 PNG (1×1 픽셀) 생성."""
    p = tmp_path / "t.png"
    p.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
        "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
        "49454e44ae426082"
    ))
    return p


def _cube_lut(tmp_path: Path) -> Path:
    """최소 유효 .cube LUT 파일 생성 (1D 3포인트)."""
    p = tmp_path / "test.cube"
    p.write_text(
        "TITLE \"Test LUT\"\n"
        "LUT_1D_SIZE 3\n"
        "0.0 0.0 0.0\n"
        "0.5 0.5 0.5\n"
        "1.0 1.0 1.0\n",
        encoding="utf-8",
    )
    return p


def _minimal_draft(tmp_path: Path, track: str = "V1", seg_index: int = 0,
                   seg_id: str = "seg_0") -> Path:
    """apply_XXX_patch 테스트용 최소 draft_content.json 작성."""
    draft = {
        "tracks": [
            {
                "type": "video",
                "name": track,
                "segments": [
                    {"id": f"seg_{i}", "extra_material_refs": []}
                    for i in range(seg_index + 1)
                ],
            }
        ],
        "materials": {
            "speeds": [],
            "video_luts": [],
            "color_curves": [],
            "material_colors": [],
        },
    }
    # 첫 번째 세그먼트 id 를 지정값으로 교체
    draft["tracks"][0]["segments"][0]["id"] = seg_id
    p = tmp_path / "draft_content.json"
    p.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    return p


def _session_data(seg_id: str = "op_0") -> dict:
    """테스트용 최소 session_data 구조."""
    return {
        "operations": [
            {
                "id": seg_id,
                "op": "add_video",
                "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"},
            }
        ]
    }


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "drafts").mkdir()
    return tmp_path


def _setup_session_with_video(workspace: Path) -> tuple[Path, str]:
    """프로젝트 생성 → 트랙 생성 → 이미지 추가 → (세션 경로, seg_op_id) 반환."""
    sp = workspace / "s.session.json"
    media = _png(workspace)
    _json(["project", "new", "--name", "test", "--preset", "square",
           "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
    _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
    r = _json(["image", "add", "-p", str(sp), "-f", str(media),
               "--start", "0s", "--duration", "3s", "--track", "V1"])
    return sp, r["id"]


# =====================================================================
# 1. video lut
# =====================================================================

class TestVideoLut:
    def test_help_output(self):
        """--help 호출 시 0 종료."""
        proc = _run(["video", "lut", "--help"])
        assert proc.returncode == 0
        assert "lut" in proc.stdout.lower() or "LUT" in proc.stdout

    def test_op_recorded_in_session(self, workspace):
        """CLI 호출 → 세션에 add_lut op가 기록되는지."""
        sp, seg_id = _setup_session_with_video(workspace)
        lut_file = _cube_lut(workspace)
        r = _json(["video", "lut", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id,
                   "--file", str(lut_file), "--intensity", "0.8"])
        assert r["type"] == "add_lut"
        assert r["track"] == "V1"
        assert r["intensity"] == pytest.approx(0.8)

    def test_lut_material_added_to_draft(self, workspace):
        """apply_lut_patch → materials.video_luts에 material 추가."""
        from cli_anything.capcut.core.postprocess import apply_lut_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        lut_file = _cube_lut(workspace)

        warnings = apply_lut_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "file": str(lut_file), "intensity": 0.8, "name": "My LUT"},
            _session_data(),
        )
        assert warnings == []
        luts = draft["materials"]["video_luts"]
        assert len(luts) == 1
        assert luts[0]["type"] == "lut"
        assert luts[0]["intensity"] == pytest.approx(0.8)
        assert luts[0]["name"] == "My LUT"

    def test_segment_enable_lut_flag(self, workspace):
        """apply_lut_patch → segment.enable_lut = True."""
        from cli_anything.capcut.core.postprocess import apply_lut_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        lut_file = _cube_lut(workspace)

        apply_lut_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "file": str(lut_file), "intensity": 1.0},
            _session_data(),
        )
        seg = draft["tracks"][0]["segments"][0]
        assert seg["enable_lut"] is True

    def test_extra_material_refs_linked(self, workspace):
        """apply_lut_patch → segment.extra_material_refs에 lut id 연결."""
        from cli_anything.capcut.core.postprocess import apply_lut_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        lut_file = _cube_lut(workspace)

        apply_lut_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "file": str(lut_file), "intensity": 1.0},
            _session_data(),
        )
        lut_id = draft["materials"]["video_luts"][0]["id"]
        seg = draft["tracks"][0]["segments"][0]
        assert lut_id in seg["extra_material_refs"]

    def test_nonstandard_extension_warning(self, workspace):
        """비표준 LUT 확장자 → 경고 포함."""
        from cli_anything.capcut.core.postprocess import apply_lut_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        # 임시 .xyz 파일 생성 (exists=True 필요 없으므로 빈 path 사용)
        fake_lut = workspace / "fake.xyz"
        fake_lut.write_text("dummy", encoding="utf-8")

        warnings = apply_lut_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "file": str(fake_lut), "intensity": 1.0},
            _session_data(),
        )
        assert any("비표준" in w or "확장자" in w for w in warnings)


# =====================================================================
# 2. video speed-curve
# =====================================================================

class TestVideoSpeedCurve:
    def test_help_output(self):
        """--help 호출 시 0 종료."""
        proc = _run(["video", "speed-curve", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        """CLI 호출 → 세션에 set_speed_curve op가 기록되는지."""
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "speed-curve", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id,
                   "--points", "0,1.0;0.5,2.0;1.0,1.0"])
        assert r["type"] == "set_speed_curve"
        assert r["track"] == "V1"

    def test_three_points_parsed(self, workspace):
        """3점 곡선 입력 시 curve_speed.points 3개 확인."""
        from cli_anything.capcut.core.postprocess import apply_speed_curve_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        warnings = apply_speed_curve_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "points": [(0.0, 1.0), (0.5, 2.0), (1.0, 1.0)],
             "curve_range": [0.0, 1.0]},
            _session_data(),
        )
        speeds = draft["materials"]["speeds"]
        assert len(speeds) == 1
        sm = speeds[0]
        assert sm["mode"] == "curve"
        pts = sm["curve_speed"]["points"]
        assert len(pts) == 3
        assert pts[1]["x"] == pytest.approx(0.5)
        assert pts[1]["y"] == pytest.approx(2.0)

    def test_existing_speed_material_updated(self, workspace):
        """기존 speed material이 있을 때 mode=curve로 업데이트."""
        from cli_anything.capcut.core.postprocess import apply_speed_curve_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        # speed material 미리 삽입
        spd_id = "spd_001"
        draft["materials"]["speeds"] = [{"id": spd_id, "mode": "normal", "speed": 1.0}]
        draft["tracks"][0]["segments"][0]["extra_material_refs"] = [spd_id]

        apply_speed_curve_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "points": [(0.0, 1.0), (1.0, 3.0)],
             "curve_range": [0.0, 1.0]},
            _session_data(),
        )
        sm = draft["materials"]["speeds"][0]
        assert sm["mode"] == "curve"
        assert len(sm["curve_speed"]["points"]) == 2

    def test_new_speed_material_created_when_missing(self, workspace):
        """speed material 없을 때 새로 생성 + extra_material_refs 연결."""
        from cli_anything.capcut.core.postprocess import apply_speed_curve_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        warnings = apply_speed_curve_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "points": [(0.0, 1.0), (1.0, 2.0)],
             "curve_range": [0.0, 1.0]},
            _session_data(),
        )
        # 경고 포함 (새로 생성 알림)
        assert any("speed material" in w for w in warnings)
        # extra_material_refs 연결 확인
        seg = draft["tracks"][0]["segments"][0]
        assert len(seg["extra_material_refs"]) == 1
        spd_id = seg["extra_material_refs"][0]
        assert any(sm["id"] == spd_id for sm in draft["materials"]["speeds"])

    def test_curve_range_stored(self, workspace):
        """curve_range가 speed material에 저장되는지."""
        from cli_anything.capcut.core.postprocess import apply_speed_curve_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        apply_speed_curve_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "points": [(0.0, 1.0), (1.0, 2.0)],
             "curve_range": [0.1, 0.9]},
            _session_data(),
        )
        sm = draft["materials"]["speeds"][0]
        assert sm["curve_speed"]["curve_range"] == [pytest.approx(0.1), pytest.approx(0.9)]


# =====================================================================
# 3. color curves
# =====================================================================

class TestColorCurves:
    def test_help_output(self):
        """--help 호출 시 0 종료."""
        proc = _run(["color", "curves", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        """CLI 호출 → 세션에 add_color_curves op가 기록되는지."""
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["color", "curves", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id,
                   "--rgb", "0,0;0.5,0.7;1,1"])
        assert r["type"] == "add_color_curves"

    def test_rgb_channel_stored(self, workspace):
        """RGB 마스터 채널 포인트가 저장되는지."""
        from cli_anything.capcut.core.postprocess import apply_color_curves_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        warnings = apply_color_curves_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "rgb": [(0.0, 0.0), (0.5, 0.7), (1.0, 1.0)]},
            _session_data(),
        )
        assert warnings == []
        mats = draft["materials"]["color_curves"]
        assert len(mats) == 1
        m = mats[0]
        assert m["type"] == "color_curves"
        assert len(m["rgb_points"]) == 3
        assert m["rgb_points"][1]["x"] == pytest.approx(0.5)
        assert m["rgb_points"][1]["y"] == pytest.approx(0.7)

    def test_per_channel_stored(self, workspace):
        """R/G/B 개별 채널 포인트가 독립적으로 저장되는지."""
        from cli_anything.capcut.core.postprocess import apply_color_curves_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        apply_color_curves_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "red": [(0.0, 0.0), (1.0, 0.8)],
             "green": [(0.0, 0.0), (1.0, 1.0)],
             "blue": [(0.0, 0.1), (1.0, 0.9)]},
            _session_data(),
        )
        m = draft["materials"]["color_curves"][0]
        assert "red_points" in m
        assert "green_points" in m
        assert "blue_points" in m
        assert "rgb_points" not in m

    def test_enable_color_curves_flag(self, workspace):
        """segment.enable_color_curves = True 설정."""
        from cli_anything.capcut.core.postprocess import apply_color_curves_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        apply_color_curves_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "rgb": [(0.0, 0.0), (1.0, 1.0)]},
            _session_data(),
        )
        seg = draft["tracks"][0]["segments"][0]
        assert seg["enable_color_curves"] is True

    def test_no_channel_returns_warning(self, workspace):
        """채널 미지정 시 경고 반환."""
        from cli_anything.capcut.core.postprocess import apply_color_curves_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        warnings = apply_color_curves_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0"},  # 채널 없음
            _session_data(),
        )
        assert len(warnings) == 1
        assert "채널" in warnings[0]

    def test_extra_material_refs_linked(self, workspace):
        """segment.extra_material_refs에 curves material id 연결."""
        from cli_anything.capcut.core.postprocess import apply_color_curves_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        apply_color_curves_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "rgb": [(0.0, 0.0), (1.0, 1.0)]},
            _session_data(),
        )
        mat_id = draft["materials"]["color_curves"][0]["id"]
        seg = draft["tracks"][0]["segments"][0]
        assert mat_id in seg["extra_material_refs"]


# =====================================================================
# 4. color hsl
# =====================================================================

class TestColorHsl:
    def test_help_output(self):
        """--help 호출 시 0 종료."""
        proc = _run(["color", "hsl", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        """CLI 호출 → 세션에 add_hsl_adjust op가 기록되는지."""
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["color", "hsl", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id,
                   "--target", "red", "--hue", "10", "--saturation", "-20"])
        assert r["type"] == "add_hsl_adjust"
        assert r["target"] == "red"

    def test_hsl_values_normalized(self, workspace):
        """hue/saturation/lightness -100~+100 → -1.0~+1.0 변환."""
        from cli_anything.capcut.core.postprocess import apply_hsl_patch

        draft_path = _minimal_draft(workspace, seg_id="seg_0")
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        warnings = apply_hsl_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "red", "hue": 50.0, "saturation": -100.0, "lightness": 100.0},
            _session_data(),
        )
        assert warnings == []
        adjusts = draft["materials"]["material_colors"][0]["adjusts"]
        assert adjusts["red"]["hue"] == pytest.approx(0.5)
        assert adjusts["red"]["saturation"] == pytest.approx(-1.0)
        assert adjusts["red"]["lightness"] == pytest.approx(1.0)

    def test_multiple_targets_accumulated(self, workspace):
        """같은 세그먼트에 여러 target 누적 적용 — 덮어쓰지 않고 추가."""
        from cli_anything.capcut.core.postprocess import apply_hsl_patch

        draft_path = _minimal_draft(workspace, seg_id="seg_0")
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        sd = _session_data()

        apply_hsl_patch(draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "red", "hue": 10.0, "saturation": 0.0, "lightness": 0.0}, sd)
        apply_hsl_patch(draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "green", "hue": -10.0, "saturation": 20.0, "lightness": 0.0}, sd)

        # material_colors 엔트리는 1개 (같은 segment_id)
        assert len(draft["materials"]["material_colors"]) == 1
        adjusts = draft["materials"]["material_colors"][0]["adjusts"]
        assert "red" in adjusts
        assert "green" in adjusts
        assert adjusts["red"]["hue"] == pytest.approx(0.1)
        assert adjusts["green"]["saturation"] == pytest.approx(0.2)

    def test_same_target_overwritten(self, workspace):
        """같은 target 두 번 호출 시 최신값으로 덮어쓰기."""
        from cli_anything.capcut.core.postprocess import apply_hsl_patch

        draft_path = _minimal_draft(workspace, seg_id="seg_0")
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        sd = _session_data()

        apply_hsl_patch(draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "blue", "hue": 30.0, "saturation": 0.0, "lightness": 0.0}, sd)
        apply_hsl_patch(draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "blue", "hue": -50.0, "saturation": 0.0, "lightness": 0.0}, sd)

        adjusts = draft["materials"]["material_colors"][0]["adjusts"]
        assert adjusts["blue"]["hue"] == pytest.approx(-0.5)

    def test_enable_color_correct_adjust_flag(self, workspace):
        """segment.enable_color_correct_adjust = True 설정."""
        from cli_anything.capcut.core.postprocess import apply_hsl_patch

        draft_path = _minimal_draft(workspace, seg_id="seg_0")
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        apply_hsl_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0",
             "target": "cyan", "hue": 0.0, "saturation": 50.0, "lightness": 0.0},
            _session_data(),
        )
        seg = draft["tracks"][0]["segments"][0]
        assert seg["enable_color_correct_adjust"] is True

    def test_all_8_targets_valid(self, workspace):
        """8가지 target 색상 모두 오류 없이 처리."""
        from cli_anything.capcut.core.postprocess import apply_hsl_patch, HSL_TARGET_CHOICES

        for target in HSL_TARGET_CHOICES:
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                (td_path / "drafts").mkdir()
                draft_path = _minimal_draft(td_path, seg_id="seg_0")
                draft = json.loads(draft_path.read_text(encoding="utf-8"))
                warnings = apply_hsl_patch(
                    draft,
                    {"track": "V1", "segment_ref": "op_0",
                     "target": target, "hue": 0.0, "saturation": 0.0, "lightness": 0.0},
                    _session_data(),
                )
                assert warnings == [], f"target={target} 처리 중 경고: {warnings}"
                adjusts = draft["materials"]["material_colors"][0]["adjusts"]
                assert target in adjusts
