"""미디어 세그먼트 그룹 — video / image / audio."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import (
    load_session,
    output_result,
    resolve_clip_settings,
)
from cli_anything.capcut.core.media_staging import (
    needs_staging,
    stage_media,
    staging_list,
    staging_stats,
    unstage_all,
)
from cli_anything.capcut.core.time_utils import resolve_start_time


def _maybe_stage(file: str) -> tuple[str, dict | None]:
    """필요 시 한글/특수경로 파일을 영문 캐시로 스테이징.

    CapCut 한글 경로 버그 대응. ``CAPCUT_NO_STAGING=1`` 로 비활성화 가능.
    """
    if not file or not needs_staging(file):
        return file, None
    staged, info = stage_media(file)
    return staged, info


def _segment_add(op_name: str, project_path: str, file: str, start: str, duration: str | None,
                 track: str | None, clip_settings: str | None, volume: float, speed: float,
                 as_json: bool):
    session = load_session(project_path)
    staged_file, staging_info = _maybe_stage(file)
    args = {
        "file": staged_file,
        "start": resolve_start_time(session.data, start, track_name=track),
        "duration": duration,
        "track": track,
        "clip_settings": resolve_clip_settings(clip_settings),
        "volume": volume if volume != 1.0 else None,
        "speed": speed if speed != 1.0 else None,
    }
    result = session.append_operation(op_name, args)
    if staging_info is not None:
        result["staging"] = staging_info
    output_result(result, as_json)


@click.group("video", help="비디오 세그먼트")
def video_group():
    pass


@video_group.command("add", help="비디오 세그먼트 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default=None)
@click.option("--track", default=None)
@click.option("--clip-settings", default=None,
              help="프리셋(subtitle-bottom, pip-top-right 등) 또는 JSON")
@click.option("--volume", type=float, default=1.0, show_default=True)
@click.option("--speed", type=float, default=1.0, show_default=True)
@click.pass_context
def video_add(ctx, project_path, file, start, duration, track, clip_settings, volume, speed):
    _segment_add("add_video", project_path, file, start, duration, track,
                 clip_settings, volume, speed, ctx.obj["json"])


@click.group("image", help="이미지 세그먼트")
def image_group():
    pass


@image_group.command("add", help="이미지 세그먼트 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default="3s", show_default=True)
@click.option("--track", default=None)
@click.option("--clip-settings", default=None)
@click.pass_context
def image_add(ctx, project_path, file, start, duration, track, clip_settings):
    _segment_add("add_image", project_path, file, start, duration, track,
                 clip_settings, 1.0, 1.0, ctx.obj["json"])


@click.group("audio", help="오디오 세그먼트")
def audio_group():
    pass


@audio_group.command("add", help="오디오 세그먼트 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default=None)
@click.option("--track", default=None)
@click.option("--volume", type=float, default=1.0, show_default=True)
@click.option("--speed", type=float, default=1.0, show_default=True)
@click.pass_context
def audio_add(ctx, project_path, file, start, duration, track, volume, speed):
    _segment_add("add_audio", project_path, file, start, duration, track,
                 None, volume, speed, ctx.obj["json"])


@audio_group.command("add-fade", help="오디오 세그먼트에 페이드 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--fade-in", default="0s", show_default=True)
@click.option("--fade-out", default="0s", show_default=True)
@click.pass_context
def audio_add_fade(ctx, project_path, track, segment_ref, fade_in, fade_out):
    session = load_session(project_path)
    result = session.append_operation(
        "add_audio_fade",
        {"track": track, "segment_ref": segment_ref, "fade_in": fade_in, "fade_out": fade_out},
    )
    output_result(result, ctx.obj["json"])


@audio_group.command("add-effect", help="오디오 세그먼트에 효과 추가 (echo, reverb, ...)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--name", required=True, help="효과 이름 (영어 별칭 또는 한자)")
@click.pass_context
def audio_add_effect(ctx, project_path, track, segment_ref, name):
    session = load_session(project_path)
    result = session.append_operation(
        "add_audio_effect",
        {"track": track, "segment_ref": segment_ref, "name": name},
    )
    output_result(result, ctx.obj["json"])


# video 그룹에 add-fade / add-transition / add-animation 부가 명령
@video_group.command("add-fade", help="비디오 세그먼트에 페이드 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--fade-in", default="0s", show_default=True)
@click.option("--fade-out", default="0s", show_default=True)
@click.pass_context
def video_add_fade(ctx, project_path, track, segment_ref, fade_in, fade_out):
    session = load_session(project_path)
    result = session.append_operation(
        "add_video_fade",
        {"track": track, "segment_ref": segment_ref, "fade_in": fade_in, "fade_out": fade_out},
    )
    output_result(result, ctx.obj["json"])


@video_group.command("add-transition", help="세그먼트 끝에 트랜지션 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--name", required=True, help="트랜지션 이름 (dissolve, slide_left, ...)")
@click.option("--duration", default="500ms", show_default=True)
@click.pass_context
def video_add_transition(ctx, project_path, track, segment_ref, name, duration):
    session = load_session(project_path)
    result = session.append_operation(
        "add_video_transition",
        {"track": track, "segment_ref": segment_ref, "name": name, "duration": duration},
    )
    output_result(result, ctx.obj["json"])


@video_group.command("add-animation", help="비디오 세그먼트에 애니메이션 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--role", type=click.Choice(["intro", "outro", "group"]), default="intro")
@click.option("--name", required=True, help="애니메이션 이름")
@click.option("--duration", default="500ms", show_default=True)
@click.pass_context
def video_add_animation(ctx, project_path, track, segment_ref, role, name, duration):
    session = load_session(project_path)
    result = session.append_operation(
        "add_video_animation",
        {"track": track, "segment_ref": segment_ref, "role": role,
         "name": name, "duration": duration},
    )
    output_result(result, ctx.obj["json"])


# ===========================================================================
# v0.4.3 복원 커맨드 — reverse / freeze-frame / blend-mode / chroma-key
# ===========================================================================

# 블렌드 모드 선택지 (postprocess.py BLEND_MODES 키 목록)
_BLEND_MODE_CHOICES = [
    "normal", "multiply", "screen", "overlay", "darken", "lighten",
    "add", "color-dodge", "color-burn", "hard-light", "soft-light",
    "difference", "exclusion",
]


@video_group.command("reverse", help="역재생 활성화")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.pass_context
def video_reverse(ctx, project_path, track, segment_ref):
    session = load_session(project_path)
    result = session.append_operation(
        "set_reverse",
        {"track": track, "segment_ref": segment_ref},
    )
    output_result(result, ctx.obj["json"])


@video_group.command("freeze-frame", help="프리즈 프레임 (속도=0)")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--duration", default=None, help="프리즈 유지 시간 (예: 2s). 기본: 세그먼트 길이 유지")
@click.pass_context
def video_freeze_frame(ctx, project_path, track, segment_ref, duration):
    session = load_session(project_path)
    args: dict = {"track": track, "segment_ref": segment_ref}
    if duration is not None:
        args["duration"] = duration
    result = session.append_operation("set_freeze_frame", args)
    output_result(result, ctx.obj["json"])


@video_group.command("blend-mode", help="블렌드 모드 설정")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--mode", required=True,
              type=click.Choice(_BLEND_MODE_CHOICES, case_sensitive=False),
              help="블렌드 모드")
@click.pass_context
def video_blend_mode(ctx, project_path, track, segment_ref, mode):
    session = load_session(project_path)
    result = session.append_operation(
        "set_blend_mode",
        {"track": track, "segment_ref": segment_ref, "mode": mode},
    )
    output_result(result, ctx.obj["json"])


@video_group.command("chroma-key", help="크로마 키(그린스크린) 효과 추가")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--color", default="#00FF00", show_default=True, help="키 색상 (hex, 기본: 그린)")
@click.option("--intensity", type=float, default=0.5, show_default=True,
              help="키 강도 (0.0~1.0)")
@click.option("--shadow", type=float, default=0.5, show_default=True,
              help="그림자 보정 (0.0~1.0)")
@click.option("--smoothness", type=float, default=0.1, show_default=True,
              help="엣지 부드러움 (0.0~1.0)")
@click.option("--spill", type=float, default=0.0, show_default=True,
              help="스필 억제 (0.0~1.0)")
@click.pass_context
def video_chroma_key(ctx, project_path, track, segment_ref, color, intensity,
                     shadow, smoothness, spill):
    session = load_session(project_path)
    result = session.append_operation(
        "set_chroma_key",
        {
            "track": track,
            "segment_ref": segment_ref,
            "color": color,
            "intensity": intensity,
            "shadow": shadow,
            "smoothness": smoothness,
            "spill": spill,
        },
    )
    output_result(result, ctx.obj["json"])


@video_group.command("lut", help="LUT 파일을 비디오 세그먼트에 적용")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--file", "lut_file", required=True,
              type=click.Path(exists=True),
              help="LUT 파일 경로 (.cube, .3dl 등)")
@click.option("--intensity", type=float, default=1.0, show_default=True,
              help="LUT 적용 강도 (0.0~1.0)")
@click.option("--name", default=None,
              help="LUT material 표시 이름 (기본: 파일 이름에서 추출)")
@click.pass_context
def video_lut(ctx, project_path, track, segment_ref, lut_file, intensity, name):
    session = load_session(project_path)
    result = session.append_operation(
        "add_lut",
        {
            "track": track,
            "segment_ref": segment_ref,
            "file": lut_file,
            "intensity": intensity,
            "name": name,
        },
    )
    output_result(result, ctx.obj["json"])


def _parse_speed_points(points_str: str) -> list[tuple[float, float]]:
    """'time_ratio,speed;time_ratio,speed;...' 형식 파싱."""
    result = []
    for part in points_str.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            t, s = part.split(",")
            result.append((float(t), float(s)))
        except ValueError:
            raise click.BadParameter(
                f"포인트 형식 오류: '{part}'. 'time_ratio,speed' 형식 필요 (예: '0.5,2.0')"
            )
    if not result:
        raise click.BadParameter("포인트가 비어 있음. 최소 2개 이상 필요")
    return result


@video_group.command("speed-curve", help="속도 커브(가변 속도) 적용")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--points", required=True,
              help="속도 포인트 'time_ratio,speed;...' (예: '0,1.0;0.5,2.0;1.0,1.0'). "
                   "time_ratio: 0.0~1.0 세그먼트 내 상대 위치, speed: 0.1~10.0")
@click.option("--curve-range", default=None,
              help="커브 유효 범위 JSON 배열 [start, end] (기본: [0.0, 1.0])")
@click.pass_context
def video_speed_curve(ctx, project_path, track, segment_ref, points, curve_range):
    import json as _json

    parsed_points = _parse_speed_points(points)

    parsed_range = [0.0, 1.0]
    if curve_range is not None:
        try:
            parsed_range = _json.loads(curve_range)
        except Exception:
            raise click.BadParameter(f"curve_range JSON 파싱 오류: '{curve_range}'")

    session = load_session(project_path)
    result = session.append_operation(
        "set_speed_curve",
        {
            "track": track,
            "segment_ref": segment_ref,
            "points": parsed_points,
            "curve_range": parsed_range,
        },
    )
    output_result(result, ctx.obj["json"])


@click.command("media-info", help="미디어 파일 정보 (ffprobe)")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def media_info_cmd(ctx, file):
    from cli_anything.capcut.core.time_utils import get_media_duration

    info = get_media_duration(file)
    if info is None:
        raise click.ClickException(
            f"미디어 정보를 가져올 수 없음: {file}\n"
            "ffprobe가 설치되어 있는지 확인."
        )
    output_result(info, ctx.obj["json"])


# =========================================================================
# staging 그룹 — 한글/공백 경로 캐시 관리
# =========================================================================


@click.group("staging", help="한글/공백 경로 미디어 스테이징 캐시 관리")
def staging_group():
    pass


@staging_group.command("stats", help="캐시 크기/파일 수")
@click.pass_context
def staging_stats_cmd(ctx):
    output_result(staging_stats(), ctx.obj["json"])


@staging_group.command("clear", help="캐시 비우기")
@click.pass_context
def staging_clear_cmd(ctx):
    before = staging_stats()
    removed = unstage_all()
    output_result(
        {
            "removed_files": removed,
            "freed_bytes": before.get("total_bytes", 0),
            "cache_dir": before.get("cache_dir"),
        },
        ctx.obj["json"],
    )


@staging_group.command("list", help="스테이징된 파일 목록")
@click.pass_context
def staging_list_cmd(ctx):
    files = staging_list()
    output_result(
        {
            "count": len(files),
            "files": files,
            "cache_dir": staging_stats().get("cache_dir"),
        },
        ctx.obj["json"],
    )
