"""merge-session 트랙 충돌 정책 회귀 테스트."""

from __future__ import annotations

from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.op_registry import CREATION_OPS
from cli_anything.capcut.core.session import Session


def _make_session(tmp_path, name: str) -> Session:
    return Session.create(
        draft_folder=str(tmp_path / "drafts"),
        draft_name=name,
        output=tmp_path / f"{name}.session.json",
    )


def _make_test_image(tmp_path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
            "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
            "49454e44ae426082"
        )
    )
    return str(path)


def _merge_via_cli(destination: Session, source: Session) -> Session:
    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "merge-session",
            "-p",
            str(destination.path),
            "--other",
            str(source.path),
        ],
    )
    assert result.exit_code == 0, result.output
    return Session.load(destination.path)


def _creation_operations(session: Session) -> list[dict]:
    return [
        operation
        for operation in session.data["operations"]
        if operation["op"] in CREATION_OPS
    ]


def _assert_segment_refs_resolve(session: Session) -> None:
    segments_by_id = {
        operation["id"]: operation
        for operation in _creation_operations(session)
    }
    referring_operations = [
        operation
        for operation in session.data["operations"]
        if operation.get("args", {}).get("segment_ref") is not None
    ]

    assert referring_operations
    for operation in referring_operations:
        args = operation["args"]
        target = segments_by_id.get(args["segment_ref"])
        assert target is not None
        assert args["track"] == target["args"]["track"]


def test_merge_same_name_and_type_reuses_track_without_losing_segments(tmp_path):
    destination = _make_session(tmp_path, "same-type-a")
    destination.append_operation("add_track", {"type": "video", "name": "V1"})
    destination.append_operation(
        "add_image",
        {
            "file": _make_test_image(tmp_path, "a.png"),
            "track": "V1",
            "start": "0s",
            "duration": "1s",
        },
    )

    source = _make_session(tmp_path, "same-type-b")
    source.append_operation("add_track", {"type": "video", "name": "V1"})
    source_segment = source.append_operation(
        "add_image",
        {
            "file": _make_test_image(tmp_path, "b.png"),
            "track": "V1",
            "start": "1s",
            "duration": "1s",
        },
    )
    source.append_operation(
        "add_video_fade",
        {
            "track": "V1",
            "segment_ref": source_segment["id"],
            "fade_in": "100ms",
        },
    )
    expected_segment_count = len(_creation_operations(destination)) + len(
        _creation_operations(source)
    )

    merged = _merge_via_cli(destination, source)

    track_operations = [
        operation
        for operation in merged.data["operations"]
        if operation["op"] == "add_track"
    ]
    assert [(op["args"]["type"], op["args"]["name"]) for op in track_operations] == [
        ("video", "V1")
    ]
    assert len(_creation_operations(merged)) == expected_segment_count == 2
    _assert_segment_refs_resolve(merged)

    script = merged.replay()
    assert list(script.tracks) == ["V1"]
    assert len(script.tracks["V1"].segments) == expected_segment_count
    assert merged.validate()["valid"] is True


def test_merge_same_name_and_different_type_renames_track_and_references(tmp_path):
    destination = _make_session(tmp_path, "different-type-a")
    destination.append_operation("add_track", {"type": "text", "name": "V1"})
    destination.append_operation(
        "add_text",
        {"text": "destination", "track": "V1", "start": "0s", "duration": "1s"},
    )

    source = _make_session(tmp_path, "different-type-b")
    source.append_operation("add_track", {"type": "video", "name": "V1"})
    source_segment = source.append_operation(
        "add_image",
        {
            "file": _make_test_image(tmp_path, "incoming.png"),
            "track": "V1",
            "start": "1s",
            "duration": "1s",
        },
    )
    source.append_operation(
        "add_video_fade",
        {
            "track": "V1",
            "segment_ref": source_segment["id"],
            "fade_out": "100ms",
        },
    )
    expected_segment_count = len(_creation_operations(destination)) + len(
        _creation_operations(source)
    )

    merged = _merge_via_cli(destination, source)

    track_operations = [
        operation
        for operation in merged.data["operations"]
        if operation["op"] == "add_track"
    ]
    assert [
        (operation["args"]["type"], operation["args"]["name"])
        for operation in track_operations
    ] == [("text", "V1"), ("video", "V1_2")]

    incoming_operations = [
        operation
        for operation in merged.data["operations"]
        if operation["op"] in {"add_image", "add_video_fade"}
    ]
    assert incoming_operations
    assert {operation["args"]["track"] for operation in incoming_operations} == {"V1_2"}
    assert len(_creation_operations(merged)) == expected_segment_count == 2
    _assert_segment_refs_resolve(merged)

    script = merged.replay()
    assert set(script.tracks) == {"V1", "V1_2"}
    assert sum(len(track.segments) for track in script.tracks.values()) == expected_segment_count
    validation = merged.validate()
    assert len(validation["tracks"]) == 2
    assert validation["valid"] is True
