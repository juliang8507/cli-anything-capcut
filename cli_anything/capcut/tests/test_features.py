"""Phase 8~13 신규 기능 회귀 테스트."""

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
    # 기존 회귀 테스트는 스테이징 도입 전에 작성됨 — 원본 경로가 세션에 그대로
    # 저장된다는 가정을 유지한다. 한글 사용자명 환경(C:\Users\<korean-name>\...)에서
    # tmp_path 가 비ASCII라 의도치 않게 스테이징되어 회귀가 깨지는 것을 방지.
    env.setdefault("CAPCUT_NO_STAGING", "1")
    return subprocess.run([CLI, *args], capture_output=True, text=True, encoding="utf-8", env=env)


def _json(args: list[str]) -> dict:
    proc = _run(["--json", *args])
    if proc.returncode != 0:
        raise RuntimeError(f"CLI fail {proc.returncode}:\n{proc.stdout}\n---\n{proc.stderr}")
    return json.loads(proc.stdout)


def _png(tmp_path: Path) -> Path:
    p = tmp_path / "t.png"
    p.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
        "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
        "49454e44ae426082"
    ))
    return p


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "drafts").mkdir()
    return tmp_path


# =========================================================================
# Phase 8 — mask / background
# =========================================================================


class TestMaskBackground:
    def test_mask_add_op_recorded(self, workspace):
        sp = workspace / "s.session.json"
        media = _png(workspace)
        _json(["project", "new", "--name", "m1", "--preset", "square",
               "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        r = _json(["image", "add", "-p", str(sp), "-f", str(media),
                   "--start", "0s", "--duration", "2s", "--track", "V1"])
        seg_id = r["id"]
        m = _json(["mask", "add", "-p", str(sp), "--track", "V1",
                   "--segment-ref", seg_id, "--name", "circle", "--size", "0.6"])
        assert m["type"] == "add_mask"
        assert m["name"] == "circle"

    def test_background_blur(self, workspace):
        sp = workspace / "s.session.json"
        media = _png(workspace)
        _json(["project", "new", "--name", "bg1", "--preset", "square",
               "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        r = _json(["image", "add", "-p", str(sp), "-f", str(media),
                   "--start", "0s", "--duration", "2s", "--track", "V1"])
        bg = _json(["background", "add", "-p", str(sp), "--track", "V1",
                    "--segment-ref", r["id"], "--fill-type", "blur", "--blur", "0.1"])
        assert bg["type"] == "add_background"


# =========================================================================
# Phase 10 — preset slideshow
# =========================================================================


class TestPresetSlideshow:
    def test_slideshow_from_folder(self, workspace):
        media_dir = workspace / "imgs"
        media_dir.mkdir()
        for i in range(3):
            p = media_dir / f"{i:02d}.png"
            p.write_bytes(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
                "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
                "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
                "49454e44ae426082"
            ))
        out = workspace / "ss.session.json"
        r = _json(["preset", "slideshow",
                   "--name", "ss", "--folder", str(media_dir),
                   "--duration", "2s", "--transition", "dissolve",
                   "--draft-folder", str(workspace / "drafts"),
                   "--output", str(out)])
        assert r["status"] == "slideshow_created"
        assert r["image_count"] == 3
        assert r["with_transition"] is True
        # 세션에 track + image*3 + transition*2 기록
        data = json.loads(out.read_text(encoding="utf-8"))
        op_types = [o["op"] for o in data["operations"]]
        assert op_types.count("add_image") == 3
        assert op_types.count("add_video_transition") == 2


# =========================================================================
# Phase 13 — session compact / find-replace
# =========================================================================


class TestSessionUtils:
    def test_compact_removes_dup_track(self, workspace):
        sp = workspace / "s.session.json"
        _json(["project", "new", "--name", "c1", "--preset", "square",
               "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        # 중복 add_track 2번 기록
        data = json.loads(sp.read_text(encoding="utf-8"))
        assert len([o for o in data["operations"] if o["op"] == "add_track"]) == 2
        r = _json(["session", "compact", "-p", str(sp)])
        assert r["status"] == "compacted"
        assert r["removed"] == 1
        data2 = json.loads(sp.read_text(encoding="utf-8"))
        assert len([o for o in data2["operations"] if o["op"] == "add_track"]) == 1

    def test_find_replace_media_literal(self, workspace):
        sp = workspace / "s.session.json"
        m1 = _png(workspace)
        _json(["project", "new", "--name", "fr1", "--preset", "square",
               "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        _json(["image", "add", "-p", str(sp), "-f", str(m1),
               "--start", "0s", "--duration", "1s", "--track", "V1"])
        # 파일 경로 일괄 치환 (존재하지 않는 대상으로 — dry-run에서만 안전)
        r = _json(["session", "find-replace-media", "-p", str(sp),
                   "--pattern", str(m1), "--replacement", "X:/dummy.png", "--dry-run"])
        assert r["count"] == 1
        # dry-run이라 실제 변경 없어야 함
        data = json.loads(sp.read_text(encoding="utf-8"))
        assert data["operations"][-1]["args"]["file"] == str(m1)


# =========================================================================
# Phase 8/10: MaskType alias
# =========================================================================


class TestAliasExpansion:
    def test_mask_circle_alias(self):
        r = _json(["alias", "resolve", "--class", "MaskType", "--name", "circle"])
        assert r["resolved"] == "圆形"


# =========================================================================
# Phase 11 — color postprocess op 기록
# =========================================================================


class TestColorPostprocess:
    def test_color_adjust_queued(self, workspace):
        sp = workspace / "s.session.json"
        media = _png(workspace)
        _json(["project", "new", "--name", "c1", "--preset", "square",
               "--draft-folder", str(workspace / "drafts"), "--output", str(sp)])
        _json(["track", "add", "-p", str(sp), "--type", "video", "--name", "V1"])
        r = _json(["image", "add", "-p", str(sp), "-f", str(media),
                   "--start", "0s", "--duration", "1s", "--track", "V1"])
        q = _json(["color", "adjust", "-p", str(sp), "--track", "V1",
                   "--segment-ref", r["id"], "--brightness", "0.2", "--saturation", "0.1"])
        assert q["type"] == "color_adjust"
        assert q["status"] == "queued"
