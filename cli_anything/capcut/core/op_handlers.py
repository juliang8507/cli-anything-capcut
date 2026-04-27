"""Op → pyCapCut ScriptFile 변환 핸들러.

`Session.replay()`가 op log를 훑으며 각 op를 여기 정의된 핸들러에 디스패치.
각 핸들러는 ``(script, args, ctx)`` 를 받고 ScriptFile을 mutate한다.

신규 op 타입을 추가하려면:
    1. `_OP_HANDLERS` 에 {op_name: handler_func} 엔트리 추가
    2. 필요하면 `op_registry.CREATION_OPS` / `MODIFIER_OPS` 에 포함

별칭 해결: 사용자가 `--name vignette` 같이 영어로 줘도 `alias_map.resolve_alias()`
가 한자 enum 이름으로 변환.
"""

from __future__ import annotations

from typing import Any, Callable

import pycapcut as cc

from cli_anything.capcut.core.alias_map import resolve_alias
from cli_anything.capcut.core.segment_utils import resolve_segment_ref
from cli_anything.capcut.core.time_utils import parse_time_value


_TRACK_TYPE_MAP = {
    "video": cc.TrackType.video,
    "audio": cc.TrackType.audio,
    "text": cc.TrackType.text,
    "effect": cc.TrackType.effect,
    "filter": cc.TrackType.filter,
    "sticker": cc.TrackType.sticker,
}


class OpHandlerError(RuntimeError):
    """op 처리 중 발생하는 에러 (복구/변환 실패)."""


# =========================================================================
# 공통 유틸
# =========================================================================


def _ensure_track(script: cc.ScriptFile, track_name: str | None, want_type: str) -> None:
    """replay 시 필요한 트랙이 없으면 자동 생성.

    pyCapCut의 `add_segment()`는 트랙이 미리 있어야 에러 없이 진행되고,
    이전 CLI 버그 리포트 #4/#9/#14에서 이 누락이 반복 문제였음.
    """
    if track_name is None:
        return
    if track_name in script.tracks:
        return
    track_type = _TRACK_TYPE_MAP.get(want_type)
    if track_type is not None:
        script.add_track(track_type, track_name)


def _clip_settings(args: dict) -> cc.ClipSettings | None:
    """``--clip-settings`` 옵션 JSON을 pyCapCut `ClipSettings`로 변환."""
    cs = args.get("clip_settings") or args.get("clip")
    if not cs:
        return None
    if isinstance(cs, str):
        # 이미 문자열 프리셋은 CLI 쪽에서 해석돼 dict로 와야 정상
        return None
    kwargs: dict[str, Any] = {}
    if "alpha" in cs:
        kwargs["alpha"] = float(cs["alpha"])
    if "rotation" in cs:
        kwargs["rotation"] = float(cs["rotation"])
    if "scale_x" in cs or "scale_y" in cs:
        kwargs["scale_x"] = float(cs.get("scale_x", 1.0))
        kwargs["scale_y"] = float(cs.get("scale_y", 1.0))
    if "transform_x" in cs or "transform_y" in cs:
        kwargs["transform_x"] = float(cs.get("transform_x", 0.0))
        kwargs["transform_y"] = float(cs.get("transform_y", 0.0))
    if "flip_horizontal" in cs:
        kwargs["flip_horizontal"] = bool(cs["flip_horizontal"])
    if "flip_vertical" in cs:
        kwargs["flip_vertical"] = bool(cs["flip_vertical"])
    return cc.ClipSettings(**kwargs) if kwargs else None


def _resolve_seg_index(ctx: dict, segment_ref: str | None, track: str | None) -> int | None:
    """segment_ref → 트랙 내 positional index. 없으면 None.

    ctx를 캐시로 재사용해서 replay 루프의 O(N²) 재순회를 O(N)로 축소.
    """
    if segment_ref is None:
        return None
    return resolve_segment_ref(ctx["session_data"], segment_ref, track, cache=ctx)


def _normalize_color(color: Any) -> tuple[float, float, float] | None:
    """[r,g,b] 또는 (r,g,b)를 0~1 범위 float tuple로 정규화. 0~255면 /255 자동 변환."""
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return None
    r, g, b = color[:3]
    if max(r, g, b) <= 1.0:
        return (float(r), float(g), float(b))
    return (r / 255.0, g / 255.0, b / 255.0)


def _resolve_enum(enum_class_name: str, enum_cls: Any, value: Any) -> Any:
    """alias 해결 + enum[] 접근을 한 번에. 실패 시 ``OpHandlerError`` 던짐."""
    try:
        resolved = resolve_alias(enum_class_name, value)
        return enum_cls[resolved]
    except (KeyError, ValueError) as e:
        raise OpHandlerError(
            f"'{value}'는 {enum_class_name}의 유효한 이름이 아님. "
            f"후보 검색: `cli-anything-capcut alias search --class {enum_class_name} "
            f"-k <키워드>` 또는 `alias list --class {enum_class_name}`"
        ) from e


# =========================================================================
# 구조 / 미디어
# =========================================================================


def _op_add_track(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    t = args.get("type")
    name = args.get("name")
    track_type = _TRACK_TYPE_MAP.get(t)
    if track_type is None:
        raise OpHandlerError(f"알 수 없는 트랙 타입: {t}")
    script.add_track(track_type, name)


def _op_add_video(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    file = args["file"]
    track = args.get("track")
    _ensure_track(script, track, "video")

    start_us = parse_time_value(args.get("start", 0))
    dur = args.get("duration")
    material = cc.VideoMaterial(file)
    if dur:
        dur_us = parse_time_value(dur)
        seg_range = cc.Timerange(start_us, dur_us)
        src_range = cc.Timerange(0, min(dur_us, material.duration))
    else:
        seg_range = cc.Timerange(start_us, material.duration)
        src_range = cc.Timerange(0, material.duration)

    segment = cc.VideoSegment(
        material,
        seg_range,
        source_timerange=src_range,
        clip_settings=_clip_settings(args),
        volume=float(args.get("volume", 1.0)),
        speed=float(args.get("speed", 1.0)),
    )
    script.add_segment(segment, track)
    ctx["last_segment"] = {"track": track, "segment": segment}


def _op_add_image(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    file = args["file"]
    track = args.get("track")
    _ensure_track(script, track, "video")

    start_us = parse_time_value(args.get("start", 0))
    dur_us = parse_time_value(args.get("duration", "3s"))
    material = cc.VideoMaterial(file)
    seg_range = cc.Timerange(start_us, dur_us)
    segment = cc.VideoSegment(material, seg_range, clip_settings=_clip_settings(args))
    script.add_segment(segment, track)
    ctx["last_segment"] = {"track": track, "segment": segment}


def _op_add_audio(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    file = args["file"]
    track = args.get("track")
    _ensure_track(script, track, "audio")

    start_us = parse_time_value(args.get("start", 0))
    dur = args.get("duration")
    material = cc.AudioMaterial(file)
    if dur:
        dur_us = parse_time_value(dur)
        seg_range = cc.Timerange(start_us, dur_us)
        src_range = cc.Timerange(0, min(dur_us, material.duration))
    else:
        seg_range = cc.Timerange(start_us, material.duration)
        src_range = cc.Timerange(0, material.duration)

    segment = cc.AudioSegment(
        material,
        seg_range,
        source_timerange=src_range,
        volume=float(args.get("volume", 1.0)),
        speed=float(args.get("speed", 1.0)),
    )
    script.add_segment(segment, track)
    ctx["last_segment"] = {"track": track, "segment": segment}


# =========================================================================
# Text
# =========================================================================


def _build_text_style(args: dict) -> cc.TextStyle | None:
    """--size/--color/--font/... 플래그들을 TextStyle로 조립."""
    kwargs: dict[str, Any] = {}
    if "size" in args and args["size"] is not None:
        kwargs["size"] = float(args["size"])
    if "bold" in args and args["bold"] is not None:
        kwargs["bold"] = bool(args["bold"])
    if "italic" in args and args["italic"] is not None:
        kwargs["italic"] = bool(args["italic"])
    if "underline" in args and args["underline"] is not None:
        kwargs["underline"] = bool(args["underline"])
    if "align" in args and args["align"] is not None:
        # pyCapCut align: 0=left, 1=center, 2=right
        align_map = {"left": 0, "center": 1, "right": 2}
        kwargs["align"] = align_map.get(args["align"], args["align"])
    if "color" in args and args["color"] is not None:
        normalized = _normalize_color(args["color"])
        if normalized is not None:
            kwargs["color"] = normalized
    if "letter_spacing" in args and args["letter_spacing"] is not None:
        kwargs["letter_spacing"] = float(args["letter_spacing"])
    if "line_spacing" in args and args["line_spacing"] is not None:
        kwargs["line_spacing"] = float(args["line_spacing"])
    return cc.TextStyle(**kwargs) if kwargs else None


def _build_text_border(args: dict) -> cc.TextBorder | None:
    b = args.get("border")
    if not b:
        return None
    kwargs: dict[str, Any] = {}
    if "alpha" in b:
        kwargs["alpha"] = float(b["alpha"])
    if "color" in b:
        normalized = _normalize_color(b["color"])
        if normalized is not None:
            kwargs["color"] = normalized
    if "width" in b:
        kwargs["width"] = float(b["width"])
    return cc.TextBorder(**kwargs) if kwargs else None


def _build_text_shadow(args: dict) -> cc.TextShadow | None:
    s = args.get("shadow")
    if not s:
        return None
    kwargs: dict[str, Any] = {}
    if "alpha" in s:
        kwargs["alpha"] = float(s["alpha"])
    if "color" in s:
        normalized = _normalize_color(s["color"])
        if normalized is not None:
            kwargs["color"] = normalized
    if "distance" in s:
        kwargs["distance"] = float(s["distance"])
    if "angle" in s:
        kwargs["angle"] = float(s["angle"])
    if "smoothing" in s:
        kwargs["smoothing"] = float(s["smoothing"])
    return cc.TextShadow(**kwargs) if kwargs else None


def _op_add_text(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """텍스트 세그먼트. 폰트/테두리/그림자는 TextSegment에 전달.

    버그 #17~#20 (pyCapCut이 반영 못 하는 필드)은 save 후 postprocess에서
    draft_content.json을 직접 패치하는 방식으로 보완 — 이 핸들러에선 일단 넘김.
    """
    text = args["text"]
    track = args.get("track")
    _ensure_track(script, track, "text")

    start_us = parse_time_value(args.get("start", 0))
    dur_us = parse_time_value(args.get("duration", "3s"))
    seg_range = cc.Timerange(start_us, dur_us)

    style = _build_text_style(args)
    border = _build_text_border(args)
    shadow = _build_text_shadow(args)
    font = args.get("font")
    font_type = None
    if font:
        try:
            font_type = _resolve_enum("FontType", cc.FontType, font)
        except OpHandlerError:
            font_type = None  # 미매칭 → 기본 폰트. postprocess에서 font_path 직접 패치

    segment = cc.TextSegment(
        text,
        seg_range,
        font=font_type,
        style=style,
        border=border,
        shadow=shadow,
        clip_settings=_clip_settings(args),
    )
    script.add_segment(segment, track)
    ctx["last_segment"] = {"track": track, "segment": segment}


# =========================================================================
# Effect / Filter
# =========================================================================


def _op_add_effect(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """씬/캐릭터 효과 트랙에 이펙트 세그먼트 추가.

    pyCapCut의 ``ScriptFile.add_effect()`` 를 사용해야 material 자동 등록됨.
    """
    name = args["name"]
    track = args.get("track")
    _ensure_track(script, track, "effect")

    start_us = parse_time_value(args.get("start", 0))
    dur_us = parse_time_value(args.get("duration", "3s"))

    effect_type: Any = None
    for enum_name, enum_cls in [
        ("VideoSceneEffectType", cc.VideoSceneEffectType),
        ("VideoCharacterEffectType", cc.VideoCharacterEffectType),
    ]:
        try:
            effect_type = _resolve_enum(enum_name, enum_cls, name)
            break
        except OpHandlerError:
            continue
    if effect_type is None:
        raise OpHandlerError(
            f"Unknown effect type: {name!r}. "
            "Check VideoSceneEffectType or VideoCharacterEffectType enums."
        )

    params = args.get("params")  # Optional[List[Optional[float]]]
    script.add_effect(effect_type, cc.Timerange(start_us, dur_us), track_name=track, params=params)


def _op_add_filter(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """필터 세그먼트. pyCapCut의 ``add_filter()`` 사용 (intensity 0~100)."""
    name = args["name"]
    track = args.get("track")
    _ensure_track(script, track, "filter")

    start_us = parse_time_value(args.get("start", 0))
    dur_us = parse_time_value(args.get("duration", "3s"))

    filter_type = _resolve_enum("FilterType", cc.FilterType, name)

    # 사용자가 0~1 또는 0~100 줄 수 있음. 1.0이면 100%로 해석.
    raw_intensity = float(args.get("intensity", 1.0))
    intensity = raw_intensity * 100.0 if raw_intensity <= 1.0 else raw_intensity
    script.add_filter(filter_type, cc.Timerange(start_us, dur_us),
                      track_name=track, intensity=intensity)


# =========================================================================
# Transition / Animation / Fade / Keyframe — 특정 세그먼트에 장식 추가
# =========================================================================


def _get_segment(script: cc.ScriptFile, track: str, index: int):
    """트랙 내 positional index로 세그먼트 조회."""
    if track not in script.tracks:
        raise OpHandlerError(f"트랙 없음: {track!r}")
    tr = script.tracks[track]
    segs = list(tr.segments)
    if index >= len(segs):
        raise OpHandlerError(f"트랙 {track!r}에 세그먼트 인덱스 {index} 없음 (보유: {len(segs)})")
    return segs[index]


def _op_add_video_transition(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_video_transition: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    tr_type = _resolve_enum("TransitionType", cc.TransitionType, args["name"])
    dur_us = parse_time_value(args.get("duration", "500ms"))
    seg.add_transition(tr_type, duration=dur_us)


def _op_add_video_fade(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_video_fade: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)
    in_us = parse_time_value(args.get("fade_in", 0))
    out_us = parse_time_value(args.get("fade_out", 0))
    seg.add_fade(in_duration=in_us, out_duration=out_us)


def _op_add_video_animation(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_video_animation: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    anim_role = args.get("role", "intro")  # intro / outro / group
    name = args["name"]
    dur_us = parse_time_value(args.get("duration", "500ms"))

    anim_map = {
        "intro": ("IntroType", cc.IntroType),
        "outro": ("OutroType", cc.OutroType),
        "group": ("GroupAnimationType", cc.GroupAnimationType),
    }
    if anim_role not in anim_map:
        raise OpHandlerError(f"알 수 없는 animation role: {anim_role}")
    enum_name, enum_cls = anim_map[anim_role]
    seg.add_animation(_resolve_enum(enum_name, enum_cls, name), duration=dur_us)


def _op_add_text_animation(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_text_animation: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    anim_role = args.get("role", "intro")
    name = args["name"]
    dur_us = parse_time_value(args.get("duration", "500ms"))
    anim_map = {
        "intro": ("TextIntro", cc.TextIntro),
        "outro": ("TextOutro", cc.TextOutro),
        "loop": ("TextLoopAnim", cc.TextLoopAnim),
    }
    if anim_role not in anim_map:
        raise OpHandlerError(f"알 수 없는 text animation role: {anim_role}")
    enum_name, enum_cls = anim_map[anim_role]
    seg.add_animation(_resolve_enum(enum_name, enum_cls, name), duration=dur_us)


_KEYFRAME_PROP_MAP = {
    "alpha": cc.KeyframeProperty.alpha,
    "position_x": cc.KeyframeProperty.position_x,
    "position_y": cc.KeyframeProperty.position_y,
    "rotation": cc.KeyframeProperty.rotation,
    "scale_x": cc.KeyframeProperty.scale_x,
    "scale_y": cc.KeyframeProperty.scale_y,
    "uniform_scale": cc.KeyframeProperty.uniform_scale,
    "volume": cc.KeyframeProperty.volume,
}


def _op_add_keyframe(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_keyframe: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    prop_name = args["property"]
    prop = _KEYFRAME_PROP_MAP.get(prop_name)
    if prop is None:
        raise OpHandlerError(
            f"알 수 없는 keyframe property: {prop_name}. "
            f"Use one of: {', '.join(_KEYFRAME_PROP_MAP)}"
        )
    time_us = parse_time_value(args["time"])
    value = float(args["value"])
    seg.add_keyframe(prop, time_us, value)


def _op_add_audio_fade(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_audio_fade: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)
    in_us = parse_time_value(args.get("fade_in", 0))
    out_us = parse_time_value(args.get("fade_out", 0))
    if hasattr(seg, "add_fade"):
        seg.add_fade(in_duration=in_us, out_duration=out_us)


def _op_add_audio_effect(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_audio_effect: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)
    fx = _resolve_enum("AudioSceneEffectType", cc.AudioSceneEffectType, args["name"])
    if hasattr(seg, "add_effect"):
        seg.add_effect(fx)


# =========================================================================
# 스티커 (최소)
# =========================================================================


def _op_add_sticker(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """스티커(=이미지+키프레임 가능한 세그먼트).

    pyCapCut의 StickerSegment는 기본적으로 VideoMaterial 위에서 동작.
    """
    file = args["file"]
    track = args.get("track")
    _ensure_track(script, track, "sticker")

    start_us = parse_time_value(args.get("start", 0))
    dur_us = parse_time_value(args.get("duration", "3s"))
    material = cc.VideoMaterial(file)
    seg_range = cc.Timerange(start_us, dur_us)
    segment = cc.StickerSegment(material, seg_range, clip_settings=_clip_settings(args))
    script.add_segment(segment, track)
    ctx["last_segment"] = {"track": track, "segment": segment}


# =========================================================================
# 레지스트리
# =========================================================================


HandlerFn = Callable[[cc.ScriptFile, dict, dict], None]

def _op_noop(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """Replay 무시. postprocess 단계에서 처리되거나 정보용으로만 저장된 op."""
    pass


# =========================================================================
# Mask / Background (심화 API)
# =========================================================================


def _op_add_mask(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """비디오 세그먼트에 마스크 추가 (circle/rectangle/heart/...)."""
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_mask: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    mask_type = _resolve_enum("MaskType", cc.MaskType, args["name"])

    kwargs: dict[str, Any] = {}
    for opt in ("center_x", "center_y", "size", "rotation", "feather",
                "rect_width", "round_corner"):
        if opt in args and args[opt] is not None:
            kwargs[opt] = float(args[opt])
    if args.get("invert") is not None:
        kwargs["invert"] = bool(args["invert"])

    seg.add_mask(mask_type, **kwargs)


def _op_add_background(script: cc.ScriptFile, args: dict, ctx: dict) -> None:
    """비디오 세그먼트에 배경 채우기. fill_type: blur | color."""
    track = args["track"]
    seg_ref = args.get("segment_ref")
    seg_idx = _resolve_seg_index(ctx, seg_ref, track)
    if seg_idx is None:
        raise OpHandlerError("add_background: segment_ref 필수")
    seg = _get_segment(script, track, seg_idx)

    fill_type = args.get("fill_type", "blur")
    blur = float(args.get("blur", 0.0625))
    color = args.get("color", "#00000000")
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        r, g, b = color[:3]
        if max(r, g, b) <= 1.0:
            r, g, b = int(r * 255), int(g * 255), int(b * 255)
        color = f"#{int(r):02x}{int(g):02x}{int(b):02x}00"
    seg.add_background_filling(fill_type, blur=blur, color=color)


_OP_HANDLERS: dict[str, HandlerFn] = {
    # 구조
    "add_track": _op_add_track,
    # 미디어 생성
    "add_video": _op_add_video,
    "add_image": _op_add_image,
    "add_audio": _op_add_audio,
    "add_text": _op_add_text,
    "add_sticker": _op_add_sticker,
    # Effect / Filter (트랙 세그먼트)
    "add_effect": _op_add_effect,
    "add_filter": _op_add_filter,
    # 세그먼트 장식
    "add_video_transition": _op_add_video_transition,
    "add_video_fade": _op_add_video_fade,
    "add_video_animation": _op_add_video_animation,
    "add_text_animation": _op_add_text_animation,
    "add_keyframe": _op_add_keyframe,
    "add_audio_fade": _op_add_audio_fade,
    "add_audio_effect": _op_add_audio_effect,
    # 심화 API
    "add_mask": _op_add_mask,
    "add_background": _op_add_background,
    # postprocess only — replay에서는 noop
    "text_style_patch": _op_noop,
    "text_transform_patch": _op_noop,
    "color_adjust": _op_noop,
    "color_wheels": _op_noop,
}


def apply_operation(script: cc.ScriptFile, op: str, args: dict, ctx: dict) -> None:
    """op 이름에 해당하는 핸들러 호출."""
    handler = _OP_HANDLERS.get(op)
    if handler is None:
        raise OpHandlerError(f"지원하지 않는 op: {op}")
    handler(script, args, ctx)


def list_ops() -> list[str]:
    """등록된 op 이름 전체."""
    return sorted(_OP_HANDLERS)
