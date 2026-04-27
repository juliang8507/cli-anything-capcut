"""render-headless 커맨드 — ffmpeg로 직접 렌더(크로스플랫폼).

기존 ``render`` (GUI 자동화)와 달리, CapCut/JianYing을 전혀 실행하지 않고
세션의 op log를 해석해서 ``ffmpeg`` 명령을 조립해 MP4를 만든다.

**지원 범위**
    - V1 트랙의 ``add_video`` / ``add_image`` concat
    - V2+ 트랙의 ``add_video`` / ``add_image`` 오버레이 (PIP)
      · ``clip_settings`` 의 ``scale_x``, ``scale_y``, ``transform_x``, ``transform_y``
        (CapCut 좌표계를 ffmpeg 픽셀 좌표로 변환)
    - A1/A2 트랙의 ``add_audio`` 믹싱
    - T1 트랙의 ``add_text`` → SRT 생성 + subtitles 필터 burn-in
    - ``add_video_fade`` / ``add_audio_fade``
    - ``add_video_transition`` (xfade 필터 기반 실제 크로스페이드)
      · dissolve / fade / slideleft / slideright / slideup / slidedown
        / wipeleft / wiperight / circleopen
    - ``add_keyframe`` 근사 (단일 세그먼트, 2개 keyframe 선형 보간)
      · uniform_scale → Ken Burns 줌
      · alpha          → fade 필터
      · transform_x/y → overlay 좌표 식 (V2+ 오버레이 전용)

**미지원 (경고 또는 에러)**
    - add_video_animation / add_video_filter / add_video_effect
    - add_mask / add_background / add_sticker
    - 3개 이상의 keyframe (처음·마지막만 사용, 경고)
    - 비지원 keyframe property (rotation, scale_x 개별 등)

복잡한 편집은 ``save`` → CapCut으로 여는 정상 워크플로를 권장.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.session import Session, SessionError
from cli_anything.capcut.core.time_utils import format_duration, parse_time_value


# =========================================================================
# 지원 / 미지원 op 분류
# =========================================================================

# replay 재생되지만 render-headless가 "의미 있게" 렌더할 수 있는 op.
SUPPORTED_OPS: set[str] = {
    "add_track",
    "add_video",
    "add_image",
    "add_audio",
    "add_text",
    "add_video_fade",
    "add_audio_fade",
    "add_video_transition",
    "add_keyframe",  # v0.4.1: 일부 property만 근사 지원
}

# 명백히 미지원 — 렌더에 반영 불가능.
UNSUPPORTED_OPS: set[str] = {
    "add_video_animation",
    "add_text_animation",
    "add_filter",
    "add_effect",
    "add_mask",
    "add_background",
    "add_sticker",
    "add_audio_effect",
}

# replay-only, 렌더에 무관 (postprocess 목적). 조용히 무시.
IGNORED_OPS: set[str] = {
    "text_style_patch",
    "text_transform_patch",
    "color_adjust",
    "color_wheels",
}


# =========================================================================
# transition 이름 매핑 (CapCut → ffmpeg xfade)
# =========================================================================

# 공식 지원하는 CapCut transition 이름 → ffmpeg xfade transition= 값
TRANSITION_NAME_MAP: dict[str, str] = {
    "dissolve": "dissolve",
    "fade": "fade",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "circle": "circleopen",
}

# legacy: 기존 코드가 참조하는 이름 (하위 호환)
SUPPORTED_TRANSITION_NAMES: set[str] = set(TRANSITION_NAME_MAP.keys())


# 근사 지원하는 keyframe property
KEYFRAME_SUPPORTED_PROPS: set[str] = {
    "uniform_scale",
    "alpha",
    "transform_x",
    "transform_y",
}


def _map_transition_name(name: str | None) -> tuple[str, str | None]:
    """CapCut transition 이름 → ffmpeg xfade 이름.

    반환: (ffmpeg_name, warning_msg_or_None)
    매핑 실패 시 'fade'로 폴백 + 경고 메시지.
    """
    raw = (name or "").lower().strip()
    if raw in TRANSITION_NAME_MAP:
        return TRANSITION_NAME_MAP[raw], None
    warn = (
        f"transition '{raw}'는 지원 매핑이 없어 'fade'로 폴백됩니다. "
        f"지원 이름: {sorted(TRANSITION_NAME_MAP.keys())}"
    )
    return "fade", warn


# =========================================================================
# 좌표/크기 변환 헬퍼
# =========================================================================


def _capcut_to_ffmpeg_xy(
    transform_x: float,
    transform_y: float,
    main_w: int,
    main_h: int,
    overlay_w: int | float,
    overlay_h: int | float,
) -> tuple[float, float]:
    """CapCut 좌표계(-1~+1, 중앙=0, Y 위=+)를 ffmpeg 오버레이 픽셀 좌표로.

    ffmpeg overlay x,y는 오버레이의 **좌상단** 기준 픽셀.

    공식::

        x_px = (transform_x * 0.5 + 0.5) * main_w - overlay_w * 0.5
        y_px = (1.0 - (transform_y * 0.5 + 0.5)) * main_h - overlay_h * 0.5
    """
    tx = float(transform_x)
    ty = float(transform_y)
    x_px = (tx * 0.5 + 0.5) * main_w - float(overlay_w) * 0.5
    y_px = (1.0 - (ty * 0.5 + 0.5)) * main_h - float(overlay_h) * 0.5
    return x_px, y_px


# =========================================================================
# 분석 헬퍼
# =========================================================================


def _seg_info_from_op(op: dict) -> dict:
    """op dict → {start_us, duration_us, track, file, text, segment_ref, extra}."""
    args = op.get("args", {}) or {}
    start_us = parse_time_value(args.get("start", 0))
    dur_raw = args.get("duration")
    dur_us = parse_time_value(dur_raw) if dur_raw else 0
    return {
        "id": op.get("id"),
        "op": op.get("op"),
        "start_us": start_us,
        "duration_us": dur_us,
        "track": args.get("track"),
        "file": args.get("file"),
        "text": args.get("text"),
        "segment_ref": args.get("segment_ref"),
        "args": args,
    }


def analyze_session_for_render(session: Session) -> dict:
    """세션을 조사해서 렌더 가능성 판정.

    반환::

        {
            "supported_segments": [segment info dicts],
            "unsupported_ops":     [{"index","op","reason"}],
            "warnings":            [str],
            "total_duration_us":   int,
            "missing_files":       [str],
            "video_tracks":        [name],  # 모든 V* 트랙 (V1 main + V2+ overlay)
            "overlay_video_tracks": [name],  # V1 제외한 overlay 트랙
            "audio_tracks":        [name],
            "text_tracks":         [name],
            "primary_video_track": "V1" 또는 유사,
            "keyframes_by_segment": {seg_id: [{property,time_us,value}, ...]},
        }
    """
    ops = session.data.get("operations", [])
    supported: list[dict] = []
    unsupported: list[dict] = []
    warnings: list[str] = []
    missing_files: list[str] = []
    video_tracks: set[str] = set()
    audio_tracks: set[str] = set()
    text_tracks: set[str] = set()
    keyframes_by_segment: dict[str, list[dict]] = {}

    # 트랙 타입 알기 위해 add_track op를 먼저 훑음
    track_types: dict[str, str] = {}
    # 트랙 선언 순서 (V1=0, V2=1, …) — primary track 결정 안정화용
    track_decl_order: dict[str, int] = {}
    for op in ops:
        if op.get("op") == "add_track":
            a = op.get("args", {})
            if a.get("name"):
                track_types[a["name"]] = a.get("type", "video")
                track_decl_order.setdefault(a["name"], len(track_decl_order))

    total_end = 0
    for i, op in enumerate(ops):
        name = op.get("op")
        if name in IGNORED_OPS:
            continue

        # add_keyframe은 property가 지원 범위면 supported로, 아니면 unsupported
        if name == "add_keyframe":
            prop = (op.get("args", {}) or {}).get("property")
            seg_ref = (op.get("args", {}) or {}).get("segment_ref")
            if prop not in KEYFRAME_SUPPORTED_PROPS:
                unsupported.append({
                    "index": i, "op": name, "id": op.get("id"),
                    "reason": f"keyframe property '{prop}'는 headless 렌더 미지원. "
                              f"지원: {sorted(KEYFRAME_SUPPORTED_PROPS)}",
                })
                continue
            info = _seg_info_from_op(op)
            # 누적
            args = info["args"]
            kf_entry = {
                "property": prop,
                "time_us": parse_time_value(args.get("time", 0)),
                "value": float(args.get("value", 0.0)),
                "index": i,
            }
            if seg_ref:
                keyframes_by_segment.setdefault(seg_ref, []).append(kf_entry)
            supported.append(info)
            continue

        if name in UNSUPPORTED_OPS:
            unsupported.append(
                {"index": i, "op": name, "id": op.get("id"),
                 "reason": f"{name}는 headless 렌더가 지원하지 않음"}
            )
            continue
        if name not in SUPPORTED_OPS:
            unsupported.append(
                {"index": i, "op": name, "id": op.get("id"),
                 "reason": f"알 수 없는 op: {name}"}
            )
            continue

        info = _seg_info_from_op(op)

        # 미디어 파일 존재 확인
        if name in ("add_video", "add_image", "add_audio"):
            f = info["file"]
            if f and not Path(f).exists():
                missing_files.append(f)

        # transition 이름 확인 (매핑 실패 시 경고)
        if name == "add_video_transition":
            tname = (op.get("args", {}).get("name") or "").lower()
            _, warn = _map_transition_name(tname)
            if warn:
                warnings.append(f"op #{i} ({info['id']}): {warn}")

        # 트랙 분류
        track = info["track"]
        if track:
            t_type = track_types.get(track)
            if t_type == "video" or (t_type is None and track.upper().startswith("V")):
                video_tracks.add(track)
            elif t_type == "audio" or (t_type is None and track.upper().startswith("A")):
                audio_tracks.add(track)
            elif t_type == "text" or (t_type is None and track.upper().startswith("T")):
                text_tracks.add(track)

        # clip_settings 복잡도 안내 (이제 일부 지원)
        cs = info["args"].get("clip_settings") or info["args"].get("clip")
        if isinstance(cs, dict):
            ignored_keys = {"rotation", "flip_horizontal", "flip_vertical"} & set(cs.keys())
            if ignored_keys:
                warnings.append(
                    f"op #{i} ({info['id']}): clip_settings의 {sorted(ignored_keys)}는 "
                    f"headless 렌더에서 무시됩니다."
                )
            applied_keys = {"scale_x", "scale_y", "transform_x", "transform_y", "alpha"} & set(cs.keys())
            if applied_keys:
                warnings.append(
                    f"op #{i} ({info['id']}): clip_settings의 {sorted(applied_keys)}를 "
                    f"적용합니다 (scale / overlay 좌표)."
                )

        supported.append(info)
        total_end = max(total_end, info["start_us"] + info["duration_us"])

    # primary video track 결정: declaration 순서대로 첫 번째
    sorted_v = sorted(
        video_tracks,
        key=lambda t: (track_decl_order.get(t, 1 << 30), t),
    )
    v_primary = sorted_v[0] if sorted_v else None
    overlay_v_tracks = sorted_v[1:] if len(sorted_v) > 1 else []

    # V2+ 트랙 존재 시 overlay로 처리된다는 정보성 경고 (하위 호환 테스트용)
    for ov in overlay_v_tracks:
        warnings.append(
            f"비디오 트랙 '{ov}'는 V1 위 오버레이(PIP)로 합성됩니다. "
            f"기준 트랙: '{v_primary}'."
        )

    # keyframe 3개 이상 경고 (선형 보간은 2개만)
    for seg_id, kfs in keyframes_by_segment.items():
        # property별로 그룹
        by_prop: dict[str, list[dict]] = {}
        for kf in kfs:
            by_prop.setdefault(kf["property"], []).append(kf)
        for prop, lst in by_prop.items():
            if len(lst) > 2:
                warnings.append(
                    f"세그먼트 '{seg_id}'의 {prop} keyframe이 {len(lst)}개 입니다 — "
                    f"headless 렌더는 처음·마지막 2개만 선형 보간합니다."
                )

    return {
        "supported_segments": supported,
        "unsupported_ops": unsupported,
        "warnings": warnings,
        "total_duration_us": total_end,
        "total_duration_human": format_duration(total_end) if total_end else "0s",
        "missing_files": sorted(set(missing_files)),
        "video_tracks": sorted_v,
        "overlay_video_tracks": overlay_v_tracks,
        "audio_tracks": sorted(audio_tracks),
        "text_tracks": sorted(text_tracks),
        "primary_video_track": v_primary,
        "keyframes_by_segment": keyframes_by_segment,
    }


# =========================================================================
# SRT 생성
# =========================================================================


def _us_to_srt_ts(us: int) -> str:
    ms_total = us // 1000
    h = ms_total // 3_600_000
    m = (ms_total // 60_000) % 60
    s = (ms_total // 1000) % 60
    ms = ms_total % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt_for_text_segments(text_segs: list[dict], path: Path) -> int:
    """T1 트랙의 add_text 세그먼트들을 SRT로 덤프. 반환=쿠 수."""
    ordered = sorted(text_segs, key=lambda s: s["start_us"])
    lines: list[str] = []
    for i, s in enumerate(ordered, 1):
        start = _us_to_srt_ts(s["start_us"])
        end = _us_to_srt_ts(s["start_us"] + max(s["duration_us"], 1))
        txt = s["text"] or ""
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(txt)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(ordered)


# =========================================================================
# keyframe 표현식 헬퍼
# =========================================================================


def _pick_first_last_kf(kfs: list[dict]) -> tuple[dict | None, dict | None]:
    """keyframe 리스트에서 time_us 오름차순 정렬 후 첫/끝만."""
    if not kfs:
        return None, None
    ordered = sorted(kfs, key=lambda k: k["time_us"])
    if len(ordered) == 1:
        return ordered[0], None
    return ordered[0], ordered[-1]


def _build_keyframe_scale_expr(
    seg_dur_us: int,
    kfs: list[dict],
    base_w: int,
    base_h: int,
) -> tuple[str, float, float]:
    """uniform_scale keyframe → ffmpeg scale 필터 문자열.

    반환: (scale_filter_str, start_scale, end_scale)
    keyframe이 없거나 1개면 정적 scale.
    2개+면 Ken Burns 식 ``scale=base_w*(s0+(s1-s0)*t/T):base_h*(...)``.
    """
    first, last = _pick_first_last_kf(kfs)
    if first is None:
        return f"scale={base_w}:{base_h}", 1.0, 1.0
    s0 = float(first["value"])
    if last is None:
        # 단일 keyframe → 정적 scale
        w = max(1, int(round(base_w * s0)))
        h = max(1, int(round(base_h * s0)))
        return f"scale={w}:{h}", s0, s0
    s1 = float(last["value"])
    dur_s = max(seg_dur_us / 1_000_000, 1e-6)
    # ffmpeg scale 은 표현식 입력 지원. PTS/AV_TIME_BASE 또는 t 사용.
    # width/height expr 안에서 ``t`` = 프레임 시간(초).
    # (s0+(s1-s0)*min(t/T,1)) 로 clamp
    expr = (
        f"scale="
        f"w='{base_w}*({s0}+({s1}-{s0})*min(t/{dur_s:.6f}\\,1))':"
        f"h='{base_h}*({s0}+({s1}-{s0})*min(t/{dur_s:.6f}\\,1))':"
        f"eval=frame"
    )
    return expr, s0, s1


def _build_keyframe_alpha_expr(seg_dur_us: int, kfs: list[dict]) -> str | None:
    """alpha keyframe → fade 필터 조합 문자열.

    2개 keyframe (0→1) = 페이드인, (1→0) = 페이드아웃.
    """
    first, last = _pick_first_last_kf(kfs)
    if first is None:
        return None
    a0 = float(first["value"])
    if last is None:
        # 단일 → 정적 alpha (format+colorchannelmixer 사용)
        return f"format=yuva420p,colorchannelmixer=aa={a0:.4f}"
    a1 = float(last["value"])
    t0_s = max(first["time_us"] / 1_000_000, 0.0)
    t1_s = max(last["time_us"] / 1_000_000, t0_s + 1e-3)
    dur_s = max((t1_s - t0_s), 1e-3)
    # 0→1 페이드인
    if a1 > a0 and a0 <= 0.01:
        return f"fade=t=in:st={t0_s:.3f}:d={dur_s:.3f}:alpha=1"
    # 1→0 페이드아웃
    if a0 > a1 and a1 <= 0.01:
        return f"fade=t=out:st={t0_s:.3f}:d={dur_s:.3f}:alpha=1"
    # 일반 선형 보간 (근사)
    # aa = a0 + (a1-a0) * clamp((t-t0)/dur, 0, 1)
    expr = (
        f"format=yuva420p,"
        f"colorchannelmixer=aa='"
        f"{a0:.4f}+({a1:.4f}-{a0:.4f})*min(max((t-{t0_s:.3f})/{dur_s:.3f}\\,0)\\,1)'"
    )
    return expr


# =========================================================================
# ffmpeg 명령 빌드 보조
# =========================================================================


def _ffmpeg_escape_path(p: str) -> str:
    """subtitles 필터용 경로 이스케이프.

    Windows의 드라이브 콜론(C:) 때문에 ffmpeg filter_complex에서 깨짐.
    해결: ``\\``, ``:``, ``'``를 모두 이스케이프.
    """
    p = p.replace("\\", "/")
    p = p.replace(":", r"\:").replace("'", r"\'")
    return p


def _build_fade_filters(seg_opts: dict, duration_us: int) -> str:
    """fade_in/fade_out 초 단위 → ffmpeg fade 필터 문자열."""
    parts: list[str] = []
    fi = seg_opts.get("fade_in_us", 0)
    fo = seg_opts.get("fade_out_us", 0)
    if fi > 0:
        parts.append(f"fade=t=in:st=0:d={fi/1_000_000:.3f}")
    if fo > 0:
        start = max(0, (duration_us - fo) / 1_000_000)
        parts.append(f"fade=t=out:st={start:.3f}:d={fo/1_000_000:.3f}")
    return ",".join(parts)


def _build_afade_filters(seg_opts: dict, duration_us: int) -> str:
    parts: list[str] = []
    fi = seg_opts.get("fade_in_us", 0)
    fo = seg_opts.get("fade_out_us", 0)
    if fi > 0:
        parts.append(f"afade=t=in:st=0:d={fi/1_000_000:.3f}")
    if fo > 0:
        start = max(0, (duration_us - fo) / 1_000_000)
        parts.append(f"afade=t=out:st={start:.3f}:d={fo/1_000_000:.3f}")
    return ",".join(parts)


def _collect_segment_extras(analysis: dict) -> dict:
    """segment_ref로 연결된 fade/transition 정보를 세그먼트별로 모음."""
    extras: dict[str, dict] = {}
    for seg in analysis["supported_segments"]:
        extras.setdefault(seg["id"], {
            "fade_in_us": 0,
            "fade_out_us": 0,
            "transition_into_next": None,  # ffmpeg xfade name
            "transition_duration_us": 0,
        })
    for seg in analysis["supported_segments"]:
        op_name = seg["op"]
        args = seg["args"]
        ref = seg["segment_ref"]
        if op_name in ("add_video_fade", "add_audio_fade"):
            target = extras.get(ref)
            if target is not None:
                target["fade_in_us"] = parse_time_value(args.get("fade_in", 0))
                target["fade_out_us"] = parse_time_value(args.get("fade_out", 0))
        elif op_name == "add_video_transition":
            target = extras.get(ref)
            if target is not None:
                tname = (args.get("name") or "").lower()
                ffmpeg_name, _warn = _map_transition_name(tname)
                target["transition_into_next"] = ffmpeg_name
                target["transition_duration_us"] = parse_time_value(
                    args.get("duration", "500ms")
                )
    return extras


def build_ffmpeg_command(
    session: Session,
    output: str,
    *,
    crf: int = 20,
    preset: str = "medium",
    srt_path: Path | None = None,
    workdir: Path | None = None,
) -> tuple[list[str], dict]:
    """ffmpeg 명령 리스트와 부수 정보(warnings, srt 등)를 함께 반환."""
    analysis = analyze_session_for_render(session)

    # 미디어 세그먼트 분류
    v_track = analysis["primary_video_track"]
    overlay_tracks: list[str] = analysis["overlay_video_tracks"]
    video_segs = [
        s for s in analysis["supported_segments"]
        if s["op"] in ("add_video", "add_image") and s["track"] == v_track
    ]
    overlay_segs_by_track: dict[str, list[dict]] = {}
    for ov in overlay_tracks:
        overlay_segs_by_track[ov] = sorted(
            [
                s for s in analysis["supported_segments"]
                if s["op"] in ("add_video", "add_image") and s["track"] == ov
            ],
            key=lambda s: s["start_us"],
        )
    audio_segs = [
        s for s in analysis["supported_segments"]
        if s["op"] == "add_audio" and s["track"] in analysis["audio_tracks"]
    ]
    text_segs = [
        s for s in analysis["supported_segments"]
        if s["op"] == "add_text" and s["track"] in analysis["text_tracks"]
    ]

    video_segs.sort(key=lambda s: s["start_us"])
    audio_segs.sort(key=lambda s: s["start_us"])

    extras = _collect_segment_extras(analysis)
    keyframes_by_segment = analysis["keyframes_by_segment"]

    width = session.width
    height = session.height
    fps = session.fps
    total_us = analysis["total_duration_us"]
    if total_us <= 0:
        raise click.ClickException("렌더할 세그먼트 없음 (총 길이 0).")

    cmd: list[str] = ["ffmpeg", "-y", "-hide_banner"]
    input_index = 0
    filter_parts: list[str] = []

    # -----------------------------------------------------------------
    # V1 메인 트랙 — concat 또는 xfade 체인
    # -----------------------------------------------------------------
    video_filter_chain: list[str] = []  # 각 세그먼트 prep 필터 (scale/fade/keyframe)
    seg_labels: list[str] = []          # [v0], [v1], ... 순차 라벨
    seg_effective: list[dict] = []      # 세그먼트 타이밍 계산용

    prev_end_us = 0
    # 트랜지션으로 인한 타임라인 shift 누적 (ms 단위로 xfade가 앞당긴 총량 us)
    xfade_shift_us = 0

    # 우선 각 세그먼트마다 입력을 등록 + prep 필터 체인 생성
    # (gap 포함: 각 세그먼트 전에 필요한 black lavfi 입력은 여기서 같이 추가)
    concat_video_labels: list[str] = []  # concat 사용 시에만 쓰는 라벨

    # -----------------------------------------------------------------
    # 트랜지션 유무 확인 (있으면 xfade 경로 사용)
    # -----------------------------------------------------------------
    has_any_transition = any(
        extras.get(s["id"], {}).get("transition_into_next") for s in video_segs[:-1]
    ) if len(video_segs) >= 2 else False

    if not has_any_transition:
        # ========================================================
        # 기존 경로: concat 필터
        # ========================================================
        for vi, seg in enumerate(video_segs):
            # 세그먼트 앞의 gap = black 프레임으로 패딩
            if seg["start_us"] > prev_end_us:
                gap_us = seg["start_us"] - prev_end_us
                cmd += [
                    "-f", "lavfi",
                    "-t", f"{gap_us/1_000_000:.3f}",
                    "-i", f"color=c=black:s={width}x{height}:r={fps}",
                ]
                concat_video_labels.append(f"[{input_index}:v]")
                input_index += 1

            # 실제 미디어 입력
            if seg["op"] == "add_image":
                dur_s = seg["duration_us"] / 1_000_000
                cmd += [
                    "-loop", "1",
                    "-t", f"{dur_s:.3f}",
                    "-i", seg["file"],
                ]
            else:
                cmd += ["-i", seg["file"]]
            in_idx = input_index
            input_index += 1

            dur_us = seg["duration_us"]
            seg_extras = extras.get(seg["id"], {})
            fade_str = _build_fade_filters(seg_extras, dur_us)

            # keyframe 적용 (V1은 alpha만 의미 있음; 스케일은 main canvas 기준)
            kfs = keyframes_by_segment.get(seg["id"], [])
            alpha_kfs = [k for k in kfs if k["property"] == "alpha"]
            scale_kfs = [k for k in kfs if k["property"] == "uniform_scale"]

            chain_ops = [
                f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
                "setsar=1",
                f"fps={fps}",
                f"trim=duration={dur_us/1_000_000:.3f}",
                "setpts=PTS-STARTPTS",
            ]
            # keyframe uniform_scale → Ken Burns 확대 적용
            if scale_kfs:
                # V1은 이미 pad로 맞춰졌으니 zoompan 대체 — 간단한 scale expr 뒤에 crop
                first, last = _pick_first_last_kf(scale_kfs)
                s0 = float(first["value"]) if first else 1.0
                s1 = float(last["value"]) if last else s0
                dur_s = max(dur_us / 1_000_000, 1e-6)
                chain_ops.append(
                    f"scale=w='iw*({s0}+({s1}-{s0})*min(t/{dur_s:.6f}\\,1))':"
                    f"h='ih*({s0}+({s1}-{s0})*min(t/{dur_s:.6f}\\,1))':eval=frame"
                )
                chain_ops.append(
                    f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2"
                )
            if fade_str:
                chain_ops.append(fade_str)
            # alpha keyframe (V1에서도 근사로 fade 적용)
            if alpha_kfs:
                ax = _build_keyframe_alpha_expr(dur_us, alpha_kfs)
                if ax:
                    chain_ops.append(ax)

            chain = f"[{in_idx}:v]" + ",".join(chain_ops)
            label = f"[v{vi}]"
            video_filter_chain.append(chain + label)
            concat_video_labels.append(label)

            prev_end_us = seg["start_us"] + dur_us

        # 비디오 끝에 남은 tail padding
        if total_us > prev_end_us and video_segs:
            tail_us = total_us - prev_end_us
            cmd += [
                "-f", "lavfi",
                "-t", f"{tail_us/1_000_000:.3f}",
                "-i", f"color=c=black:s={width}x{height}:r={fps}",
            ]
            concat_video_labels.append(f"[{input_index}:v]")
            input_index += 1

        # 비디오 세그먼트 하나도 없으면 전체 black
        if not video_segs:
            cmd += [
                "-f", "lavfi",
                "-t", f"{total_us/1_000_000:.3f}",
                "-i", f"color=c=black:s={width}x{height}:r={fps}",
            ]
            concat_video_labels.append(f"[{input_index}:v]")
            input_index += 1

    else:
        # ========================================================
        # xfade 경로: 트랜지션 있을 때
        # 각 세그먼트 prep 후 xfade로 체이닝.
        # 단순화를 위해 gap 패딩은 skip (연속 컷 가정).
        # offset 계산: accumulated timeline
        # ========================================================
        prep_labels: list[str] = []
        seg_durations_s: list[float] = []
        for vi, seg in enumerate(video_segs):
            if seg["op"] == "add_image":
                dur_s = seg["duration_us"] / 1_000_000
                cmd += [
                    "-loop", "1",
                    "-t", f"{dur_s:.3f}",
                    "-i", seg["file"],
                ]
            else:
                cmd += ["-i", seg["file"]]
            in_idx = input_index
            input_index += 1

            dur_us = seg["duration_us"]
            dur_s = dur_us / 1_000_000
            seg_durations_s.append(dur_s)

            seg_extras = extras.get(seg["id"], {})
            fade_str = _build_fade_filters(seg_extras, dur_us)
            kfs = keyframes_by_segment.get(seg["id"], [])
            alpha_kfs = [k for k in kfs if k["property"] == "alpha"]

            chain_ops = [
                f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
                "setsar=1",
                f"fps={fps}",
                f"trim=duration={dur_s:.3f}",
                "setpts=PTS-STARTPTS",
                "format=yuv420p",  # xfade가 같은 픽셀 포맷 요구
            ]
            if fade_str:
                chain_ops.append(fade_str)
            if alpha_kfs:
                ax = _build_keyframe_alpha_expr(dur_us, alpha_kfs)
                if ax:
                    chain_ops.append(ax)

            label = f"[xv{vi}]"
            video_filter_chain.append(
                f"[{in_idx}:v]" + ",".join(chain_ops) + label
            )
            prep_labels.append(label)

        # xfade 체인: 왼쪽→오른쪽 누적
        cur_label = prep_labels[0]
        cur_duration_s = seg_durations_s[0]
        for vi in range(1, len(video_segs)):
            seg_prev = video_segs[vi - 1]
            seg_prev_extras = extras.get(seg_prev["id"], {})
            tname = seg_prev_extras.get("transition_into_next") or "fade"
            tdur_us = seg_prev_extras.get("transition_duration_us") or 500_000
            tdur_s = max(tdur_us / 1_000_000, 0.1)
            # xfade offset = 이전 누적 길이 - 트랜지션 duration
            offset_s = max(cur_duration_s - tdur_s, 0.0)
            out_label = f"[xfout{vi}]"
            video_filter_chain.append(
                f"{cur_label}{prep_labels[vi]}"
                f"xfade=transition={tname}:duration={tdur_s:.3f}:offset={offset_s:.3f}"
                f"{out_label}"
            )
            cur_label = out_label
            # 새 누적 길이 = cur_duration + next_duration - transition
            cur_duration_s = cur_duration_s + seg_durations_s[vi] - tdur_s
            xfade_shift_us += tdur_us

        # xfade 완료 후 라벨 = cur_label
        concat_video_labels = [cur_label]

    # -----------------------------------------------------------------
    # filter_complex 조립: V1 메인 → (concat 또는 xfade 결과)
    # -----------------------------------------------------------------
    fc_parts: list[str] = []
    fc_parts.extend(video_filter_chain)

    if not has_any_transition:
        if len(concat_video_labels) == 1:
            vout_label = "[vconcat]"
            fc_parts.append(f"{concat_video_labels[0]}null{vout_label}")
        else:
            inputs_str = "".join(concat_video_labels)
            vout_label = "[vconcat]"
            fc_parts.append(
                f"{inputs_str}concat=n={len(concat_video_labels)}:v=1:a=0{vout_label}"
            )
    else:
        # xfade 결과 하나
        vout_label = "[vconcat]"
        fc_parts.append(f"{concat_video_labels[0]}null{vout_label}")

    # -----------------------------------------------------------------
    # V2+ 오버레이 처리
    # -----------------------------------------------------------------
    overlay_count = 0
    current_main_label = vout_label  # [vconcat]부터 시작
    for ov_track in overlay_tracks:
        for oi, seg in enumerate(overlay_segs_by_track[ov_track]):
            # 각 overlay 세그먼트를 별도 입력으로
            dur_us = seg["duration_us"]
            dur_s = dur_us / 1_000_000
            if seg["op"] == "add_image":
                cmd += [
                    "-loop", "1",
                    "-t", f"{dur_s:.3f}",
                    "-i", seg["file"],
                ]
            else:
                cmd += ["-i", seg["file"]]
            in_idx = input_index
            input_index += 1

            # clip_settings 해석
            cs = seg["args"].get("clip_settings") or seg["args"].get("clip") or {}
            sx = float(cs.get("scale_x", 1.0))
            sy = float(cs.get("scale_y", 1.0))
            tx = float(cs.get("transform_x", 0.0))
            ty = float(cs.get("transform_y", 0.0))

            # overlay 사이즈 (scale 적용)
            ov_w = max(1, int(round(width * sx)))
            ov_h = max(1, int(round(height * sy)))

            # keyframe (overlay용)
            kfs = keyframes_by_segment.get(seg["id"], [])
            scale_kfs = [k for k in kfs if k["property"] == "uniform_scale"]
            alpha_kfs = [k for k in kfs if k["property"] == "alpha"]
            tx_kfs = [k for k in kfs if k["property"] == "transform_x"]
            ty_kfs = [k for k in kfs if k["property"] == "transform_y"]

            # prep 체인
            prep_ops = [
                f"scale={ov_w}:{ov_h}:force_original_aspect_ratio=decrease",
                f"setsar=1",
                f"fps={fps}",
                f"trim=duration={dur_s:.3f}",
                "setpts=PTS-STARTPTS",
            ]
            # uniform_scale 키프레임 → 동적 scale
            if scale_kfs:
                first, last = _pick_first_last_kf(scale_kfs)
                k0 = float(first["value"]) if first else 1.0
                k1 = float(last["value"]) if last else k0
                base_w = ov_w
                base_h = ov_h
                # scale의 w/h 표현식에 eval=frame 붙여 프레임마다 재계산
                # prep 체인의 첫 scale을 교체
                prep_ops[0] = (
                    f"scale="
                    f"w='{base_w}*({k0}+({k1}-{k0})*min(t/{dur_s:.6f}\\,1))':"
                    f"h='{base_h}*({k0}+({k1}-{k0})*min(t/{dur_s:.6f}\\,1))':"
                    f"eval=frame"
                )
            # alpha → format+colorchannelmixer or fade
            if alpha_kfs:
                ax = _build_keyframe_alpha_expr(dur_us, alpha_kfs)
                if ax:
                    prep_ops.append(ax)
            else:
                # 오버레이는 기본 yuva420p (투명 지원) 없으면 RGBA alpha=1
                prep_ops.append("format=yuva420p")

            ov_prep_label = f"[ov{overlay_count}]"
            fc_parts.append(
                f"[{in_idx}:v]" + ",".join(prep_ops) + ov_prep_label
            )

            # overlay 좌표 (정적 또는 keyframe 보간)
            x_static, y_static = _capcut_to_ffmpeg_xy(
                tx, ty, width, height, ov_w, ov_h
            )
            if tx_kfs or ty_kfs:
                # keyframe 보간
                # 위쪽 공식에 동적 tx(t), ty(t) 대입
                tx_first, tx_last = _pick_first_last_kf(tx_kfs or [{"time_us": 0, "value": tx}])
                ty_first, ty_last = _pick_first_last_kf(ty_kfs or [{"time_us": 0, "value": ty}])
                tx0 = float(tx_first["value"]) if tx_first else tx
                tx1 = float(tx_last["value"]) if tx_last else tx0
                ty0 = float(ty_first["value"]) if ty_first else ty
                ty1 = float(ty_last["value"]) if ty_last else ty0
                # x_px(t) = ((tx0 + (tx1-tx0)*clamp(t/T,0,1)) * 0.5 + 0.5) * main_w - ov_w*0.5
                x_expr = (
                    f"(({tx0}+({tx1}-{tx0})*min(t/{dur_s:.6f}\\,1))*0.5+0.5)"
                    f"*{width}-{ov_w}*0.5"
                )
                y_expr = (
                    f"(1.0-(({ty0}+({ty1}-{ty0})*min(t/{dur_s:.6f}\\,1))*0.5+0.5))"
                    f"*{height}-{ov_h}*0.5"
                )
            else:
                x_expr = f"{x_static:.2f}"
                y_expr = f"{y_static:.2f}"

            # 오버레이 enable 윈도우 (타임라인 상 start_us ~ start_us+duration)
            start_s = seg["start_us"] / 1_000_000
            end_s = (seg["start_us"] + dur_us) / 1_000_000
            enable = f"between(t\\,{start_s:.3f}\\,{end_s:.3f})"

            new_main = f"[vmain{overlay_count+1}]"
            fc_parts.append(
                f"{current_main_label}{ov_prep_label}"
                f"overlay=x='{x_expr}':y='{y_expr}':enable='{enable}':"
                f"shortest=0"
                f"{new_main}"
            )
            current_main_label = new_main
            overlay_count += 1

    # 최종 메인 라벨
    if overlay_count > 0:
        post_overlay_label = current_main_label
    else:
        post_overlay_label = vout_label

    # -----------------------------------------------------------------
    # SRT burn-in (텍스트 있으면)
    # -----------------------------------------------------------------
    if text_segs and srt_path is not None:
        _write_srt_for_text_segments(text_segs, srt_path)
        escaped = _ffmpeg_escape_path(str(srt_path.resolve()))
        fc_parts.append(f"{post_overlay_label}subtitles='{escaped}'[vout]")
        vout_final = "[vout]"
    else:
        fc_parts.append(f"{post_overlay_label}null[vout]")
        vout_final = "[vout]"

    # -----------------------------------------------------------------
    # 오디오 입력
    # -----------------------------------------------------------------
    audio_filter_chain: list[str] = []
    audio_mix_labels: list[str] = []

    for ai, seg in enumerate(audio_segs):
        cmd += ["-i", seg["file"]]
        in_idx = input_index
        input_index += 1

        start_s = seg["start_us"] / 1_000_000
        dur_us = seg["duration_us"] or 0
        seg_extras = extras.get(seg["id"], {})
        afade_str = _build_afade_filters(seg_extras, dur_us)

        vol = float(seg["args"].get("volume", 1.0))
        body_parts: list[str] = []
        if dur_us > 0:
            body_parts.append(f"atrim=duration={dur_us/1_000_000:.3f}")
            body_parts.append("asetpts=PTS-STARTPTS")
        if afade_str:
            body_parts.append(afade_str)
        if abs(vol - 1.0) > 1e-6:
            body_parts.append(f"volume={vol:.3f}")
        if start_s > 0:
            delay_ms = int(start_s * 1000)
            body_parts.append(f"adelay={delay_ms}|{delay_ms}")
        filter_body = ",".join(body_parts) if body_parts else "anull"
        label = f"[a{ai}]"
        audio_filter_chain.append(f"[{in_idx}:a]{filter_body}{label}")
        audio_mix_labels.append(label)

    has_audio = bool(audio_segs)
    if has_audio:
        fc_parts.extend(audio_filter_chain)
        if len(audio_mix_labels) == 1:
            fc_parts.append(f"{audio_mix_labels[0]}anull[aout]")
        else:
            inputs_str = "".join(audio_mix_labels)
            fc_parts.append(
                f"{inputs_str}amix=inputs={len(audio_mix_labels)}:"
                f"duration=longest:normalize=0[aout]"
            )

    filter_complex = ";".join(fc_parts)
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", vout_final]
    if has_audio:
        cmd += ["-map", "[aout]"]

    cmd += [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart"]
    cmd += [output]

    info = {
        "analysis": analysis,
        "video_segments": len(video_segs),
        "overlay_segments": sum(len(v) for v in overlay_segs_by_track.values()),
        "audio_segments": len(audio_segs),
        "text_segments": len(text_segs),
        "filter_complex": filter_complex,
        "input_count": input_index,
        "xfade_used": has_any_transition,
    }
    return cmd, info


# =========================================================================
# 메인 render 함수
# =========================================================================


def render_headless(
    session: Session,
    output: str,
    *,
    crf: int = 20,
    preset: str = "medium",
    allow_unsupported: bool = False,
    dry_run: bool = False,
) -> dict:
    """세션을 ffmpeg headless 렌더 실행."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None and not dry_run:
        raise click.ClickException(
            "ffmpeg을 찾을 수 없음.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: winget install ffmpeg 또는 https://www.gyan.dev/ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        )

    analysis = analyze_session_for_render(session)

    if analysis["missing_files"]:
        raise click.ClickException(
            "미디어 파일 누락:\n  " + "\n  ".join(analysis["missing_files"])
        )

    if analysis["unsupported_ops"] and not allow_unsupported:
        reasons = "\n  ".join(
            f"#{u['index']} {u['op']} ({u['id']}): {u['reason']}"
            for u in analysis["unsupported_ops"]
        )
        raise click.ClickException(
            "미지원 op 발견. --allow-unsupported 로 계속하거나 해당 op 제거:\n  " + reasons
        )

    workdir = Path(tempfile.mkdtemp(prefix="capcut-headless-"))
    srt_path = workdir / "subs.srt"

    cmd, info = build_ffmpeg_command(
        session, output,
        crf=crf, preset=preset,
        srt_path=srt_path, workdir=workdir,
    )

    if dry_run:
        return {
            "status": "dry_run",
            "output": output,
            "duration_ms": 0,
            "ffmpeg_command": cmd,
            "warnings": analysis["warnings"],
            "unsupported_ops": analysis["unsupported_ops"],
            "analysis": {
                "total_duration_us": analysis["total_duration_us"],
                "total_duration_human": analysis["total_duration_human"],
                "video_segments": info["video_segments"],
                "overlay_segments": info["overlay_segments"],
                "audio_segments": info["audio_segments"],
                "text_segments": info["text_segments"],
                "video_tracks": analysis["video_tracks"],
                "overlay_video_tracks": analysis["overlay_video_tracks"],
                "audio_tracks": analysis["audio_tracks"],
                "text_tracks": analysis["text_tracks"],
                "xfade_used": info.get("xfade_used", False),
            },
        }

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        raise click.ClickException(f"ffmpeg 실행 실패: {e}") from e
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-40:])
        raise click.ClickException(
            f"ffmpeg 렌더 실패 (exit {proc.returncode}):\n{tail}"
        )

    return {
        "status": "rendered",
        "output": output,
        "duration_ms": elapsed_ms,
        "ffmpeg_command": cmd,
        "warnings": analysis["warnings"],
        "unsupported_ops": analysis["unsupported_ops"],
    }


# =========================================================================
# CLI 커맨드
# =========================================================================


@click.command(
    "render-headless",
    help="ffmpeg로 직접 렌더 (CapCut 없이, V1 concat + V2+ 오버레이 + xfade 지원)",
)
@click.option("-p", "--project", "project_path", required=True,
              help="세션 JSON 파일 경로")
@click.option("-o", "--output", "output_path", required=True,
              help="출력 mp4 경로")
@click.option("--crf", type=int, default=20, show_default=True,
              help="x264 품질 (낮을수록 고품질, 18~28 권장)")
@click.option("--preset",
              type=click.Choice(
                  ["ultrafast", "superfast", "veryfast", "faster", "fast",
                   "medium", "slow", "slower", "veryslow"]),
              default="medium", show_default=True,
              help="x264 인코딩 속도/압축 트레이드오프")
@click.option("--allow-unsupported", is_flag=True, default=False,
              help="미지원 op 있어도 무시하고 진행 (렌더 결과에 반영 안 됨)")
@click.option("--dry-run", is_flag=True, default=False,
              help="ffmpeg 명령만 출력하고 실행하지 않음")
@click.pass_context
def render_headless_cmd(ctx, project_path, output_path, crf, preset,
                        allow_unsupported, dry_run):
    session = load_session(project_path)
    result = render_headless(
        session,
        output_path,
        crf=crf,
        preset=preset,
        allow_unsupported=allow_unsupported,
        dry_run=dry_run,
    )
    as_json = ctx.obj.get("json", False)
    if not as_json:
        summary = {
            "status": result["status"],
            "output": result["output"],
            "duration_ms": result["duration_ms"],
            "warnings": result["warnings"],
            "unsupported_ops": [
                f"#{u['index']} {u['op']}" for u in result["unsupported_ops"]
            ],
        }
        if dry_run:
            summary["ffmpeg_command"] = " ".join(
                _shell_quote(a) for a in result["ffmpeg_command"]
            )
            if "analysis" in result:
                summary["analysis"] = result["analysis"]
        output_result(summary, False)
    else:
        output_result(result, True)


def _shell_quote(s: str) -> str:
    """사람이 읽기 좋은 shell quoting (실제 실행은 subprocess list 사용)."""
    if not s:
        return "''"
    special = any(ch in s for ch in ' \t"\'`\\$;&|()<>*?[]{}#')
    if special:
        return '"' + s.replace('"', '\\"') + '"'
    return s
