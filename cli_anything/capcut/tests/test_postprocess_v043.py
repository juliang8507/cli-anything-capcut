"""v0.4.3 복원 기능 테스트 — reverse / freeze-frame / blend-mode / chroma-key.

각 기능마다 두 가지 검증:
1. CLI 커맨드가 op를 세션에 올바르게 기록하는지
2. apply_postprocess 핸들러가 draft_content.json을 올바르게 패치하는지
"""

from __future__ import annotations

import json
import os
import subprocess
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


def _minimal_draft(tmp_path: Path, track: str = "V1", seg_index: int = 0) -> Path:
    """apply_postprocess 테스트용 최소 draft_content.json 작성."""
    draft = {
        "tracks": [
            {
                "type": "video",
                "name": track,
                "segments": [
                    {
                        "id": "seg_0",
                        "extra_material_refs": [],
                    }
                ] * (seg_index + 1),
            }
        ],
        "materials": {
            "speeds": [],
            "video_chromakeys": [],
        },
    }
    # seg_index 이후 세그먼트는 별도 객체여야 해 (같은 참조면 안 됨)
    draft["tracks"][0]["segments"] = [
        {"id": f"seg_{i}", "extra_material_refs": []} for i in range(seg_index + 1)
    ]
    p = tmp_path / "draft_content.json"
    p.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "drafts").mkdir()
    return tmp_path


# =====================================================================
# 공통 세션 셋업 헬퍼
# =====================================================================

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
# 1. video reverse
# =====================================================================

class TestVideoReverse:
    def test_help_output(self):
        """--help 호출 시 0 종료."""
        proc = _run(["video", "reverse", "--help"])
        assert proc.returncode == 0
        assert "reverse" in proc.stdout.lower() or "역재생" in proc.stdout

    def test_op_recorded_in_session(self, workspace):
        """CLI 호출 → 세션에 set_reverse op가 기록되는지."""
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "reverse", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id])
        # append_operation은 clean_args를 최상위로 스프레드해서 반환
        assert r["type"] == "set_reverse"
        assert r["track"] == "V1"
        assert r["segment_ref"] == seg_id

    def test_draft_json_patched(self, workspace):
        """apply_postprocess 핸들러가 segment["reverse"] = True 를 설정하는지."""
        from cli_anything.capcut.core.postprocess import apply_reverse_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        seg = draft["tracks"][0]["segments"][0]
        assert "reverse" not in seg

        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_reverse_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0"},
            session_data,
        )
        assert warnings == []
        assert draft["tracks"][0]["segments"][0]["reverse"] is True


# =====================================================================
# 2. video freeze-frame
# =====================================================================

class TestVideoFreezeFrame:
    def test_help_output(self):
        proc = _run(["video", "freeze-frame", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "freeze-frame", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id])
        assert r["type"] == "set_freeze_frame"
        assert r["track"] == "V1"

    def test_op_recorded_with_duration(self, workspace):
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "freeze-frame", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id, "--duration", "2s"])
        assert r.get("duration") == "2s"

    def test_draft_json_patched_with_speed_material(self, workspace):
        """speed material이 있을 때 mode=freeze, speed=0.0 으로 패치."""
        from cli_anything.capcut.core.postprocess import apply_freeze_frame_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        # speed material 미리 삽입
        speed_mat_id = "spd_001"
        draft["materials"]["speeds"] = [{"id": speed_mat_id, "mode": "normal", "speed": 1.0}]
        draft["tracks"][0]["segments"][0]["extra_material_refs"] = [speed_mat_id]

        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_freeze_frame_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0"},
            session_data,
        )
        spd = draft["materials"]["speeds"][0]
        assert spd["mode"] == "freeze"
        assert spd["speed"] == 0.0

    def test_draft_json_patched_fallback(self, workspace):
        """speed material 없을 때 speed_info 폴백 패치."""
        from cli_anything.capcut.core.postprocess import apply_freeze_frame_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_freeze_frame_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0"},
            session_data,
        )
        seg = draft["tracks"][0]["segments"][0]
        assert seg["speed_info"]["mode"] == "freeze"
        assert seg["speed_info"]["speed"] == 0.0
        # 경고 메시지 포함
        assert any("speed material" in w for w in warnings)


# =====================================================================
# 3. video blend-mode
# =====================================================================

class TestVideoBlendMode:
    def test_help_output(self):
        proc = _run(["video", "blend-mode", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "blend-mode", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id, "--mode", "multiply"])
        assert r["type"] == "set_blend_mode"
        assert r["mode"] == "multiply"

    def test_blend_mode_integer_mapping(self, workspace):
        """각 모드가 올바른 정수로 매핑되는지."""
        from cli_anything.capcut.core.postprocess import BLEND_MODES, apply_blend_mode_patch

        # 핵심 매핑 검증
        assert BLEND_MODES["normal"] == 0
        assert BLEND_MODES["multiply"] == 1
        assert BLEND_MODES["screen"] == 2
        assert BLEND_MODES["overlay"] == 3
        assert BLEND_MODES["darken"] == 4
        assert BLEND_MODES["lighten"] == 5

    def test_draft_json_patched_multiply(self, workspace):
        from cli_anything.capcut.core.postprocess import apply_blend_mode_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_blend_mode_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0", "mode": "multiply"},
            session_data,
        )
        assert warnings == []
        seg = draft["tracks"][0]["segments"][0]
        assert seg["track_attribute"]["blend_mode"] == 1  # multiply

    def test_draft_json_patched_screen(self, workspace):
        from cli_anything.capcut.core.postprocess import apply_blend_mode_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        apply_blend_mode_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0", "mode": "screen"},
            session_data,
        )
        assert draft["tracks"][0]["segments"][0]["track_attribute"]["blend_mode"] == 2

    def test_unknown_mode_falls_back_to_normal(self, workspace):
        from cli_anything.capcut.core.postprocess import apply_blend_mode_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_blend_mode_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0", "mode": "bogus_mode"},
            session_data,
        )
        seg = draft["tracks"][0]["segments"][0]
        assert seg["track_attribute"]["blend_mode"] == 0  # normal 폴백
        assert len(warnings) == 1


# =====================================================================
# 4. video chroma-key
# =====================================================================

class TestVideoChromaKey:
    def test_help_output(self):
        proc = _run(["video", "chroma-key", "--help"])
        assert proc.returncode == 0

    def test_op_recorded_in_session(self, workspace):
        sp, seg_id = _setup_session_with_video(workspace)
        r = _json(["video", "chroma-key", "-p", str(sp),
                   "--track", "V1", "--segment-ref", seg_id,
                   "--color", "#00FF00", "--intensity", "0.6"])
        assert r["type"] == "set_chroma_key"
        assert r["color"] == "#00FF00"
        assert r["intensity"] == pytest.approx(0.6)

    def test_draft_json_material_added(self, workspace):
        """video_chromakeys 배열에 material이 추가되는지."""
        from cli_anything.capcut.core.postprocess import apply_chroma_key_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        warnings = apply_chroma_key_patch(
            draft,
            {
                "track": "V1",
                "segment_ref": "op_0",
                "color": "#00FF00",
                "intensity": 0.5,
                "shadow": 0.5,
                "smoothness": 0.1,
                "spill": 0.0,
            },
            session_data,
        )
        assert warnings == []
        mats = draft["materials"]["video_chromakeys"]
        assert len(mats) == 1
        m = mats[0]
        assert m["type"] == "video_chromakey"
        assert m["color"] == "#00FF00"
        assert m["intensity"] == pytest.approx(0.5)

    def test_draft_json_extra_material_refs_linked(self, workspace):
        """segment.extra_material_refs 에 material id가 연결되는지."""
        from cli_anything.capcut.core.postprocess import apply_chroma_key_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        apply_chroma_key_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0", "color": "#00FF00",
             "intensity": 0.5, "shadow": 0.5, "smoothness": 0.1, "spill": 0.0},
            session_data,
        )
        seg = draft["tracks"][0]["segments"][0]
        mat_id = draft["materials"]["video_chromakeys"][0]["id"]
        assert mat_id in seg["extra_material_refs"]

    def test_default_color_is_green(self, workspace):
        """--color 미지정 시 기본값이 #00FF00 인지."""
        from cli_anything.capcut.core.postprocess import apply_chroma_key_patch

        draft_path = _minimal_draft(workspace)
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        session_data = {
            "operations": [
                {"id": "op_0", "op": "add_video",
                 "args": {"track": "V1", "file": "x.mp4", "start": "0s", "duration": "3s"}},
            ]
        }
        apply_chroma_key_patch(
            draft,
            {"track": "V1", "segment_ref": "op_0"},  # color 없음
            session_data,
        )
        assert draft["materials"]["video_chromakeys"][0]["color"] == "#00FF00"
