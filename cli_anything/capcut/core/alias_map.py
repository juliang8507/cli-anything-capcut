"""pyCapCut 중국어 enum에 대한 영어 별칭 매핑.

pyCapCut의 `TransitionType`, `FilterType`, `VideoSceneEffectType`, `IntroType` 등은
enum 멤버명이 한자(예: `叠化`, `暗角`). 영어로 쓰기 편하게 별칭을 제공하고, 이미
한자 이름을 직접 쓰면 그대로 통과시킨다.

버그 리포트 대응:
    - #2  TransitionType: `dissolve` → `叠化` (이전에 `溶解`는 enum에 존재하지 않음)
    - #3  IntroType/OutroType: 단독 `淡入`/`淡出` 없음 → 복합형 `炫目淡入` 등 사용
    - #15 TextOutro: `淡出` 없음 → `渐隐` 사용

편의 API:
    - resolve_alias(enum_class_name, name)  — 영→한자 해석 (통과 허용)
    - reverse_alias(enum_class, chinese_name)  — 한자→영 (있으면)
    - search_enum(enum_class_name, keyword, limit)  — 퍼지 검색
    - list_enum_classes()  — 지원 enum 카테고리
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Type

import pycapcut as cc


# =========================================================================
# 카테고리별 별칭 (영어 → pyCapCut 실제 enum 멤버명)
# =========================================================================

# 비디오 전환 효과 (TransitionType)
TRANSITION_ALIASES: dict[str, str] = {
    # 기본 — 버그 #2 수정: dissolve는 叠化 (溶解 아님)
    "dissolve": "叠化",
    "cross_dissolve": "叠化",
    "fade": "叠化",
    "fade_in": "渐显",
    "fade_out": "渐隐",
    # 흑백/반전
    "white_flash": "White_Flash",
    "black_flash": "黑场",
    "black": "黑场",
    # 방향
    "slide_left": "左移",
    "slide_right": "右移",
    "slide_up": "上移",
    "slide_down": "下移",
    "push_left": "左移",
    "push_right": "右移",
    "push_up": "上移",
    "push_down": "下移",
    # 줌
    "zoom_in": "放大",
    "zoom_out": "缩小",
    # 와이프
    "wipe_left": "左擦除",
    "wipe_right": "右擦除",
    "wipe_up": "上擦除",
    "wipe_down": "下擦除",
    # 회전/3D
    "rotate": "旋转",
    "rotate_3d": "3D旋转",
    "3d_space": "_3D空间",
    "flip": "翻转",
    "flip_in": "翻转",
    # 블러
    "blur": "模糊",
    "gaussian_blur": "模糊",
    "motion_blur": "动感模糊",
    "radial_blur": "径向模糊",
    # 분할
    "center_split": "中间分割",
    "split_h": "水平分割",
    "split_v": "垂直分割",
    "three_split": "三分屏",
    # 기타
    "heartbeat": "心跳",
    "pixelate": "像素化",
    "glitch": "故障",
    "cutout_flip": "Cutout_Flip",
    "fold_over": "Fold_Over",
}

# 필터 (FilterType)
FILTER_ALIASES: dict[str, str] = {
    # 온도
    "warm": "暖黄",
    "warm_yellow": "暖黄",
    "warm_dawn": "暖黄",
    "warm_sun": "暖阳",
    "cool": "冷蓝",
    "cool_blue": "冷蓝",
    # 시간대
    "golden_hour": "黄金时刻",
    "sunset": "落日",
    "sunrise": "日出",
    "twilight": "暮光",
    # 스타일
    "classic": "经典",
    "cinematic": "电影感",
    "vintage": "复古",
    "film": "胶片",
    "film_grain": "胶片颗粒",
    # 흑백
    "bw": "黑白",
    "black_white": "黑白",
    "grayscale": "灰度",
    "bw_2": "BW_2",
    "bw_3": "BW_3",
    # 영문 그대로
    "badbunny": "Badbunny",
    "daisies_glow": "Daisies_Glow",
    "lover_blue": "Lover_Blue",
    "party_tonight": "Party_Tonight",
    "peach_fuzz": "Peach_Fuzz",
    "purple_sunset": "Purple_Sunset",
    "reindeer": "Reindeer",
    # 컬러 그레이딩
    "teal_orange": "青橙",
    "blue_gold": "蓝金",
    # 분위기
    "natural": "自然",
    "portrait": "人像",
    "landscape": "风景",
    "food": "美食",
    "bright": "明亮",
}

# 비디오 씬 효과 (VideoSceneEffectType) — 버그 #12 정답
VIDEO_SCENE_EFFECT_ALIASES: dict[str, str] = {
    "vignette": "暗角",
    "soft": "柔光",
    "soft_light": "柔光",
    "glow": "光晕",
    "lens_flare": "镜头光晕",
    "light_leak": "漏光",
    "glitch": "故障",
    "light_glitch": "光故障",
    "chromatic": "色差",
    "chromatic_aberration": "色差",
    "pixelate": "像素化",
    "blur": "模糊",
    "gaussian_blur": "高斯模糊",
    "motion_blur": "动感模糊",
    "radial_blur": "径向模糊",
    "mosaic": "马赛克",
    "oil_paint": "油画",
    "watercolor": "水彩",
    "sketch": "素描",
    "cartoon": "卡通",
    "retro": "复古",
    "old_film": "老电影",
    "heartbeat": "心跳",
    "shake": "抖动",
    "shake_h": "水平抖动",
    "shake_horizontal": "水平抖动",
    "shake_v": "垂直抖动",
    "shake_vertical": "垂直抖动",
    "neon": "霓虹",
    "neon_glow": "霓虹光",
}

# 비디오 인트로 (IntroType) — 버그 #3: 단독 `淡入` 없음
INTRO_ALIASES: dict[str, str] = {
    "fade_in": "炫目淡入",      # 가장 흔한 fade_in 대체
    "zoom_in": "动感放大",
    "scale_up": "动感放大",
    "zoom_out": "动感缩小",
    "slide_up": "向上滑动",
    "slide_down": "向下滑动",
    "slide_left": "向左滑动",
    "slide_right": "向右滑动",
    "rotate_in": "旋入",
    "rotate_in_up": "向上转入",
    "bounce_in": "弹性进入",
    "spin": "旋入",
    "drop_in": "掉落",
    "blur_open": "模糊展开",
    "mc_explosion": "MC爆炸",
    "reverse": "反转回正",
    "tremble": "上下抖动",
}

# 비디오 아웃트로 (OutroType)
OUTRO_ALIASES: dict[str, str] = {
    "fade_out": "碎片淡出",
    "zoom_in": "动感放大",
    "zoom_out": "动感缩小",
    "slide_up": "向上滑出",
    "slide_down": "向下滑出",
    "slide_left": "向左滑出",
    "slide_right": "向右滑出",
    "rotate_out": "旋出",
    "blur_out": "模糊收束",
}

# 텍스트 인트로 (TextIntro)
TEXT_INTRO_ALIASES: dict[str, str] = {
    "fade_in": "渐显",
    "karaoke": "卡拉OK",
    "typewriter": "打字机",
    "typewriter_i": "打字机I",
    "typewriter_ii": "打字机II",
    "bounce": "可爱悦动",
    "scale_up": "放大",
    "slide_up": "向上滑入",
    "slide_down": "向下滑入",
    "slide_left": "向左滑入",
    "slide_right": "向右滑入",
    "flip": "侧身翻转",
    "rainbow": "七彩散光",
    "glow": "光晕",
    "light_scan": "光线扫描",
    "playful_spin": "俏皮旋入",
    "symphony_bounce": "交响弹动",
    "tyndall_light": "丁达尔光效",
}

# 텍스트 아웃트로 (TextOutro) — 버그 #15 수정
TEXT_OUTRO_ALIASES: dict[str, str] = {
    "fade_out": "渐隐",  # 버그 #15: 淡出 없음 → 渐隐
    "scale_down": "缩小",
    "slide_up": "向上滑出",
    "slide_down": "向下滑出",
    "slide_left": "向左滑出",
    "slide_right": "向右滑出",
    "disappear": "消失",
    "dissolve": "溶解",
}

# 텍스트 루프 (TextLoopAnim)
TEXT_LOOP_ANIM_ALIASES: dict[str, str] = {
    "heartbeat": "心跳",
    "shake": "抖动",
    "bounce": "弹跳",
    "pulse": "脉动",
    "wave": "波浪",
    "rainbow": "彩虹",
    "flash": "闪烁",
}

# 오디오 씬 효과 (AudioSceneEffectType)
AUDIO_SCENE_EFFECT_ALIASES: dict[str, str] = {
    "echo": "回声",
    "reverb": "混响",
    "concert_hall": "音乐厅",
    "telephone": "电话音效",
    "underwater": "水下",
    "robot": "机器人",
    "chipmunk": "花栗鼠",
    "bass_boost": "低音增强",
    "treble_boost": "高音增强",
    "bathroom": "浴室",
    "stadium": "体育馆",
}

# 비디오 캐릭터 효과 (VideoCharacterEffectType)
VIDEO_CHARACTER_EFFECT_ALIASES: dict[str, str] = {
    "face_reshape": "瘦脸",
    "slim_face": "瘦脸",
    "chin_slim": "下巴塑形",
    "nose_slim": "鼻子塑形",
    "big_eyes": "大眼",
    "eye_bright": "亮眼",
    "teeth_whiten": "美白牙齿",
    "smooth_skin": "磨皮",
    "lip_color": "口红",
    "eyebrow": "眉毛",
    "eyeliner": "眼线",
    "eye_shadow": "眼影",
    "contour": "修容",
    "forehead": "额头",
}

# 그룹 애니메이션 (GroupAnimationType)
GROUP_ANIMATION_ALIASES: dict[str, str] = {
    "zoom_in": "放大",
    "zoom_out": "缩小",
    "shake": "抖动",
    "heartbeat": "心跳",
    "rotate": "旋转",
    "bounce": "弹跳",
}

# 폰트 (FontType) — 대부분 폰트명 그대로
FONT_ALIASES: dict[str, str] = {
    "arial": "Arial",
    "helvetica": "Helvetica",
    "times": "Times New Roman",
    "times_new_roman": "Times New Roman",
    "courier": "Courier New",
    "courier_new": "Courier New",
    "comic_sans": "Comic Sans MS",
    "consolas": "Consolas",
    "georgia": "Georgia",
    "impact": "Impact",
    "roboto": "Roboto",
    "noto_sans": "Noto Sans",
    "noto_serif": "Noto Serif",
    "simhei": "SimHei",
    "simsun": "SimSun",
    "fangsong": "仿宋",
    "microsoft_yahei": "Microsoft YaHei",
    "jua": "Jua",
    "nanum_gothic": "NanumGothic",
    "nanum_myeongjo": "NanumMyeongjo",
}

# 마스크 (MaskType)
MASK_ALIASES: dict[str, str] = {
    "linear": "线性",
    "mirror": "镜面",
    "circle": "圆形",
    "rectangle": "矩形",
    "heart": "爱心",
    "star": "星形",
}


# =========================================================================
# Registry: enum 클래스 이름 → (pyCapCut enum, alias dict)
# =========================================================================

_ALIAS_REGISTRY: dict[str, tuple[Type[Enum], dict[str, str]]] = {
    "TransitionType": (cc.TransitionType, TRANSITION_ALIASES),
    "FilterType": (cc.FilterType, FILTER_ALIASES),
    "VideoSceneEffectType": (cc.VideoSceneEffectType, VIDEO_SCENE_EFFECT_ALIASES),
    "VideoCharacterEffectType": (cc.VideoCharacterEffectType, VIDEO_CHARACTER_EFFECT_ALIASES),
    "IntroType": (cc.IntroType, INTRO_ALIASES),
    "OutroType": (cc.OutroType, OUTRO_ALIASES),
    "GroupAnimationType": (cc.GroupAnimationType, GROUP_ANIMATION_ALIASES),
    "TextIntro": (cc.TextIntro, TEXT_INTRO_ALIASES),
    "TextOutro": (cc.TextOutro, TEXT_OUTRO_ALIASES),
    "TextLoopAnim": (cc.TextLoopAnim, TEXT_LOOP_ANIM_ALIASES),
    "AudioSceneEffectType": (cc.AudioSceneEffectType, AUDIO_SCENE_EFFECT_ALIASES),
    "FontType": (cc.FontType, FONT_ALIASES),
    "MaskType": (cc.MaskType, MASK_ALIASES),
}


# =========================================================================
# Public API
# =========================================================================


# enum 멤버 이름 set을 lazy 캐시 (매 resolve_alias 호출마다 순회 비용 제거)
_MEMBER_NAME_CACHE: dict[str, set[str]] = {}


def _members(enum_class_name: str) -> set[str]:
    cached = _MEMBER_NAME_CACHE.get(enum_class_name)
    if cached is None:
        enum_cls, _ = _ALIAS_REGISTRY[enum_class_name]
        cached = {m.name for m in enum_cls}
        _MEMBER_NAME_CACHE[enum_class_name] = cached
    return cached


def list_enum_classes() -> list[str]:
    """별칭을 지원하는 enum 카테고리 이름 목록."""
    return sorted(_ALIAS_REGISTRY)


def resolve_alias(enum_class_name: str, name_or_alias: str) -> str:
    """영어 별칭이나 원본 한자명을 실제 enum 멤버명으로 변환.

    동작 우선순위:
        1. 이미 enum 멤버로 존재하는 이름이면 그대로 반환
        2. 소문자로 내린 문자열이 alias 사전에 있으면 매핑 반환
        3. 제거된 언더스코어/공백 기준 느슨한 매칭
        4. 매칭 실패 시 KeyError

    Args:
        enum_class_name: "TransitionType", "FilterType" 등
        name_or_alias: 영문 alias 또는 한자 원본 이름

    Returns:
        실제 pyCapCut enum 멤버명 (문자열).
    """
    if enum_class_name not in _ALIAS_REGISTRY:
        raise KeyError(
            f"Unknown enum class: {enum_class_name}. "
            f"Use one of: {', '.join(list_enum_classes())}"
        )

    _, aliases = _ALIAS_REGISTRY[enum_class_name]
    member_names = _members(enum_class_name)

    # 1) 이미 실제 enum 이름
    if name_or_alias in member_names:
        return name_or_alias

    # 2) 정확 alias
    key = name_or_alias.lower().strip()
    if key in aliases:
        mapped = aliases[key]
        if mapped in member_names:
            return mapped

    # 3) 공백·언더스코어 무시 매칭 (alias 쪽)
    normalized = re.sub(r"[_\s\-]", "", key)
    for alias, chinese in aliases.items():
        if re.sub(r"[_\s\-]", "", alias) == normalized and chinese in member_names:
            return chinese

    # 4) 실패
    raise KeyError(
        f"No match for '{name_or_alias}' in {enum_class_name}. "
        f"Use 'alias search {enum_class_name} <keyword>' to find valid names."
    )


def reverse_alias(enum_class_name: str, chinese_name: str) -> str | None:
    """한자 enum 이름에서 영어 별칭 찾기 (여러 개면 첫 번째)."""
    if enum_class_name not in _ALIAS_REGISTRY:
        return None
    _, aliases = _ALIAS_REGISTRY[enum_class_name]
    for alias, chn in aliases.items():
        if chn == chinese_name:
            return alias
    return None


def reverse_alias_any(chinese_name: str) -> list[tuple[str, str]]:
    """모든 카테고리에서 한자명에 매칭되는 (enum_class, alias) 쌍."""
    hits: list[tuple[str, str]] = []
    for enum_class_name, (_, aliases) in _ALIAS_REGISTRY.items():
        for alias, chn in aliases.items():
            if chn == chinese_name:
                hits.append((enum_class_name, alias))
    return hits


def list_aliases(enum_class_name: str) -> dict[str, str]:
    """해당 카테고리의 영→한자 별칭 사전 반환 (사본)."""
    if enum_class_name not in _ALIAS_REGISTRY:
        raise KeyError(f"Unknown enum class: {enum_class_name}")
    return dict(_ALIAS_REGISTRY[enum_class_name][1])


def search_enum(enum_class_name: str, keyword: str, limit: int = 30) -> list[dict[str, Any]]:
    """특정 enum에서 키워드로 멤버 검색 (한자/영어 둘 다 처리).

    Returns:
        [{"name": "暗角", "alias": "vignette"}, ...] 리스트.
    """
    if enum_class_name not in _ALIAS_REGISTRY:
        raise KeyError(f"Unknown enum class: {enum_class_name}")
    enum_cls, aliases = _ALIAS_REGISTRY[enum_class_name]

    key_lower = keyword.lower().strip()
    reverse_lookup = {v: k for k, v in aliases.items()}

    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 영어 alias 매칭
    for alias, chn in aliases.items():
        if key_lower in alias.lower() and chn not in seen:
            hits.append({"name": chn, "alias": alias})
            seen.add(chn)

    # 한자 enum 이름에 직접 키워드 포함 (한자 일부 또는 영문)
    for member in enum_cls:
        if member.name in seen:
            continue
        if keyword in member.name or key_lower in member.name.lower():
            hits.append({"name": member.name, "alias": reverse_lookup.get(member.name)})
            seen.add(member.name)
            if len(hits) >= limit:
                break

    return hits[:limit]


def search_all_enums(keyword: str, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    """모든 enum 카테고리에서 키워드 검색."""
    results: dict[str, list[dict[str, Any]]] = {}
    for enum_class_name in list_enum_classes():
        found = search_enum(enum_class_name, keyword, limit)
        if found:
            results[enum_class_name] = found
    return results
