"""End-to-End 통합 테스트 — CLI subprocess로 실제 실행.

실제 CapCut 폴더 대신 임시 디렉토리를 ``--draft-folder`` 로 전달.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = "cli-anything-capcut"


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env["PYTHONIOENCODING"] = "utf-8"
    # E2E 테스트는 tmp_path 의 (비-ASCII) 원본 경로가 세션에 그대로 저장된다는
    # 가정을 유지하도록 한글 경로 스테이징 끔. 스테이징 자체는 test_staging 에서 검증.
    full_env.setdefault("CAPCUT_NO_STAGING", "1")
    if env:
        full_env.update(env)
    return subprocess.run(
        [CLI, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=full_env,
    )


def _json(args: list[str], env: dict | None = None) -> dict:
    proc = _run(["--json", *args], env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed ({proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
    return json.loads(proc.stdout)


@pytest.fixture
def workspace(tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    return tmp_path, drafts


def test_cli_loads():
    proc = _run(["--version"])
    assert proc.returncode == 0
    assert "cli-anything-capcut" in proc.stdout


def test_help_lists_all_groups():
    proc = _run(["--help"])
    assert proc.returncode == 0
    out = proc.stdout
    for cmd in ["project", "track", "video", "image", "audio", "text", "srt",
                "sticker", "effect", "keyframe", "color", "alias", "agent",
                "save", "validate", "undo", "history", "timeline", "stats",
                "import-recipe", "export-recipe", "batch", "merge-session"]:
        assert cmd in out, f"'{cmd}' missing from --help"


def test_diagnose_returns_json(workspace):
    info = _json(["diagnose"])
    assert "cli_version" in info
    assert info["python"].startswith("3.")


def test_full_workflow_draft(workspace, tmp_path):
    """project new → track → image × 2 → save → validate → undo."""
    _, drafts = workspace
    session_path = tmp_path / "wf.session.json"
    media = _make_test_image(tmp_path)

    info = _json([
        "project", "new", "--name", "wf-test",
        "--preset", "square",
        "--draft-folder", str(drafts),
        "--output", str(session_path),
    ])
    assert info["status"] == "created"
    assert Path(info["session_path"]).exists()

    _json(["track", "add", "-p", str(session_path), "--type", "video", "--name", "V1"])
    _json([
        "image", "add", "-p", str(session_path),
        "-f", str(media), "--start", "0s", "--duration", "2s", "--track", "V1",
    ])
    _json([
        "image", "add", "-p", str(session_path),
        "-f", str(media), "--start", "auto", "--duration", "2s", "--track", "V1",
    ])

    val = _json(["validate", "-p", str(session_path)])
    assert val["valid"] is True
    assert val["operation_count"] == 3
    assert val["duration_us"] == 4_000_000

    save = _json(["save", "-p", str(session_path)])
    assert save["status"] == "saved"
    draft_path = Path(save["draft_path"])
    assert (draft_path / "draft_content.json").exists()
    assert (draft_path / "draft_meta_info.json").exists()  # CapCut 목록 노출 핵심

    # 마지막 op 되돌리기
    undo = _json(["undo", "-p", str(session_path), "-n", "1"])
    assert undo["count"] == 1


def test_alias_resolve():
    out = _json(["alias", "resolve", "--class", "VideoSceneEffectType", "--name", "vignette"])
    assert out["resolved"] == "暗角"


def test_alias_search():
    hits = _json(["alias", "search", "--class", "VideoSceneEffectType", "-k", "glow", "--limit", "5"])
    assert isinstance(hits, list)
    assert any(h.get("alias") == "glow" or "glow" in (h.get("name", "") or "").lower() for h in hits)


def test_recipe_roundtrip(workspace, tmp_path):
    """레시피 export → import 라운드트립."""
    _, drafts = workspace
    session_path = tmp_path / "rt.session.json"
    recipe_path = tmp_path / "rt.recipe.json"
    media = _make_test_image(tmp_path)

    _json([
        "project", "new", "--name", "rt", "--preset", "square",
        "--draft-folder", str(drafts), "--output", str(session_path),
    ])
    _json(["track", "add", "-p", str(session_path), "--type", "video", "--name", "V1"])
    _json(["image", "add", "-p", str(session_path), "-f", str(media),
           "--start", "0s", "--duration", "1s", "--track", "V1"])

    # export
    proc = _run(["--json", "export-recipe", "-p", str(session_path), "-o", str(recipe_path)])
    assert proc.returncode == 0
    assert recipe_path.exists()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe.get("name") is not None
    assert len(recipe["operations"]) == 2

    # 새 세션에 import
    new_session_path = tmp_path / "rt2.session.json"
    _json([
        "project", "new", "--name", "rt2", "--preset", "square",
        "--draft-folder", str(drafts), "--output", str(new_session_path),
    ])
    result = _json(["import-recipe", "-p", str(new_session_path), "-f", str(recipe_path)])
    assert result["status"] == "applied"
    assert result["applied_count"] == 2


def test_validate_recipe_warns_no_track(tmp_path):
    """레시피에 add_track 없이 미디어만 있으면 경고."""
    recipe = {
        "operations": [
            {"op": "add_image", "args": {"file": "x.png", "track": "V1",
                                         "start": "0s", "duration": "1s"}},
        ]
    }
    p = tmp_path / "warn.recipe.json"
    p.write_text(json.dumps(recipe), encoding="utf-8")
    out = _json(["validate-recipe", "-f", str(p)])
    assert out["valid"] is True
    assert any("track" in w.lower() for w in out.get("warnings", []))


# =========================================================================
# helpers
# =========================================================================


def _make_test_image(tmp_path: Path) -> Path:
    """1x1 PNG 생성 (pyCapCut에 입력으로 충분)."""
    png_path = tmp_path / "test.png"
    # 1x1 PNG 바이너리 (투명)
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
        "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
        "49454e44ae426082"
    )
    png_path.write_bytes(png_bytes)
    return png_path
