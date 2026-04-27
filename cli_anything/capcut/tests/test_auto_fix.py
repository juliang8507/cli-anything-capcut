"""auto-fix replay 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_anything.capcut.core.auto_fix import (
    explain_fix,
    replay_with_auto_fix,
    save_with_auto_fix,
)
from cli_anything.capcut.core.session import Session


# =========================================================================
# fixtures
# =========================================================================


@pytest.fixture
def drafts_folder(tmp_path):
    d = tmp_path / "drafts"
    d.mkdir()
    return d


@pytest.fixture
def fresh_session(tmp_path, drafts_folder):
    session_path = tmp_path / "s.session.json"
    session = Session.create(
        draft_folder=str(drafts_folder),
        draft_name="auto_fix_test",
        width=1280,
        height=720,
        fps=30,
        output=session_path,
    )
    # 기본 트랙 하나
    session.append_operation("add_track", {"type": "video", "name": "V1"})
    return session


def _tiny_png(path: Path) -> Path:
    path.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
        "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
        "49454e44ae426082"
    ))
    return path


# =========================================================================
# happy path
# =========================================================================


class TestHappyPath:
    def test_clean_session_empty_fix_report(self, fresh_session, tmp_path):
        img = _tiny_png(tmp_path / "a.png")
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "0s", "duration": "2s", "track": "V1",
        })
        script, fix_report = replay_with_auto_fix(fresh_session)
        assert fix_report == []
        assert script is not None

    def test_explain_fix_empty(self):
        assert "자동 수정 없음" in explain_fix([])


# =========================================================================
# broken op gets quarantined
# =========================================================================


class TestQuarantine:
    def test_unknown_op_is_quarantined(self, fresh_session, tmp_path):
        """지원하지 않는 op 가 있어도 나머지 op 는 성공해야 함."""
        img = _tiny_png(tmp_path / "a.png")
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "0s", "duration": "2s", "track": "V1",
        })
        fresh_session.append_operation("this_op_does_not_exist", {"foo": "bar"})
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "2s", "duration": "2s", "track": "V1",
        })

        script, fix_report = replay_with_auto_fix(fresh_session)
        assert len(fix_report) == 1
        assert fix_report[0]["op"] == "this_op_does_not_exist"
        assert fix_report[0]["attempt"] == 1
        assert fix_report[0]["op_id"]
        # 남은 두 image op 는 들어감 (V1 트랙 존재 + 2개 세그먼트)
        assert script is not None
        assert "V1" in script.tracks

    def test_bad_segment_ref_is_quarantined(self, fresh_session):
        """add_video_fade 의 segment_ref 가 존재 안 해도 다른 op 는 진행."""
        fresh_session.append_operation("add_video_fade", {
            "track": "V1",
            "segment_ref": "nonexistent_op_id",
            "fade_in": "500ms",
            "fade_out": "500ms",
        })
        script, fix_report = replay_with_auto_fix(fresh_session)
        assert len(fix_report) >= 1
        # 격리된 op 는 add_video_fade
        quarantined_ops = {r["op"] for r in fix_report}
        assert "add_video_fade" in quarantined_ops

    def test_multiple_bad_ops(self, fresh_session, tmp_path):
        img = _tiny_png(tmp_path / "a.png")
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "0s", "duration": "2s", "track": "V1",
        })
        fresh_session.append_operation("bad_op_1", {})
        fresh_session.append_operation("bad_op_2", {})
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "2s", "duration": "2s", "track": "V1",
        })

        script, fix_report = replay_with_auto_fix(fresh_session)
        assert len(fix_report) == 2
        op_names = {r["op"] for r in fix_report}
        assert op_names == {"bad_op_1", "bad_op_2"}

    def test_explain_fix_summarizes(self, fresh_session):
        fresh_session.append_operation("bad_op", {})
        _, fix_report = replay_with_auto_fix(fresh_session)
        summary = explain_fix(fix_report)
        assert "격리" in summary
        assert "bad_op" in summary


# =========================================================================
# max_attempts
# =========================================================================


class TestMaxAttempts:
    def test_max_attempts_bounded(self, fresh_session):
        """여러 bad op 가 있어도 max_attempts 제한 내에서 종료해야 함."""
        for _ in range(5):
            fresh_session.append_operation("bad_op", {})
        # 1차 replay_skip_errors 가 모두 수집하므로 보통 1 attempt 에 끝남.
        _, fix_report = replay_with_auto_fix(fresh_session, max_attempts=2)
        # 모든 bad op 가 attempt <= max_attempts 이내에서 격리돼야.
        for r in fix_report:
            assert r["attempt"] <= 2


# =========================================================================
# save_with_auto_fix (dry-run)
# =========================================================================


class TestSaveWithAutoFix:
    def test_dry_run_reports_fixes(self, fresh_session):
        fresh_session.append_operation("bad_op", {})
        result = save_with_auto_fix(fresh_session, dry_run=True)
        assert result["status"] == "dry_run_ok"
        assert result["draft_path"] is None
        assert len(result["fix_report"]) == 1
        assert "bad_op" in result["fix_summary"]

    def test_dry_run_clean_session(self, fresh_session, tmp_path):
        img = _tiny_png(tmp_path / "a.png")
        fresh_session.append_operation("add_image", {
            "file": str(img), "start": "0s", "duration": "2s", "track": "V1",
        })
        result = save_with_auto_fix(fresh_session, dry_run=True)
        assert result["status"] == "dry_run_ok"
        assert result["fix_report"] == []
        assert result["operation_count"] >= 2
