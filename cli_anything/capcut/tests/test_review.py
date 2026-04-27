"""review 커맨드 테스트.

체크별 단위 테스트 + CLI 통합 테스트. ffprobe는 없어도 나머지는 모두 실행 가능.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.commands.review import (
    Finding,
    check_duration,
    check_gaps,
    check_media_files,
    check_overlaps,
    check_resolution_mismatch,
    check_subtitle_pacing,
    check_unsupported_for_render,
    check_volume_clipping,
    filter_by_severity,
    format_findings_human,
    review_cmd,
    run_review,
    summarize_findings,
)


def _build_standalone_cli():
    """team-lead의 capcut_cli에 review가 등록되었는지와 무관하게 테스트할 수 있도록,
    review_cmd만 등록한 standalone group을 만든다."""

    @click.group()
    @click.option("--json", "as_json", is_flag=True)
    @click.pass_context
    def root(ctx, as_json):
        ctx.ensure_object(dict)
        ctx.obj["json"] = as_json

    root.add_command(review_cmd)
    return root


def _resolve_cli():
    """capcut_cli.cli에 review가 등록되어 있으면 그걸, 아니면 standalone을 사용."""
    if "review" in cli.commands:
        return cli
    return _build_standalone_cli()
from cli_anything.capcut.core.session import Session


# =========================================================================
# fixtures
# =========================================================================


@pytest.fixture
def tmp_session(tmp_path):
    return Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="review-test",
        width=1920,
        height=1080,
        fps=30,
        output=tmp_path / "t.session.json",
    )


@pytest.fixture
def vertical_session(tmp_path):
    return Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="vertical",
        width=1080,
        height=1920,
        fps=30,
        output=tmp_path / "v.session.json",
    )


def _add_video(session, path, start, duration, track="V1"):
    session.append_operation(
        "add_video",
        {
            "file": str(path),
            "start": start,
            "duration": duration,
            "track": track,
        },
    )


def _add_audio(session, path, start, duration, track="A1", volume=1.0):
    session.append_operation(
        "add_audio",
        {
            "file": str(path),
            "start": start,
            "duration": duration,
            "track": track,
            "volume": volume,
        },
    )


def _add_text(session, text, start, duration, track="T1"):
    session.append_operation(
        "add_text",
        {
            "text": text,
            "start": start,
            "duration": duration,
            "track": track,
        },
    )


def _ghost_file(tmp_path, name="x.mp4"):
    p = tmp_path / name
    p.write_bytes(b"x")
    return p


# =========================================================================
# check_gaps
# =========================================================================


class TestCheckGaps:
    def test_no_gap(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "2s", "2s")
        assert check_gaps(tmp_session) == []

    def test_small_gap_ignored(self, tmp_session, tmp_path):
        """1초 미만 갭은 무시 (의도적 연출 가능성)."""
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "2s500ms", "2s")  # 0.5s 갭
        assert check_gaps(tmp_session) == []

    def test_warning_gap(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "4s", "2s")  # 2s 갭
        findings = check_gaps(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "V1" in findings[0].message

    def test_error_gap_5s(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "10s", "2s")  # 8s 갭
        findings = check_gaps(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "error"


# =========================================================================
# check_overlaps
# =========================================================================


class TestCheckOverlaps:
    def test_no_overlap(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "2s", "2s")
        assert check_overlaps(tmp_session) == []

    def test_overlap_is_error(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "3s")
        _add_video(tmp_session, f, "2s", "2s")  # 1s 겹침
        findings = check_overlaps(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "V1" in findings[0].message


# =========================================================================
# check_volume_clipping
# =========================================================================


class TestCheckVolumeClipping:
    def test_single_audio_no_issue(self, tmp_session, tmp_path):
        a = _ghost_file(tmp_path, "a.mp3")
        _add_audio(tmp_session, a, "0s", "5s", track="A1", volume=1.0)
        assert check_volume_clipping(tmp_session) == []

    def test_concurrent_over_one_warns(self, tmp_session, tmp_path):
        """A1(1.0) + A2(0.8) = 1.8 → error (>1.5)."""
        a = _ghost_file(tmp_path, "a.mp3")
        _add_audio(tmp_session, a, "0s", "5s", track="A1", volume=1.0)
        _add_audio(tmp_session, a, "0s", "5s", track="A2", volume=0.8)
        findings = check_volume_clipping(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].location["total_volume"] >= 1.5

    def test_concurrent_warning_threshold(self, tmp_session, tmp_path):
        """A1(0.7) + A2(0.5) = 1.2 → warning."""
        a = _ghost_file(tmp_path, "a.mp3")
        _add_audio(tmp_session, a, "0s", "5s", track="A1", volume=0.7)
        _add_audio(tmp_session, a, "0s", "5s", track="A2", volume=0.5)
        findings = check_volume_clipping(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_non_overlapping_audio_ok(self, tmp_session, tmp_path):
        a = _ghost_file(tmp_path, "a.mp3")
        _add_audio(tmp_session, a, "0s", "2s", track="A1", volume=1.0)
        _add_audio(tmp_session, a, "3s", "2s", track="A2", volume=1.0)
        assert check_volume_clipping(tmp_session) == []


# =========================================================================
# check_subtitle_pacing
# =========================================================================


class TestCheckSubtitlePacing:
    def test_normal_pacing_ok(self, tmp_session):
        _add_text(tmp_session, "안녕하세요", "0s", "2s")  # 5글자/2s=2.5 cps
        assert check_subtitle_pacing(tmp_session) == []

    def test_too_short_duration(self, tmp_session):
        _add_text(tmp_session, "안녕", "0s", "500ms")  # 0.5s
        findings = check_subtitle_pacing(tmp_session)
        assert any("너무 짧아서" in f.message for f in findings)
        assert all(f.severity == "warning" for f in findings)

    def test_too_fast_cps(self, tmp_session):
        # 30자를 2초에 → 15 cps
        text = "가" * 30
        _add_text(tmp_session, text, "0s", "2s")
        findings = check_subtitle_pacing(tmp_session)
        assert any("초당" in f.message for f in findings)

    def test_too_long_info(self, tmp_session):
        _add_text(tmp_session, "읽기 편한 문장입니다", "0s", "15s")
        findings = check_subtitle_pacing(tmp_session)
        assert any(f.severity == "info" for f in findings)


# =========================================================================
# check_media_files
# =========================================================================


class TestCheckMediaFiles:
    def test_existing_file_ok(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        findings = check_media_files(tmp_session)
        # error 없어야
        assert all(f.severity != "error" for f in findings)

    def test_missing_file_error(self, tmp_session):
        tmp_session.append_operation(
            "add_video",
            {
                "file": "/definitely/not/here.mp4",
                "start": "0s",
                "duration": "2s",
                "track": "V1",
            },
        )
        findings = check_media_files(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "파일 누락" in findings[0].message


# =========================================================================
# check_resolution_mismatch
# =========================================================================


class TestCheckResolution:
    def test_skips_without_ffprobe_or_runs(self, tmp_session, tmp_path):
        """ffprobe 유무와 무관하게 예외 없이 리스트 반환."""
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        findings = check_resolution_mismatch(tmp_session)
        assert isinstance(findings, list)


# =========================================================================
# check_duration
# =========================================================================


class TestCheckDuration:
    def test_empty_is_error(self, tmp_session):
        findings = check_duration(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "빈 프로젝트" in findings[0].message

    def test_vertical_short_is_info(self, vertical_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(vertical_session, f, "0s", "10s")
        findings = check_duration(vertical_session)
        assert len(findings) == 1
        assert findings[0].severity == "info"

    def test_vertical_over_90s_warns(self, vertical_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(vertical_session, f, "0s", "120s")
        findings = check_duration(vertical_session)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "한계 초과" in findings[0].message

    def test_horizontal_short_is_info(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "10s")
        findings = check_duration(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "info"


# =========================================================================
# check_unsupported_for_render
# =========================================================================


class TestCheckRender:
    def test_clean_session_no_findings(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        _add_video(tmp_session, f, "0s", "2s")
        findings = check_unsupported_for_render(tmp_session)
        assert findings == []

    def test_unsupported_op_info(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        tmp_session.append_operation("add_track", {"type": "video", "name": "V1"})
        _add_video(tmp_session, f, "0s", "2s")
        # add_filter 는 headless 미지원
        tmp_session.append_operation(
            "add_filter",
            {
                "name": "vignette",
                "start": "0s",
                "duration": "2s",
                "track": "F1",
            },
        )
        findings = check_unsupported_for_render(tmp_session)
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert "add_filter" in findings[0].message


# =========================================================================
# run_review + filter_by_severity + summarize
# =========================================================================


class TestRunReview:
    def test_all_checks_execute(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "5s")
        findings = run_review(tmp_session)
        # 적어도 duration info 는 있어야
        assert any(f.check == "duration" for f in findings)

    def test_only_filter(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "10s", "2s")  # 8s gap
        findings = run_review(tmp_session, only=["gaps"])
        assert len(findings) >= 1
        # 전부 gaps 체크여야
        assert all(f.check == "gaps" for f in findings)

    def test_only_alias(self, tmp_session, tmp_path):
        """'audio' 는 'volume' 로 매핑."""
        a = _ghost_file(tmp_path, "a.mp3")
        _add_audio(tmp_session, a, "0s", "5s", track="A1", volume=1.0)
        _add_audio(tmp_session, a, "0s", "5s", track="A2", volume=0.8)
        findings = run_review(tmp_session, only=["audio"])
        assert all(f.check == "volume" for f in findings)
        assert len(findings) >= 1

    def test_unknown_check_warning(self, tmp_session):
        findings = run_review(tmp_session, only=["zzz_not_real"])
        # 알 수 없는 체크 → review warning 한 건
        assert any(f.check == "review" for f in findings)


class TestFilterBySeverity:
    def test_warning_threshold_drops_info(self):
        items = [
            Finding(check="a", severity="info", message="i"),
            Finding(check="a", severity="warning", message="w"),
            Finding(check="a", severity="error", message="e"),
        ]
        got = filter_by_severity(items, "warning")
        assert len(got) == 2
        assert [f.severity for f in got] == ["warning", "error"]

    def test_error_threshold_keeps_error_only(self):
        items = [
            Finding(check="a", severity="info", message="i"),
            Finding(check="a", severity="warning", message="w"),
            Finding(check="a", severity="error", message="e"),
        ]
        got = filter_by_severity(items, "error")
        assert [f.severity for f in got] == ["error"]


class TestSummarize:
    def test_status_ok_when_info_only(self):
        items = [Finding(check="a", severity="info", message="x")]
        s = summarize_findings(items)
        assert s["status"] == "ok"
        assert s["finding_count"]["info"] == 1

    def test_status_error_wins(self):
        items = [
            Finding(check="a", severity="warning", message="w"),
            Finding(check="a", severity="error", message="e"),
        ]
        s = summarize_findings(items)
        assert s["status"] == "error"
        assert s["finding_count"]["error"] == 1
        assert s["finding_count"]["warning"] == 1


class TestFormatHuman:
    def test_empty(self):
        out = format_findings_human([])
        assert "통과" in out

    def test_order_error_first(self):
        items = [
            Finding(check="a", severity="info", message="i"),
            Finding(check="b", severity="error", message="e"),
        ]
        out = format_findings_human(items)
        # ERROR 가 INFO 보다 먼저 나와야
        assert out.index("ERROR") < out.index("INFO")


# =========================================================================
# CLI 통합 (click.testing)
# =========================================================================


class TestReviewCli:
    def _run(self, args):
        return CliRunner().invoke(_resolve_cli(), args, obj={})

    def test_json_output_structure(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "10s", "2s")  # 8s gap → error
        result = self._run(
            ["--json", "review", "-p", str(tmp_session.path)]
        )
        # error 갭 때문에 종료코드 2
        assert result.exit_code == 2, result.output
        data = json.loads(result.output)
        assert "status" in data
        assert "finding_count" in data
        assert "findings" in data
        assert data["finding_count"]["error"] >= 1

    def test_only_filter_cli(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "2s")
        _add_video(tmp_session, f, "10s", "2s")  # gap
        result = self._run(
            ["--json", "review", "-p", str(tmp_session.path), "--only", "gaps"]
        )
        assert result.exit_code == 2
        data = json.loads(result.output)
        assert all(f["check"] == "gaps" for f in data["findings"])

    def test_severity_filter_cli(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "5s")  # duration info만
        # severity warning 이상만 → findings 비어야 (info 제외)
        result = self._run(
            [
                "--json",
                "review",
                "-p",
                str(tmp_session.path),
                "--severity",
                "warning",
            ]
        )
        # info 만 있었으므로 filter 후 빔 → status ok → exit 0
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["findings"] == []
        assert data["status"] == "ok"

    def test_human_output_contains_status(self, tmp_session, tmp_path):
        f = _ghost_file(tmp_path)
        _add_video(tmp_session, f, "0s", "5s")
        result = self._run(["review", "-p", str(tmp_session.path)])
        assert result.exit_code == 0
        assert "status=" in result.output
