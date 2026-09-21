"""CapCut draft_content.json을 분석용 세션 JSON으로 역변환한다."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import click

from cli_anything.capcut.commands.helpers import output_result
from cli_anything.capcut.core.session import Session


DRAFT_CONTENT_FILENAME = "draft_content.json"
IMPORT_NOTE_KO = (
    "CapCut draft의 최종 상태를 손실 변환한 읽기 전용 분석용 세션입니다. "
    "편집 op 순서·이력과 modifier op(마스크·애니메이션·트랜지션·효과)는 "
    "복원되지 않으며 save 시 원본과 다른 draft가 만들어질 수 있습니다."
)


def _resolve_draft_json(source: Path) -> Path:
    draft_json = source / DRAFT_CONTENT_FILENAME if source.is_dir() else source
    if not draft_json.is_file():
        raise click.ClickException(f"draft_content.json을 찾을 수 없습니다: {draft_json}")
    return draft_json.resolve()


def _read_draft(draft_json: Path) -> dict[str, Any]:
    try:
        data = json.loads(draft_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise click.ClickException(f"draft_content.json 파싱 실패: {error}") from error
    except OSError as error:
        raise click.ClickException(f"draft_content.json 읽기 실패: {error}") from error
    if not isinstance(data, dict):
        raise click.ClickException("draft_content.json 최상위 값은 JSON 객체여야 합니다.")
    return data


def _material_index(materials: dict[str, Any], collection: str) -> dict[str, dict]:
    entries = materials.get(collection, [])
    if not isinstance(entries, list):
        return {}
    return {
        item["id"]: item
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _reference_type_index(materials: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for collection, entries in materials.items():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                index.setdefault(item["id"], collection)
    return index


def _time_arg(timerange: Any, field: str) -> str:
    if not isinstance(timerange, dict):
        return "0us"
    value = timerange.get(field, 0)
    try:
        return f"{int(value)}us"
    except (TypeError, ValueError, OverflowError):
        return "0us"


def _optional_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nested_value(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_text_color(fill: Any) -> list[float] | None:
    if isinstance(fill, (list, tuple)):
        color = fill
    else:
        color = None
        for path in (
            ("color",),
            ("solid", "color"),
            ("content", "color"),
            ("content", "solid", "color"),
        ):
            candidate = _nested_value(fill, path)
            if isinstance(candidate, (list, tuple)) and len(candidate) >= 3:
                color = candidate
                break
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return None
    try:
        return [float(component) for component in color[:3]]
    except (TypeError, ValueError):
        return None


def _parse_text_material(material: dict[str, Any]) -> dict[str, Any]:
    raw_content = material.get("content")
    if isinstance(raw_content, str):
        content = json.loads(raw_content)
    elif isinstance(raw_content, dict):
        content = raw_content
    else:
        raise ValueError("content가 JSON 문자열 또는 객체가 아님")
    if not isinstance(content, dict) or not isinstance(content.get("text"), str):
        raise ValueError("content.text가 문자열이 아님")

    styles = content.get("styles")
    style = styles[0] if isinstance(styles, list) and styles and isinstance(styles[0], dict) else {}
    size = style.get("size", material.get("font_size"))
    parsed: dict[str, Any] = {"text": content["text"]}
    if size is not None:
        parsed["size"] = _optional_float(size, 0.0)
    color = _extract_text_color(style.get("fill"))
    if color is not None:
        parsed["color"] = color
    return parsed


_TRACK_NAME_PREFIXES = {
    "video": "V",
    "audio": "A",
    "text": "T",
    "effect": "E",
    "sticker": "S",
    "filter": "F",
}

_PLACEHOLDER_PREFIX = "##_draftpath_placeholder_"
_PLACEHOLDER_SEPARATOR = "_##/"


def _assign_track_names(tracks: list[dict[str, Any]]) -> int:
    """CapCut GUI가 만든 draft는 트랙 name이 비어 있다. 타입별 순번으로 채운다."""
    used = {
        track["name"]
        for track in tracks
        if isinstance(track.get("name"), str) and track["name"].strip()
    }
    counters: Counter[str] = Counter()
    auto_named = 0
    for track in tracks:
        name = track.get("name")
        if isinstance(name, str) and name.strip():
            continue
        track_type = track.get("type")
        prefix = _TRACK_NAME_PREFIXES.get(str(track_type)) or str(track_type)[:1].upper() or "X"
        while True:
            counters[prefix] += 1
            candidate = f"{prefix}{counters[prefix]}"
            if candidate not in used:
                break
        track["name"] = candidate
        used.add(candidate)
        auto_named += 1
    return auto_named


def _resolve_placeholder_path(raw: str, draft_folder: Path) -> str | None:
    """##_draftpath_placeholder_<UUID>_##/<상대경로>를 draft 폴더 절대경로로 바꾼다."""
    if not raw.startswith(_PLACEHOLDER_PREFIX):
        return None
    _, separator, relative = raw.partition(_PLACEHOLDER_SEPARATOR)
    if not separator or not relative:
        return None
    return str((draft_folder / relative).resolve())


def _resolve_media_paths(
    material_indexes: dict[str, dict[str, dict]],
    tracks: list[dict[str, Any]],
    draft_folder: Path,
    warnings: list[str],
) -> int:
    """draft 폴더 기준 플레이스홀더 경로를 실제 경로로 치환한다. 절대경로는 그대로 둔다."""
    referenced = {
        segment.get("material_id")
        for track in tracks
        for segment in (track.get("segments") or [])
        if isinstance(segment, dict)
    }
    resolved_count = 0
    for collection in ("videos", "audios"):
        for material_id, material in material_indexes.get(collection, {}).items():
            raw = material.get("path")
            if not isinstance(raw, str) or not raw:
                continue
            resolved = _resolve_placeholder_path(raw, draft_folder)
            if resolved is None:
                continue
            material["path"] = resolved
            resolved_count += 1
            if material_id in referenced and not Path(resolved).exists():
                warnings.append(f"draft 폴더 안 소재를 찾을 수 없습니다: {resolved}")
    return resolved_count


def _summarize_extra_material_refs(
    tracks: list[dict[str, Any]],
    reference_types: dict[str, str],
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    total_refs = 0
    total_unrestored = 0
    for track in tracks:
        if not isinstance(track, dict):
            continue
        for segment in track.get("segments", []):
            if not isinstance(segment, dict):
                continue
            refs = segment.get("extra_material_refs")
            if not isinstance(refs, list) or not refs:
                continue
            material_types = sorted(
                {reference_types.get(ref, "unknown") for ref in refs if isinstance(ref, str)}
            )
            unrestored = sum(
                1 for ref in refs if reference_types.get(ref, "unknown") != "speeds"
            )
            total_refs += len(refs)
            total_unrestored += unrestored
            segments.append(
                {
                    "track": track.get("name"),
                    "track_type": track.get("type"),
                    "segment_id": segment.get("id"),
                    "reference_count": len(refs),
                    "unrestored_reference_count": unrestored,
                    "material_types": material_types,
                }
            )
    return {
        "segment_count": len(segments),
        "reference_count": total_refs,
        "unrestored_reference_count": total_unrestored,
        "segments": segments,
    }


def _append_track_segments(
    session: Session,
    track: dict[str, Any],
    material_indexes: dict[str, dict[str, dict]],
    warnings: list[str],
    unsupported_segments: Counter[str],
) -> int:
    track_type = track.get("type")
    track_name = track.get("name")
    segments = track.get("segments", [])
    if not isinstance(segments, list):
        return 0
    if track_type not in {"video", "audio", "text"}:
        if segments:
            unsupported_segments[str(track_type)] += len(segments)
        return 0

    collection = {"video": "videos", "audio": "audios", "text": "texts"}[track_type]
    restored = 0
    for segment_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            warnings.append(f"트랙 {track_name!r}의 세그먼트 #{segment_index} 형식이 잘못되어 건너뜀")
            continue
        material_id = segment.get("material_id")
        material = material_indexes[collection].get(material_id)
        if material is None:
            warnings.append(
                f"트랙 {track_name!r} 세그먼트 {segment.get('id') or segment_index!r}: "
                f"material_id {material_id!r}를 {collection}에서 찾지 못해 건너뜀"
            )
            continue

        timerange = segment.get("target_timerange")
        args: dict[str, Any] = {
            "start": _time_arg(timerange, "start"),
            "duration": _time_arg(timerange, "duration"),
            "track": track_name,
        }
        if track_type == "video":
            file_path = material.get("path")
            material_type = material.get("type")
            if not isinstance(file_path, str) or not file_path:
                warnings.append(f"video material {material_id!r}에 path가 없어 세그먼트를 건너뜀")
                continue
            args["file"] = file_path
            if material_type == "video":
                args["speed"] = _optional_float(segment.get("speed"), 1.0)
                args["volume"] = _optional_float(segment.get("volume"), 1.0)
                op_name = "add_video"
            elif material_type == "photo":
                op_name = "add_image"
            else:
                warnings.append(
                    f"video material {material_id!r}의 type {material_type!r}을 알 수 없어 건너뜀"
                )
                continue
        elif track_type == "audio":
            file_path = material.get("path")
            if not isinstance(file_path, str) or not file_path:
                warnings.append(f"audio material {material_id!r}에 path가 없어 세그먼트를 건너뜀")
                continue
            args["file"] = file_path
            args["volume"] = _optional_float(segment.get("volume"), 1.0)
            op_name = "add_audio"
        else:
            try:
                args.update(_parse_text_material(material))
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                warnings.append(
                    f"text material {material_id!r}의 content 파싱 실패로 세그먼트를 건너뜀: {error}"
                )
                continue
            op_name = "add_text"

        session.append_operation(op_name, args)
        restored += 1
    return restored


@click.command(
    "import-draft",
    help="CapCut draft_content.json을 읽기 전용 분석용 세션 JSON으로 역변환",
)
@click.option(
    "--from",
    "source",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="드래프트 폴더 또는 draft_content.json 경로",
)
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path), help="세션 JSON 출력 경로")
@click.option("--draft-folder", default=None, type=click.Path(path_type=Path), help="향후 save 대상 폴더")
@click.pass_context
def import_draft_cmd(ctx: click.Context, source: Path, output: Path, draft_folder: Path | None) -> None:
    draft_json = _resolve_draft_json(source)
    output_path = output.resolve()
    if output_path == draft_json:
        raise click.ClickException("출력 세션 경로는 원본 draft_content.json과 달라야 합니다.")

    draft = _read_draft(draft_json)
    canvas = draft.get("canvas_config") if isinstance(draft.get("canvas_config"), dict) else {}
    width = int(canvas.get("width", 1920))
    height = int(canvas.get("height", 1080))
    fps = draft.get("fps", 30)
    if not isinstance(fps, (int, float)):
        fps = 30

    source_name = draft_json.parent.name
    imported_draft_name = f"{source_name}-imported"
    target_draft_folder = (
        str(draft_folder)
        if draft_folder is not None
        else str(output_path.parent / "imported_drafts")
    )

    materials = draft.get("materials") if isinstance(draft.get("materials"), dict) else {}
    material_indexes = {
        collection: _material_index(materials, collection)
        for collection in ("videos", "audios", "texts")
    }
    tracks = draft.get("tracks") if isinstance(draft.get("tracks"), list) else []
    typed_tracks = [track for track in tracks if isinstance(track, dict)]
    warnings: list[str] = []
    auto_named_track_count = _assign_track_names(typed_tracks)
    resolved_media_count = _resolve_media_paths(
        material_indexes, typed_tracks, draft_json.parent, warnings
    )
    extra_material_refs = _summarize_extra_material_refs(
        typed_tracks,
        _reference_type_index(materials),
    )

    session = Session.create(
        target_draft_folder,
        imported_draft_name,
        width=width,
        height=height,
        fps=fps,
        output=output_path,
    )
    session.data.update(
        {
            "imported_from": str(draft_json),
            "import_note_ko": IMPORT_NOTE_KO,
            "lossy": True,
        }
    )

    unsupported_segments: Counter[str] = Counter()
    restored_segments = 0
    with session.batch():
        for track in typed_tracks:
            session.append_operation(
                "add_track",
                {"type": track.get("type"), "name": track.get("name")},
            )
        for track in typed_tracks:
            restored_segments += _append_track_segments(
                session,
                track,
                material_indexes,
                warnings,
                unsupported_segments,
            )

    for track_type, count in unsupported_segments.items():
        warnings.append(
            f"{track_type} 트랙 세그먼트 {count}개는 대응 세션 op가 없어 복원하지 않음"
        )
    if extra_material_refs["unrestored_reference_count"]:
        warnings.append(
            "extra_material_refs의 modifier 참조 "
            f"{extra_material_refs['unrestored_reference_count']}개는 요약만 기록하고 복원하지 않음"
        )

    result_payload: dict[str, Any] = {
            "status": "imported",
            "session_path": str(session.path),
            "imported_from": str(draft_json),
            "draft_folder": target_draft_folder,
            "draft_name": imported_draft_name,
            "track_count": len(typed_tracks),
            "auto_named_track_count": auto_named_track_count,
            "resolved_media_path_count": resolved_media_count,
            "segment_count": restored_segments,
            "operation_count": session.operation_count,
            "lossy": True,
            "notice_ko": "이 세션은 분석용이며 save 시 원본과 달라질 수 있습니다.",
            "warnings": warnings,
            "unsupported_segments": dict(unsupported_segments),
            "extra_material_refs": extra_material_refs,
    }
    if auto_named_track_count:
        result_payload["track_name_notice_ko"] = (
            f"트랙 이름이 없어 {auto_named_track_count}개를 자동 명명했습니다."
        )
    output_result(result_payload, ctx.obj["json"])

