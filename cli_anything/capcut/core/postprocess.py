"""Save 후 draft_content.json 직접 패치.

pyCapCut이 제대로 반영 못 하는 필드들을 save가 끝난 뒤 JSON을 읽어 수정하고
다시 쓰는 방식으로 보완한다. 버그 리포트 #17~#21 대응.

패치 op 종류:
    - text_style_patch   : 특정 text 세그먼트의 font/border/shadow/color 덮어쓰기
    - text_transform_patch : clip.transform.{x,y} 덮어쓰기 (위치)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli_anything.capcut.core.op_registry import POSTPROCESS_OPS
from cli_anything.capcut.core.segment_utils import resolve_segment_ref


def _rgb_to_hex(color: Any) -> str | None:
    """[r,g,b] (0-1 또는 0-255) → '#rrggbb'."""
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return None
    r, g, b = color[:3]
    if max(r, g, b) <= 1.0:
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _find_text_segment(draft_json: dict, track_name: str, seg_index: int) -> dict | None:
    """draft_content.json에서 특정 텍스트 세그먼트 찾기."""
    for track in draft_json.get("tracks", []):
        if track.get("type") != "text":
            continue
        if track.get("name") != track_name:
            continue
        segs = track.get("segments", [])
        if seg_index < len(segs):
            return segs[seg_index]
    return None


def _find_text_material(draft_json: dict, material_id: str) -> dict | None:
    for tm in draft_json.get("materials", {}).get("texts", []):
        if tm.get("id") == material_id:
            return tm
    return None


def apply_text_style_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """font_path / border_* / shadow_* / font_color 직접 기록.

    버그 #17, #18, #19, #20 대응.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("text_style_patch: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"text_style_patch: {e}")
        return warnings

    seg = _find_text_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"text_style_patch: 세그먼트 없음 (track={track}, index={idx})")
        return warnings
    mat = _find_text_material(draft_json, seg.get("material_id", ""))
    if mat is None:
        warnings.append("text_style_patch: text material 없음")
        return warnings

    # 폰트 경로 (버그 #17)
    if "font_path" in args:
        mat["font_path"] = args["font_path"]
    if "font_resource_id" in args:
        mat["font_resource_id"] = args["font_resource_id"]

    # 색 (버그 #20) — "None" 문자열 대신 hex
    if "color" in args:
        hex_col = _rgb_to_hex(args["color"])
        if hex_col:
            mat["font_color"] = hex_col

    # 테두리 (버그 #18)
    border = args.get("border")
    if border:
        hex_col = _rgb_to_hex(border.get("color", [0, 0, 0]))
        if hex_col:
            mat["border_color"] = hex_col
        if "alpha" in border:
            mat["border_alpha"] = float(border["alpha"])
        if "width" in border:
            mat["border_width"] = float(border["width"])

    # 그림자 (버그 #19)
    shadow = args.get("shadow")
    if shadow:
        import math

        mat["has_shadow"] = True
        if "alpha" in shadow:
            mat["shadow_alpha"] = float(shadow["alpha"])
        hex_col = _rgb_to_hex(shadow.get("color", [0, 0, 0]))
        if hex_col:
            mat["shadow_color"] = hex_col
        if "distance" in shadow:
            mat["shadow_distance"] = float(shadow["distance"])
        if "smoothing" in shadow:
            mat["shadow_smoothing"] = float(shadow["smoothing"])
        # angle → shadow_point (단위 원 좌표)
        angle = shadow.get("angle")
        if angle is not None:
            rad = math.radians(float(angle))
            mat["shadow_point"] = {"x": math.cos(rad), "y": -math.sin(rad)}

    return warnings


def _find_video_segment(draft_json: dict, track_name: str, seg_index: int) -> dict | None:
    for track in draft_json.get("tracks", []):
        if track.get("type") != "video":
            continue
        if track.get("name") != track_name:
            continue
        segs = track.get("segments", [])
        if seg_index < len(segs):
            return segs[seg_index]
    return None


def apply_color_adjust_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """비디오 세그먼트에 색 보정 값 반영 (draft_content.json 직접 패치).

    CapCut은 ``materials.adjusts[]``에 보정값을 저장하고 세그먼트가
    ``extra_material_refs``로 참조하는 방식. 간단히 세그먼트에 직접
    ``hdr_settings`` 또는 ``color_correct`` 필드에 기록.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("color_adjust: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"color_adjust: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"color_adjust: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    # hdr_settings 에 색 보정 구조 추가 (CapCut 포맷)
    hdr = seg.setdefault("hdr_settings", {"intensity": 1.0, "mode": 1, "nits": 1000})

    # color_correct dict에 개별 값 기록
    cc_dict = seg.setdefault("common_keyframes", [])  # 보정 슬롯
    # CapCut 실제로는 materials.adjusts에 별도 entry 필요하지만,
    # 여기서는 세그먼트 자체 fields에 기록하는 간단 방식 사용:
    for field in ("brightness", "contrast", "saturation", "temperature",
                  "highlights", "shadows", "vibrance"):
        val = args.get(field)
        if val is not None:
            seg.setdefault("color_adjust", {})[field] = float(val)
    return warnings


def apply_color_wheels_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """컬러 휠 (shadows/midtones/highlights 색조)."""
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("color_wheels: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"color_wheels: {e}")
        return warnings
    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"color_wheels: 세그먼트 없음")
        return warnings

    wheels = seg.setdefault("color_wheels", {})
    for slot in ("shadows", "midtones", "highlights"):
        color = args.get(f"{slot}_color")
        if color and isinstance(color, (list, tuple)) and len(color) >= 3:
            wheels[slot] = list(color[:3])
    return warnings


def apply_text_transform_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """clip.transform.{x,y} 직접 기록 (버그 #21)."""
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("text_transform_patch: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"text_transform_patch: {e}")
        return warnings

    seg = _find_text_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"text_transform_patch: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    clip = seg.setdefault("clip", {})
    transform = clip.setdefault("transform", {"x": 0.0, "y": 0.0})
    if "x" in args:
        transform["x"] = float(args["x"])
    if "y" in args:
        transform["y"] = float(args["y"])
    return warnings


# ===========================================================================
# v0.4.3 복원 핸들러 — v0.3 _apply_* 이식
# ===========================================================================

# 블렌드 모드 이름 → 정수 매핑
# 출처: CapCut draft JSON 관찰 값 + CapCutAPI/VectCutAPI GitHub 조사 결과.
# 공식 문서 없음 — "합리적 기본값" (주석에 명시). 추후 GUI 확인 권장.
BLEND_MODES: dict[str, int] = {
    "normal": 0,
    "multiply": 1,
    "screen": 2,
    "overlay": 3,
    "darken": 4,
    "lighten": 5,
    "add": 6,          # linear-dodge 와 동일 처리
    "linear_dodge": 6,
    "color_dodge": 7,
    "color_burn": 8,
    "hard_light": 9,
    "soft_light": 10,
    "difference": 11,
    "exclusion": 12,
    "linear_burn": 13,
    "vivid_light": 14,
    "linear_light": 15,
    "pin_light": 16,
}


def _new_uuid() -> str:
    """유니크 ID 생성 (CapCut material ID 용)."""
    import uuid
    return uuid.uuid4().hex


def apply_reverse_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """비디오 세그먼트에 역재생 플래그 설정.

    segment["reverse"] = True 한 줄만 패치.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("set_reverse: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"set_reverse: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"set_reverse: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    seg["reverse"] = True
    return warnings


def apply_freeze_frame_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """세그먼트의 speed material을 freeze 모드로 설정.

    speed material이 없으면 세그먼트 직접에 speed 관련 필드를 기록하는 방식으로 폴백.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("set_freeze_frame: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"set_freeze_frame: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"set_freeze_frame: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    # speed material ref_id 를 통해 materials.speeds 에서 찾기
    speed_mat_id = None
    for ref_id in seg.get("extra_material_refs", []):
        for sm in draft_json.get("materials", {}).get("speeds", []):
            if sm.get("id") == ref_id:
                speed_mat_id = ref_id
                sm["mode"] = "freeze"
                sm["speed"] = 0.0
                break
        if speed_mat_id:
            break

    if speed_mat_id is None:
        # speed material 없음 → 세그먼트 직접 패치 (폴백)
        seg.setdefault("speed_info", {}).update({"mode": "freeze", "speed": 0.0})
        warnings.append("set_freeze_frame: speed material 없음, 세그먼트 직접 패치")

    return warnings


def apply_blend_mode_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """세그먼트의 track_attribute.blend_mode 정수값 설정."""
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    mode = args.get("mode", "normal")
    if not track or not seg_ref:
        warnings.append("set_blend_mode: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"set_blend_mode: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"set_blend_mode: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    int_val = BLEND_MODES.get(mode.lower().replace("-", "_"))
    if int_val is None:
        warnings.append(f"set_blend_mode: 알 수 없는 모드 '{mode}', normal(0) 사용")
        int_val = 0

    seg.setdefault("track_attribute", {})["blend_mode"] = int_val
    return warnings


def apply_chroma_key_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """크로마 키(그린스크린) material 추가 + 세그먼트에 연결.

    CapCut JSON 구조:
      - materials.video_chromakeys[] 에 material 추가
      - segment.extra_material_refs[] 에 material id 연결
    키 이름은 _recovered/postprocess.info.md string constants 기준.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("set_chroma_key: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"set_chroma_key: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"set_chroma_key: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    color = args.get("color", "#00FF00")
    # hex 그대로 저장 (CapCut GUI도 "#RRGGBB" 형식 사용)
    new_material = {
        "id": _new_uuid(),
        "type": "video_chromakey",
        "color": color,
        "intensity": float(args.get("intensity", 0.5)),
        "shadow": float(args.get("shadow", 0.5)),
        "smoothness": float(args.get("smoothness", 0.1)),
        "spill_correction": float(args.get("spill", 0.0)),
    }

    # materials.video_chromakeys 배열에 추가
    draft_json.setdefault("materials", {}).setdefault("video_chromakeys", []).append(new_material)

    # 세그먼트의 extra_material_refs 에 id 연결
    seg.setdefault("extra_material_refs", []).append(new_material["id"])

    return warnings


# ===========================================================================
# v0.4.4 복원 핸들러 — video lut / video speed-curve / color curves / color hsl
# ===========================================================================


def apply_lut_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """LUT 파일을 세그먼트에 적용.

    CapCut JSON 구조 (v0.3 _recovered/postprocess.info.md 기준):
      - materials.video_luts[] 에 LUT material 추가
      - segment.extra_material_refs[] 에 material id 연결
      - segment["enable_lut"] = True 설정
    JSON 키: "enable_lut", "video_luts", "intensity", "name", "file"
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("add_lut: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"add_lut: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"add_lut: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    lut_file = args.get("file", "")
    lut_name = args.get("name") or "Custom LUT"
    intensity = float(args.get("intensity", 1.0))

    # .cube 이외 확장자 경고 (블로커 아님)
    import pathlib
    ext = pathlib.Path(lut_file).suffix.lower() if lut_file else ""
    if lut_file and ext not in (".cube", ".3dl", ".look", ".lut"):
        warnings.append(f"add_lut: 비표준 확장자 '{ext}'. .cube 권장")

    # LUT material 생성 및 등록
    lut_material = {
        "id": _new_uuid(),
        "type": "lut",  # v0.3 string constants: 'lut'
        "file": lut_file,
        "intensity": intensity,
        "name": lut_name,
    }
    draft_json.setdefault("materials", {}).setdefault("video_luts", []).append(lut_material)

    # 세그먼트 연결 및 플래그 설정
    seg.setdefault("extra_material_refs", []).append(lut_material["id"])
    seg["enable_lut"] = True  # v0.3 string constants: 'enable_lut'

    return warnings


def apply_speed_curve_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """speed material에 curve 모드 + 포인트 주입.

    v0.3 기준: speed material의 mode="curve", curve_speed.points 주입.
    speed material이 없으면 새로 생성 후 extra_material_refs에 연결.
    JSON 키: "curve_speed", "points", "mode", "speeds"
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("set_speed_curve: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"set_speed_curve: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"set_speed_curve: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    points_raw = args.get("points", [])
    curve_range = args.get("curve_range", [0.0, 1.0])

    # 포인트 리스트 → {"x": time_ratio, "y": speed} dict 변환
    point_dicts = [{"x": float(t), "y": float(s)} for (t, s) in points_raw]

    # 기존 speed material 찾기 (extra_material_refs 통해)
    speed_mat = None
    for ref_id in seg.get("extra_material_refs", []):
        for sm in draft_json.get("materials", {}).get("speeds", []):
            if sm.get("id") == ref_id:
                speed_mat = sm
                break
        if speed_mat:
            break

    if speed_mat is None:
        # speed material 없음 → 새로 생성
        speed_mat = {
            "id": _new_uuid(),
            "mode": "curve",
            "speed": 1.0,
            "curve_speed": {
                "points": point_dicts,
                "curve_range": curve_range,  # v0.3 string constants: 'curve_range'
            },
        }
        draft_json.setdefault("materials", {}).setdefault("speeds", []).append(speed_mat)
        seg.setdefault("extra_material_refs", []).append(speed_mat["id"])
        warnings.append("set_speed_curve: speed material 없음, 새로 생성")
    else:
        # 기존 material 업데이트
        speed_mat["mode"] = "curve"
        speed_mat.setdefault("curve_speed", {})["points"] = point_dicts
        speed_mat["curve_speed"]["curve_range"] = curve_range

    return warnings


def apply_color_curves_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """color_curves material 추가 + 세그먼트에 연결.

    CapCut JSON 구조 (v0.3 _recovered/postprocess.info.md 기준):
      - materials.color_curves[] 에 material 추가
      - segment.extra_material_refs[] 에 material id 연결
      - segment["enable_color_curves"] = True
    JSON 키: "color_curves", "color_curve", "enable_color_curves", "rgb", "red", "green", "blue"
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("add_color_curves: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"add_color_curves: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"add_color_curves: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    # 최소 1개 채널 필수
    rgb_pts = args.get("rgb")
    red_pts = args.get("red")
    green_pts = args.get("green")
    blue_pts = args.get("blue")

    if not any([rgb_pts, red_pts, green_pts, blue_pts]):
        warnings.append("add_color_curves: 최소 1개 채널 필수 (--rgb/--red/--green/--blue)")
        return warnings

    # 포인트 리스트 → {"x": in, "y": out} dict 변환
    def _to_points(pts):
        if pts is None:
            return None
        return [{"x": float(x), "y": float(y)} for (x, y) in pts]

    curves_material = {
        "id": _new_uuid(),
        "type": "color_curves",  # v0.3 string constants: 'color_curves'
    }
    # 각 채널 포인트 저장 (None이면 키 제외)
    if rgb_pts is not None:
        curves_material["rgb_points"] = _to_points(rgb_pts)
    if red_pts is not None:
        curves_material["red_points"] = _to_points(red_pts)
    if green_pts is not None:
        curves_material["green_points"] = _to_points(green_pts)
    if blue_pts is not None:
        curves_material["blue_points"] = _to_points(blue_pts)

    # materials.color_curves 배열에 추가
    draft_json.setdefault("materials", {}).setdefault("color_curves", []).append(curves_material)

    # 세그먼트 연결 및 플래그 설정
    seg.setdefault("extra_material_refs", []).append(curves_material["id"])
    seg["enable_color_curves"] = True  # v0.3 string constants: 'enable_color_curves'

    return warnings


# HSL target_color 선택지 (v0.3 color.info.md 기준)
HSL_TARGET_CHOICES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"]


def apply_hsl_patch(draft_json: dict, args: dict, session_data: dict) -> list[str]:
    """target_color 채널별 HSL 주입.

    CapCut JSON 구조 (v0.3 _recovered/postprocess.info.md 기준):
      - materials.material_colors[] (hsl_adjusts) 에 entry 추가/업데이트
      - target_color 별 hue/saturation/lightness 저장
      - segment["enable_color_correct_adjust"] = True
    JSON 키: "material_colors", "target_color", "hue", "saturation", "lightness",
             "enable_color_correct_adjust"
    같은 segment에 여러 target 누적 적용 지원.
    """
    warnings: list[str] = []
    track = args.get("track")
    seg_ref = args.get("segment_ref")
    if not track or not seg_ref:
        warnings.append("add_hsl_adjust: track/segment_ref 필수")
        return warnings
    try:
        idx = resolve_segment_ref(session_data, seg_ref, track)
    except ValueError as e:
        warnings.append(f"add_hsl_adjust: {e}")
        return warnings

    seg = _find_video_segment(draft_json, track, idx)
    if seg is None:
        warnings.append(f"add_hsl_adjust: 세그먼트 없음 (track={track}, index={idx})")
        return warnings

    target = args.get("target")
    if not target:
        warnings.append("add_hsl_adjust: --target 필수")
        return warnings

    # 수치: -100~+100 (UX) → -1.0~+1.0 (내부 저장)
    hue = float(args.get("hue", 0)) / 100.0
    saturation = float(args.get("saturation", 0)) / 100.0
    lightness = float(args.get("lightness", 0)) / 100.0

    # materials.material_colors에서 해당 segment_id의 entry 찾기
    # v0.3 string constants: 'material_colors', 'target_color'
    hsl_list = draft_json.setdefault("materials", {}).setdefault("material_colors", [])
    existing = next((m for m in hsl_list if m.get("segment_id") == seg.get("id")), None)

    if existing is None:
        existing = {
            "id": _new_uuid(),
            "segment_id": seg.get("id"),
            "adjusts": {},
        }
        hsl_list.append(existing)

    # target_color 별 HSL 값 덮어쓰기 (중복 호출 시 업데이트)
    existing["adjusts"][target] = {
        "hue": hue,
        "saturation": saturation,
        "lightness": lightness,
    }

    # 세그먼트 플래그 설정
    seg["enable_color_correct_adjust"] = True  # v0.3 string constants

    return warnings


def apply_postprocess(draft_content_path: Path, session_data: dict) -> dict:
    """세션 op 중 POSTPROCESS_OPS에 해당하는 것을 순서대로 적용."""
    post_ops = [o for o in session_data.get("operations", []) if o["op"] in POSTPROCESS_OPS]
    if not post_ops:
        return {"applied": 0, "warnings": []}

    draft_content_path = Path(draft_content_path)
    if not draft_content_path.exists():
        return {"applied": 0, "warnings": [f"draft_content.json 없음: {draft_content_path}"]}

    draft_json = json.loads(draft_content_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    for op in post_ops:
        args = op.get("args", {})
        if op["op"] == "text_style_patch":
            warnings.extend(apply_text_style_patch(draft_json, args, session_data))
        elif op["op"] == "text_transform_patch":
            warnings.extend(apply_text_transform_patch(draft_json, args, session_data))
        elif op["op"] == "color_adjust":
            warnings.extend(apply_color_adjust_patch(draft_json, args, session_data))
        elif op["op"] == "color_wheels":
            warnings.extend(apply_color_wheels_patch(draft_json, args, session_data))
        # v0.4.3 복원
        elif op["op"] == "set_reverse":
            warnings.extend(apply_reverse_patch(draft_json, args, session_data))
        elif op["op"] == "set_freeze_frame":
            warnings.extend(apply_freeze_frame_patch(draft_json, args, session_data))
        elif op["op"] == "set_blend_mode":
            warnings.extend(apply_blend_mode_patch(draft_json, args, session_data))
        elif op["op"] == "set_chroma_key":
            warnings.extend(apply_chroma_key_patch(draft_json, args, session_data))
        # v0.4.4 복원
        elif op["op"] == "add_lut":
            warnings.extend(apply_lut_patch(draft_json, args, session_data))
        elif op["op"] == "set_speed_curve":
            warnings.extend(apply_speed_curve_patch(draft_json, args, session_data))
        elif op["op"] == "add_color_curves":
            warnings.extend(apply_color_curves_patch(draft_json, args, session_data))
        elif op["op"] == "add_hsl_adjust":
            warnings.extend(apply_hsl_patch(draft_json, args, session_data))

    draft_content_path.write_text(
        json.dumps(draft_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"applied": len(post_ops), "warnings": warnings}
