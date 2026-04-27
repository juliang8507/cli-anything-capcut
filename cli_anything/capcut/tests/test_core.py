"""Core 유닛 테스트.

pytest로 실행::

    cd agent-harness-new
    python -m pytest cli_anything/capcut/tests -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cli_anything.capcut.core.session import Session, SessionError
from cli_anything.capcut.core.time_utils import (
    calc_auto_start,
    format_duration,
    parse_time_value,
    resolve_start_time,
)


# =========================================================================
# time_utils
# =========================================================================


class TestParseTimeValue:
    """버그 리포트 #1 회귀 방지 — bare numeric 문자열도 제대로 파싱되어야."""

    def test_integer_microseconds(self):
        assert parse_time_value(3_000_000) == 3_000_000

    def test_seconds_string(self):
        assert parse_time_value("3s") == 3_000_000

    def test_milliseconds_string(self):
        assert parse_time_value("500ms") == 500_000

    def test_compound_string(self):
        assert parse_time_value("1m30s") == 90_000_000

    def test_bare_microseconds_string(self):
        """버그 #1의 핵심 — tim()이 0을 반환하는 케이스."""
        assert parse_time_value("3000000") == 3_000_000

    def test_bare_decimal_seconds(self):
        """소수는 초로 해석."""
        assert parse_time_value("3.5") == 3_500_000

    def test_none_returns_zero(self):
        assert parse_time_value(None) == 0

    def test_empty_string(self):
        assert parse_time_value("") == 0

    def test_invalid_string(self):
        assert parse_time_value("abc") == 0


class TestFormatDuration:
    def test_seconds(self):
        assert format_duration(1_500_000) == "1.5s"

    def test_minutes_seconds(self):
        assert format_duration(90_000_000) == "1m30s"


class TestAutoStart:
    def test_empty_session(self):
        assert calc_auto_start({"operations": []}) == 0

    def test_stacks_segments(self):
        data = {
            "operations": [
                {"op": "add_image", "args": {"start": "0s", "duration": "3s", "track": "V1"}},
                {"op": "add_image", "args": {"start": "3s", "duration": "2s", "track": "V1"}},
            ]
        }
        assert calc_auto_start(data, "V1") == 5_000_000

    def test_track_filter(self):
        data = {
            "operations": [
                {"op": "add_image", "args": {"start": "0s", "duration": "3s", "track": "V1"}},
                {"op": "add_audio", "args": {"start": "0s", "duration": "10s", "track": "A1"}},
            ]
        }
        assert calc_auto_start(data, "V1") == 3_000_000
        assert calc_auto_start(data, "A1") == 10_000_000


class TestResolveStartTime:
    def test_auto_on_empty(self):
        assert resolve_start_time({"operations": []}, "auto") == "0us"

    def test_absolute_passes_through(self):
        assert resolve_start_time({"operations": []}, "5s") == "5s"

    def test_relative_offset(self):
        data = {
            "operations": [
                {"op": "add_image", "args": {"start": "0s", "duration": "3s", "track": "V1"}},
            ]
        }
        # auto_start = 3s, +500ms = 3.5s = 3_500_000us
        assert resolve_start_time(data, "+500ms", "V1") == "3500000us"


# =========================================================================
# Session
# =========================================================================


@pytest.fixture
def tmp_session(tmp_path):
    session = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="test-draft",
        width=1080,
        height=1080,
        fps=30,
        output=tmp_path / "test.session.json",
    )
    return session


class TestSessionLifecycle:
    def test_create_writes_file(self, tmp_session):
        assert tmp_session.path.exists()
        data = json.loads(tmp_session.path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 2
        assert data["draft_name"] == "test-draft"
        assert data["operations"] == []

    def test_load_roundtrip(self, tmp_session):
        loaded = Session.load(tmp_session.path)
        assert loaded.draft_name == "test-draft"
        assert loaded.data["width"] == 1080

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(SessionError):
            Session.load(tmp_path / "missing.session.json")


class TestSessionOperations:
    def test_append_assigns_id(self, tmp_session):
        r = tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        assert r["id"] == "op_1"
        assert tmp_session.operation_count == 1

    def test_append_filters_none(self, tmp_session):
        tmp_session.append_operation("add_track", {"type": "video", "name": None})
        op = tmp_session.data["operations"][0]
        assert "name" not in op["args"]

    def test_undo_removes_last(self, tmp_session):
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_track", {"type": "audio", "name": "A1"})
        removed = tmp_session.undo(1)
        assert len(removed) == 1
        assert tmp_session.operation_count == 1

    def test_undo_with_type_filter(self, tmp_session):
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        tmp_session.append_operation("add_image", {"file": "x.png"})
        removed = tmp_session.undo(1, op_type="track")
        assert len(removed) == 1
        assert removed[0]["op"] == "add_track"


class TestSrtParser:
    """SRT 파서 견고함 (2차 리뷰 대응)."""

    def test_comma_timestamps(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\n00:00:01,000 --> 00:00:03,500\nhello\n"
        out = _parse_srt(srt)
        assert len(out) == 1
        assert out[0]["start_us"] == 1_000_000
        assert out[0]["end_us"] == 3_500_000

    def test_dot_timestamps(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\n00:00:01.000 --> 00:00:03.500\nhello\n"
        assert len(_parse_srt(srt)) == 1

    def test_crlf_and_cr_line_endings(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\na\r\n\r\n2\r\n00:00:02,000 --> 00:00:03,000\r\nb\r\n"
        assert len(_parse_srt(srt)) == 2

    def test_missing_index_ok(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "00:00:01,000 --> 00:00:02,000\nhello\n"
        assert len(_parse_srt(srt)) == 1

    def test_invalid_block_skipped(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\nNOT A TIMESTAMP\nhello\n\n2\n00:00:01,000 --> 00:00:02,000\nok\n"
        out = _parse_srt(srt)
        assert len(out) == 1
        assert out[0]["text"] == "ok"

    def test_empty_text_skipped(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\n00:00:01,000 --> 00:00:02,000\n\n2\n00:00:02,000 --> 00:00:03,000\nok\n"
        assert len(_parse_srt(srt)) == 1

    def test_end_before_start_skipped(self):
        from cli_anything.capcut.commands.text import _parse_srt
        srt = "1\n00:00:03,000 --> 00:00:01,000\nbad\n"
        assert _parse_srt(srt) == []


class TestSessionAtomicWrite:
    def test_temp_file_cleaned_up(self, tmp_path):
        session = Session.create(
            draft_folder=str(tmp_path / "drafts"),
            draft_name="atomic",
            width=1080,
            height=1080,
            fps=30,
            output=tmp_path / "atomic.session.json",
        )
        session.append_operation("add_track", {"type": "video", "name": "V1"})
        # atomic rename 끝난 뒤 .tmp 파일이 남아있지 않아야
        assert list(tmp_path.glob("*.tmp")) == []


class TestV1Migration:
    def test_adds_schema_version_and_ids(self, tmp_path):
        v1 = {
            "draft_folder": "x",
            "draft_name": "y",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "operations": [
                {"op": "add_track", "args": {"type": "video"}},
                {"op": "add_image", "args": {"file": "a.png"}},
            ],
        }
        p = tmp_path / "v1.session.json"
        p.write_text(json.dumps(v1), encoding="utf-8")
        session = Session.load(p)
        assert session.data["schema_version"] == 2
        assert session.data["operations"][0]["id"] == "op_1"
        assert session.data["operations"][1]["id"] == "op_2"
