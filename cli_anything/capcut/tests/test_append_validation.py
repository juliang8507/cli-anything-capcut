"""CLI 입력 경계의 operation 검증 회귀 테스트."""

from __future__ import annotations

import json

import pytest
from click import Group, Option
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.session import Session, SessionError


@pytest.fixture
def segment_session(tmp_path):
    session = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="append-validation",
        output=tmp_path / "append-validation.session.json",
    )
    track = session.append_operation(
        "add_track", {"type": "video", "name": "V1"},
    )
    segment = session.append_operation(
        "add_image",
        {
            "file": str(tmp_path / "clip.png"),
            "track": "V1",
            "start": "0s",
            "duration": "1s",
        },
    )
    return session, track, segment


def _invoke_keyframe(session: Session, segment_ref: str, track: str = "V1"):
    return CliRunner().invoke(
        cli,
        [
            "keyframe",
            "add",
            "-p",
            str(session.path),
            "--track",
            track,
            "--segment-ref",
            segment_ref,
            "--property",
            "alpha",
            "--time",
            "0s",
            "--value",
            "0.5",
        ],
    )


def test_cli_rejects_index_like_segment_ref_when_appending(segment_session):
    session, _, _ = segment_session

    result = _invoke_keyframe(session, "0")

    assert result.exit_code != 0
    assert "op ID" in result.output
    assert "history" in result.output
    assert Session.load(session.path).operation_count == 2


def test_cli_rejects_unknown_segment_ref_when_appending(segment_session):
    session, _, _ = segment_session

    result = _invoke_keyframe(session, "op_999")

    assert result.exit_code != 0
    assert "존재하지" in result.output
    assert "history" in result.output
    assert Session.load(session.path).operation_count == 2


def test_cli_rejects_non_segment_operation_ref(segment_session):
    session, track, _ = segment_session

    result = _invoke_keyframe(session, track["id"])

    assert result.exit_code != 0
    assert "세그먼트를 만드는 op" in result.output
    assert Session.load(session.path).operation_count == 2


def test_cli_rejects_segment_ref_from_another_track(segment_session):
    session, _, segment = segment_session
    session.append_operation("add_track", {"type": "video", "name": "V2"})

    result = _invoke_keyframe(session, segment["id"], track="V2")

    assert result.exit_code != 0
    assert "V1" in result.output
    assert "V2" in result.output
    assert Session.load(session.path).operation_count == 3


def test_cli_accepts_existing_segment_ref_on_same_track(segment_session):
    session, _, segment = segment_session

    result = _invoke_keyframe(session, segment["id"])

    assert result.exit_code == 0, result.output
    assert Session.load(session.path).data["operations"][-1]["op"] == "add_keyframe"


def test_session_api_remains_lenient_for_auto_fix_quarantine(segment_session):
    session, _, _ = segment_session

    result = session.append_operation(
        "add_keyframe",
        {
            "track": "V1",
            "segment_ref": "0",
            "property": "alpha",
            "time": "0s",
            "value": 0.5,
        },
    )

    assert result["status"] == "added"
    assert result["segment_ref"] == "0"


def test_edit_op_rejects_arg_not_read_by_registered_handler(segment_session):
    session, _, segment = segment_session
    mask = session.append_operation(
        "add_mask",
        {"track": "V1", "segment_ref": segment["id"], "name": "circle"},
    )

    result = CliRunner().invoke(
        cli,
        [
            "edit-op",
            "-p",
            str(session.path),
            "--index",
            str(mask["operation_index"]),
            "--args",
            json.dumps({"filter": "golden_hour"}),
        ],
    )

    assert result.exit_code != 0
    assert "filter" in result.output
    assert "add_mask" in result.output
    edited = Session.load(session.path).data["operations"][mask["operation_index"]]
    assert "filter" not in edited["args"]


def test_edit_op_accepts_arg_read_through_handler_static_loop(segment_session):
    session, _, segment = segment_session
    mask = session.append_operation(
        "add_mask",
        {"track": "V1", "segment_ref": segment["id"], "name": "circle"},
    )

    result = CliRunner().invoke(
        cli,
        [
            "edit-op",
            "-p",
            str(session.path),
            "--index",
            str(mask["operation_index"]),
            "--args",
            json.dumps({"feather": 0.25}),
        ],
    )

    assert result.exit_code == 0, result.output
    edited = Session.load(session.path).data["operations"][mask["operation_index"]]
    assert edited["args"]["feather"] == pytest.approx(0.25)


def test_edit_op_skips_arg_validation_for_noop_handler(segment_session):
    session, _, segment = segment_session
    queued = session.append_operation(
        "color_adjust",
        {"track": "V1", "segment_ref": segment["id"], "brightness": 0.1},
    )

    result = CliRunner().invoke(
        cli,
        [
            "edit-op",
            "-p",
            str(session.path),
            "--index",
            str(queued["operation_index"]),
            "--args",
            json.dumps({"future_extension": True}),
        ],
    )

    assert result.exit_code == 0, result.output


def test_pycapcut_missing_dedicated_track_error_has_korean_guidance(tmp_path):
    session = Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name="missing-track",
        output=tmp_path / "missing-track.session.json",
    )
    # append_operation의 전용 트랙 자동 생성은 우회해, 레거시/손상 세션을 재현한다.
    session.data["operations"].append(
        {
            "id": "op_1",
            "op": "add_filter",
            "args": {"name": "BW_2", "start": "0s", "duration": "1s"},
        },
    )

    with pytest.raises(SessionError) as exc_info:
        session.replay()

    message = str(exc_info.value)
    assert "호환되는 전용 트랙" in message
    assert "--track" in message
    assert "pycapcut 원문" in message
    assert "不存在接受" in message


def test_every_segment_ref_option_has_consistent_help():
    segment_ref_options: list[tuple[str, Option]] = []

    def visit(command, path: tuple[str, ...] = ()):
        for param in command.params:
            if isinstance(param, Option) and "--segment-ref" in param.opts:
                segment_ref_options.append((" ".join(path), param))
        if isinstance(command, Group):
            for name, child in command.commands.items():
                visit(child, (*path, name))

    visit(cli)

    assert segment_ref_options
    inconsistent = {
        path: option.help
        for path, option in segment_ref_options
        if option.help != "세그먼트 참조 (op ID)"
    }
    assert inconsistent == {}
