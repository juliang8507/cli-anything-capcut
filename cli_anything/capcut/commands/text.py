"""text 그룹 — 텍스트 세그먼트 + 스타일 패치 + 애니메이션 + SRT."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import (
    load_session,
    output_result,
    parse_color,
    parse_json_option,
    resolve_clip_settings,
)
from cli_anything.capcut.core import style_registry
from cli_anything.capcut.core.time_utils import parse_time_value, resolve_start_time


@click.group("text", help="텍스트 세그먼트")
def text_group():
    pass


@text_group.command("add", help="텍스트 추가 (폰트/테두리/그림자/색/위치 모두)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-t", "--text", required=True, help="표시할 텍스트")
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default="3s", show_default=True)
@click.option("--track", default=None)
@click.option("--font", default=None, help="폰트 이름 (영어 별칭 또는 한자)")
@click.option("--size", type=float, default=None)
@click.option("--bold", is_flag=True, default=None)
@click.option("--italic", is_flag=True, default=None)
@click.option("--underline", is_flag=True, default=None)
@click.option("--align", type=click.Choice(["left", "center", "right"]), default=None)
@click.option("--color", default=None,
              help='텍스트 색. "r,g,b" 또는 "[r,g,b]" (0~1 또는 0~255)')
@click.option("--letter-spacing", type=float, default=None)
@click.option("--line-spacing", type=float, default=None)
@click.option("--border", default=None,
              help='테두리 JSON: \'{"alpha": 1.0, "color": [0,0,0], "width": 0.08}\'')
@click.option("--shadow", default=None,
              help='그림자 JSON: \'{"alpha": 0.9, "color": [0,0,0], "distance": 5, "angle": 315}\'')
@click.option("--clip-settings", default=None, help="프리셋 또는 JSON")
@click.option("--position-x", type=float, default=None, help="X 좌표 (-1~1)")
@click.option("--position-y", type=float, default=None, help="Y 좌표 (-1=하단, +1=상단)")
@click.option("--patch-style", is_flag=True, default=None,
              help="font/border/shadow를 save 후 draft_content.json에 직접 패치")
@click.option("--style", "style_name", default=None,
              help="저장된 스타일 프리셋 이름 (명시 옵션이 프리셋을 덮어씀)")
@click.pass_context
def text_add(ctx, project_path, text, start, duration, track, font, size, bold, italic,
             underline, align, color, letter_spacing, line_spacing, border, shadow,
             clip_settings, position_x, position_y, patch_style, style_name):
    session = load_session(project_path)

    border_dict = parse_json_option(border, "border")
    shadow_dict = parse_json_option(shadow, "shadow")
    color_arr = parse_color(color)
    clip_dict = resolve_clip_settings(clip_settings)

    # --style 지정 시 스타일 불러와 overrides 머지 (명시 옵션이 우선)
    overrides = {
        "font": font,
        "size": size,
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "align": align,
        "color": color_arr,
        "letter_spacing": letter_spacing,
        "line_spacing": line_spacing,
        "border": border_dict,
        "shadow": shadow_dict,
        "clip_settings": clip_dict,
    }
    if style_name:
        try:
            merged = style_registry.merge_style_with_overrides(style_name, overrides)
        except KeyError:
            raise click.ClickException(f"스타일 '{style_name}' 없음")
    else:
        merged = overrides

    font = merged.get("font")
    size = merged.get("size")
    bold = merged.get("bold")
    italic = merged.get("italic")
    underline = merged.get("underline")
    align = merged.get("align")
    color_arr = merged.get("color")
    letter_spacing = merged.get("letter_spacing")
    line_spacing = merged.get("line_spacing")
    border_dict = merged.get("border")
    shadow_dict = merged.get("shadow")
    clip_dict = merged.get("clip_settings")

    # position-x/y 가 따로 들어왔으면 clip_settings에 머지
    if position_x is not None or position_y is not None:
        clip_dict = dict(clip_dict) if clip_dict else {}
        if position_x is not None:
            clip_dict["transform_x"] = position_x
        if position_y is not None:
            clip_dict["transform_y"] = position_y

    args = {
        "text": text,
        "start": resolve_start_time(session.data, start, track_name=track),
        "duration": duration,
        "track": track,
        "font": font,
        "size": size,
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "align": align,
        "color": color_arr,
        "letter_spacing": letter_spacing,
        "line_spacing": line_spacing,
        "border": border_dict,
        "shadow": shadow_dict,
        "clip_settings": clip_dict,
    }
    result = session.append_operation("add_text", args)
    text_op_id = result.get("id")

    # patch-style 모드: 동일 세그먼트에 대해 postprocess op도 추가
    if patch_style:
        with session.batch():
            patch_args = {
                "track": track,
                "segment_ref": text_op_id,
                "color": color_arr,
                "border": border_dict,
                "shadow": shadow_dict,
            }
            session.append_operation("text_style_patch", patch_args, _status="queued")
            if position_x is not None or position_y is not None:
                tr_args = {"track": track, "segment_ref": text_op_id}
                if position_x is not None:
                    tr_args["x"] = position_x
                if position_y is not None:
                    tr_args["y"] = position_y
                session.append_operation("text_transform_patch", tr_args, _status="queued")
        result["postprocess_queued"] = True

    output_result(result, ctx.obj["json"])


@text_group.command("add-animation", help="텍스트 세그먼트에 애니메이션 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--role", type=click.Choice(["intro", "outro", "loop"]), default="intro")
@click.option("--name", required=True)
@click.option("--duration", default="500ms", show_default=True)
@click.pass_context
def text_add_animation(ctx, project_path, track, segment_ref, role, name, duration):
    session = load_session(project_path)
    result = session.append_operation(
        "add_text_animation",
        {"track": track, "segment_ref": segment_ref, "role": role,
         "name": name, "duration": duration},
    )
    output_result(result, ctx.obj["json"])


@text_group.command("style-patch",
                    help="기존 텍스트 세그먼트의 스타일/위치를 save 후 패치 (버그 #17~#21 회피)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--font-path", default=None, help="폰트 절대 경로 (TTF/OTF)")
@click.option("--font-resource-id", default=None, help="CapCut 폰트 resource_id")
@click.option("--color", default=None)
@click.option("--border", default=None)
@click.option("--shadow", default=None)
@click.option("--position-x", type=float, default=None)
@click.option("--position-y", type=float, default=None)
@click.pass_context
def text_style_patch(ctx, project_path, track, segment_ref, font_path, font_resource_id,
                     color, border, shadow, position_x, position_y):
    session = load_session(project_path)
    border_dict = parse_json_option(border, "border")
    shadow_dict = parse_json_option(shadow, "shadow")
    color_arr = parse_color(color)

    queued: list[dict] = []
    with session.batch():
        # 스타일 패치
        if any(x is not None for x in (font_path, font_resource_id, color_arr, border_dict, shadow_dict)):
            queued.append(session.append_operation(
                "text_style_patch",
                {
                    "track": track,
                    "segment_ref": segment_ref,
                    "font_path": font_path,
                    "font_resource_id": font_resource_id,
                    "color": color_arr,
                    "border": border_dict,
                    "shadow": shadow_dict,
                },
                _status="queued",
            ))
        # 위치 패치
        if position_x is not None or position_y is not None:
            tr_args = {"track": track, "segment_ref": segment_ref}
            if position_x is not None:
                tr_args["x"] = position_x
            if position_y is not None:
                tr_args["y"] = position_y
            queued.append(session.append_operation(
                "text_transform_patch", tr_args, _status="queued"
            ))
    output_result({"status": "queued", "ops": queued}, ctx.obj["json"])


# =========================================================================
# SRT 자막 import
# =========================================================================


_SRT_TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_SRT_ARROW_RE = re.compile(r"\s*-{1,3}>\s*")


def _srt_ts_to_us(ts: str) -> int | None:
    """``HH:MM:SS,mmm`` 또는 ``HH:MM:SS.mmm`` → 마이크로초. 실패 시 None."""
    m = _SRT_TS_RE.search(ts)
    if not m:
        return None
    h, mnt, s, ms = (int(x) for x in m.groups())
    return ((h * 3600 + mnt * 60 + s) * 1000 + ms) * 1000


def _parse_srt(content: str) -> list[dict]:
    """SRT 파서 — BOM/CRLF/\\r/점-콤마 타임코드/번호 누락/빈 블록 모두 허용.

    반환: ``[{index, start_us, end_us, text}, ...]``.
    잘못된 타임코드나 번호는 건너뜀. 파서 자체는 예외를 던지지 않음.
    """
    # 줄바꿈 정규화 (오래된 Mac CR 포함)
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        return []

    blocks = re.split(r"\n\s*\n+", content)
    out: list[dict] = []
    for blk in blocks:
        lines = [l for l in blk.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue

        # 첫 줄이 순번이면 떼고, 아니면 타임코드 줄일 수 있음
        ts_line = lines[1] if _SRT_ARROW_RE.search(lines[0]) is None else lines[0]
        text_start_idx = 2 if ts_line is lines[1] else 1
        if _SRT_ARROW_RE.search(ts_line) is None:
            continue

        parts = _SRT_ARROW_RE.split(ts_line, maxsplit=1)
        if len(parts) != 2:
            continue
        start_us = _srt_ts_to_us(parts[0])
        end_us = _srt_ts_to_us(parts[1])
        if start_us is None or end_us is None or end_us <= start_us:
            continue

        text = "\n".join(lines[text_start_idx:]).strip()
        if not text:
            continue
        out.append({"index": lines[0].strip() if text_start_idx == 2 else "",
                    "start_us": start_us, "end_us": end_us, "text": text})
    return out


@click.group("srt", help="SRT 자막 import")
def srt_group():
    pass


@srt_group.command("import", help="SRT 파일을 텍스트 세그먼트들로 import")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--track", required=True, help="텍스트 트랙 이름 (없으면 자동 생성)")
@click.option("--font", default=None)
@click.option("--style", "style_name", default=None,
              help="저장된 스타일 프리셋 이름 (--style-json/--font 보다 우선 순위가 낮음)")
@click.option("--style-json", default=None,
              help='추가 스타일 JSON 예: \'{"size": 6.0}\'')
@click.option("--clip-settings", default="subtitle-bottom",
              help="프리셋 또는 JSON. 기본 subtitle-bottom", show_default=True)
@click.pass_context
def srt_import(ctx, project_path, file, track, font, style_name, style_json, clip_settings):
    session = load_session(project_path)
    style_json_dict = parse_json_option(style_json, "style-json") or {}
    clip_dict = resolve_clip_settings(clip_settings)

    # --style 프리셋을 베이스로, --style-json/--font/--clip-settings 이 덮어쓴다
    base: dict = {}
    if style_name:
        try:
            base = style_registry.get_style(style_name)
        except KeyError:
            raise click.ClickException(f"스타일 '{style_name}' 없음")
        base = {k: v for k, v in base.items() if not k.startswith("_")}

    # 명시 옵션 오버라이드
    if font is not None:
        base["font"] = font
    if clip_dict is not None:
        base["clip_settings"] = clip_dict
    # style-json 은 가장 마지막에 머지 (키 단위 교체)
    for k, v in style_json_dict.items():
        if v is not None:
            base[k] = v

    merged_font = base.get("font")
    merged_clip = base.get("clip_settings")
    # text 내용/시간만 빼고 스타일 필드 모음
    style_extra = {k: v for k, v in base.items()
                   if k not in {"font", "clip_settings"}}

    content = Path(file).read_text(encoding="utf-8-sig")
    entries = _parse_srt(content)

    added: list[dict] = []
    with session.batch():
        for e in entries:
            duration_us = e["end_us"] - e["start_us"]
            args = {
                "text": e["text"],
                "start": f"{e['start_us']}us",
                "duration": f"{duration_us}us",
                "track": track,
                "font": merged_font,
                "clip_settings": dict(merged_clip) if merged_clip else None,
                **style_extra,
            }
            added.append(session.append_operation("add_text", args))
    output_result({"status": "imported", "count": len(added), "first_id": added[0]["id"] if added else None},
                  ctx.obj["json"])


# =========================================================================
# auto-srt — whisper CLI 연동 자동 자막 생성
# =========================================================================


@text_group.command("auto-srt", help="오디오/영상에서 whisper로 SRT 자동 생성 후 세션에 import")
@click.option("-p", "--project", "project_path", required=True,
              help="세션 JSON 경로")
@click.option("--audio", required=True,
              help="입력 파일 경로 (mp3/wav/mp4/mov 등)")
@click.option("--model", default="small", show_default=True,
              type=click.Choice(["tiny", "base", "small", "medium", "large"]),
              help="whisper 모델 크기")
@click.option("--language", default="ko", show_default=True,
              help="언어 코드 (ko, en, ja 등). 'auto'는 whisper 자동감지")
@click.option("--style", "style_name", default="youtube-subtitle", show_default=True,
              help="스타일 프리셋 이름")
@click.option("--track", default="T1", show_default=True,
              help="텍스트 트랙 이름")
@click.option("--word-level/--segment-level", "word_level", default=True, show_default=True,
              help="단어 단위 타임스탬프 (word-level) vs 세그먼트 단위 (segment-level)")
@click.option("--initial-prompt", default=None,
              help="한국어 도메인 힌트 (예: 'Product Pro Max 256GB')")
@click.option("--output-dir", default=None,
              help="SRT 파일 저장 경로 (기본: 임시 디렉토리)")
@click.option("--keep-srt/--no-keep-srt", default=False, show_default=True,
              help="SRT 파일 보존 여부 (기본: 임시 디렉토리 자동 정리)")
@click.option("--clip-settings", default="subtitle-bottom", show_default=True,
              help="srt import에 전달할 클립 설정 프리셋 또는 JSON")
@click.option("--font", default=None,
              help="폰트 이름 (srt import에 전달)")
@click.pass_context
def text_auto_srt(ctx, project_path, audio, model, language, style_name, track,
                  word_level, initial_prompt, output_dir, keep_srt, clip_settings, font):
    """whisper CLI를 subprocess로 호출해 SRT 생성 후 기존 srt import 로직으로 세션에 연결."""

    # 출력 디렉토리 결정 — 사용자 지정이면 그대로, 아니면 임시 디렉토리 생성
    user_specified_dir = output_dir is not None
    if user_specified_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir_to_cleanup = None  # 사용자 디렉토리는 정리하지 않음
    else:
        tmp_dir = tempfile.mkdtemp(prefix="capcut-autosrt-")
        out_dir = Path(tmp_dir)
        tmp_dir_to_cleanup = tmp_dir  # --no-keep-srt 시 정리 대상

    # whisper CLI 명령 구성
    audio_path = str(audio)
    cmd = [
        "whisper", audio_path,
        "--model", model,
        "--output_format", "srt",
        "--output_dir", str(out_dir),
    ]
    if language != "auto":
        cmd.extend(["--language", language])
    if word_level:
        cmd.extend([
            "--word_timestamps", "True",
            "--max_line_width", "24",
            "--max_words_per_line", "6",
        ])
    if initial_prompt:
        cmd.extend(["--initial_prompt", initial_prompt])

    # whisper 실행
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
        )
    except FileNotFoundError:
        raise click.ClickException(
            "whisper 명령을 찾을 수 없습니다.\n"
            "설치 방법: pip install openai-whisper\n"
            "설치 후 'whisper --help'로 확인하세요."
        )

    if result.returncode != 0:
        raise click.ClickException(
            f"whisper 실패 (returncode={result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    # SRT 파일 탐색 — whisper는 <output_dir>/<audio_stem>.srt 형태로 저장
    audio_stem = Path(audio_path).stem
    srt_path = out_dir / f"{audio_stem}.srt"
    if not srt_path.exists():
        # whisper가 만든 .srt 파일 목록에서 탐색 (파일명이 달라질 수 있음)
        srt_candidates = list(out_dir.glob("*.srt"))
        if not srt_candidates:
            raise click.ClickException(
                f"whisper가 SRT 파일을 생성하지 않았습니다. "
                f"출력 디렉토리: {out_dir}"
            )
        srt_path = srt_candidates[0]

    # 세그먼트 수 미리 파악 (보고용)
    srt_content = srt_path.read_text(encoding="utf-8-sig")
    segments = _parse_srt(srt_content)

    # 기존 srt_import 재호출 (ctx.invoke 패턴)
    ctx.invoke(
        srt_import,
        project_path=project_path,
        file=str(srt_path),
        track=track,
        font=font,
        style_name=style_name,
        style_json=None,
        clip_settings=clip_settings,
    )

    # --no-keep-srt + 임시 디렉토리인 경우에만 정리
    if not keep_srt and tmp_dir_to_cleanup:
        shutil.rmtree(tmp_dir_to_cleanup, ignore_errors=True)
        srt_path_display = "(임시 디렉토리 정리됨)"
    else:
        srt_path_display = str(srt_path)

    output_result(
        {
            "status": "auto_srt_applied",
            "audio": audio_path,
            "srt_path": srt_path_display,
            "srt_segments": len(segments),
            "model": model,
            "language": language,
            "word_level": word_level,
        },
        ctx.obj["json"],
    )
