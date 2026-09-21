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

import os
import re
import struct
import unicodedata
from enum import Enum
from functools import lru_cache
from pathlib import Path
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
    # 흑백/반전
    "white_flash": "White_Flash",
    "black_flash": "闪黑",
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
    "zoom_in": "推近",
    "zoom_out": "拉远",
    # 와이프
    "wipe_left": "向左擦除",
    "wipe_right": "向右擦除",
    "wipe_up": "向上擦除",
    "wipe_down": "向下擦除",
    # 회전/3D
    "rotate": "旋转转场",
    "rotate_3d": "三维旋转",
    "3d_space": "_3D空间",
    "flip": "翻转",
    "flip_in": "翻转",
    # 블러
    "blur": "转场_模糊",
    # 분할
    "center_split": "居中分割",
    "split_h": "横向分割",
    "split_v": "竖向分割",
    # 기타
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
    "twilight": "暮光",
    # 스타일
    "film_grain": "Soft_Grain",
    # 흑백
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
    # 분위기
    "natural": "自然",
    "bright": "提亮",
}

# 비디오 씬 효과 (VideoSceneEffectType) — 버그 #12 정답
VIDEO_SCENE_EFFECT_ALIASES: dict[str, str] = {
    "vignette": "暗角",
    "soft": "柔光",
    "soft_light": "柔光",
    "glow": "光晕",
    "glitch": "故障",
    "chromatic": "色差",
    "chromatic_aberration": "色差",
    "blur": "模糊",
    "gaussian_blur": "模糊",
    "motion_blur": "动感模糊",
    "mosaic": "马赛克",
    "oil_paint": "油画",
    "old_film": "老电影_II",
    "heartbeat": "心跳",
    "shake": "抖动",
    "shake_v": "纵向抖动",
    "shake_vertical": "纵向抖动",
    "neon_glow": "霓虹光线",
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
    "rotate_in": "旋转进入",
    "rotate_in_up": "向上转入",
    "spin": "旋转进入",
    "drop_in": "Drop_down",
    "blur_open": "模糊渐显",
    "mc_explosion": "MC爆炸",
    "reverse": "反转回正",
    "tremble": "上下抖动",
}

# 비디오 아웃트로 (OutroType)
OUTRO_ALIASES: dict[str, str] = {
    "fade_out": "渐隐",
    "zoom_in": "放大",
    "zoom_out": "缩小",
    "slide_up": "向上滑动",
    "slide_down": "向下滑动",
    "slide_left": "向左滑动",
    "slide_right": "向右滑动",
    "rotate_out": "旋转出",
    "blur_out": "模糊渐隐",
}

# 텍스트 인트로 (TextIntro)
TEXT_INTRO_ALIASES: dict[str, str] = {
    "fade_in": "渐显",
    "karaoke": "卡拉OK",
    "typewriter": "打字机",
    "typewriter_i": "打字机_I",
    "typewriter_ii": "打字机_II",
    "bounce": "可爱悦动",
    "scale_up": "放大",
    "slide_up": "向上滑动",
    "slide_down": "向下滑动",
    "slide_left": "向左滑动",
    "slide_right": "向右滑动",
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
    "slide_up": "向上滑动",
    "slide_down": "向下滑动",
    "slide_left": "向左滑动",
    "slide_right": "向右滑动",
    "disappear": "消散",
    "dissolve": "溶解_出场",
}

# 텍스트 루프 (TextLoopAnim)
TEXT_LOOP_ANIM_ALIASES: dict[str, str] = {
    "heartbeat": "心跳",
    "shake": "晃动",
    "wave": "波浪",
    "flash": "闪烁",
}

# 오디오 씬 효과 (AudioSceneEffectType)
AUDIO_SCENE_EFFECT_ALIASES: dict[str, str] = {
    "echo": "回音",
    "concert_hall": "音乐厅",
    "telephone": "电话",
    "underwater": "水下",
    "robot": "机器人",
    "chipmunk": "花栗鼠",
    "bass_boost": "低音增强",
    "treble_boost": "高音增强",
    "bathroom": "浴室",
}

# 비디오 캐릭터 효과 (VideoCharacterEffectType)
VIDEO_CHARACTER_EFFECT_ALIASES: dict[str, str] = {}

# 그룹 애니메이션 (GroupAnimationType)
GROUP_ANIMATION_ALIASES: dict[str, str] = {
    "rotate": "转圈圈",
}

# 폰트 (FontType)


def normalize_font_alias(name: str) -> str:
    """폰트/enum 이름을 소문자 snake_case 별칭으로 정규화."""
    normalized = unicodedata.normalize("NFKC", name).casefold().strip()
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE)
    return re.sub(r"_+", "_", normalized).strip("_")


def _font_name_aliases(name: str) -> tuple[str, ...]:
    """원래 표기와 CamelCase를 나눈 표기에서 폰트 별칭을 생성."""
    normalized = unicodedata.normalize("NFKC", name).strip()
    camel_separated = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        normalized,
    )
    return tuple(
        sorted(
            {
                alias
                for candidate in (normalized, camel_separated)
                if (alias := normalize_font_alias(candidate))
            }
        )
    )


def _build_bundled_font_aliases() -> dict[str, str]:
    """설치된 pycapcut FontType 전체에서 번들 별칭을 기계적으로 생성."""
    aliases: dict[str, str] = {}
    for member in cc.FontType:
        alias = normalize_font_alias(member.name)
        if not alias or alias in aliases:
            raise RuntimeError(f"FontType 별칭 정규화 충돌: {member.name!r} -> {alias!r}")
        aliases[alias] = member.name
    return aliases


_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}


def _font_scan_locations() -> tuple[Path, Path, Path, Path]:
    """실행 시점 환경에서 CapCut 캐시/SystemFont/사용자/Windows Fonts 경로를 계산."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    windows_root = Path(os.environ.get("WINDIR", "C:/Windows"))
    capcut_root = local_app_data / "CapCut" / "User Data"
    return (
        capcut_root / "Cache" / "effect",
        capcut_root / "Resources" / "Font" / "SystemFont",
        local_app_data / "Microsoft" / "Windows" / "Fonts",
        windows_root / "Fonts",
    )


def _font_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.casefold() in _FONT_SUFFIXES
        ),
        key=lambda path: str(path).casefold(),
    )


def _sfnt_offsets(data: bytes) -> tuple[int, ...]:
    """단일 SFNT와 TTC 컬렉션의 각 face 시작 오프셋을 반환."""
    if data[:4] != b"ttcf":
        return (0,)
    if len(data) < 12:
        return ()
    font_count = struct.unpack_from(">I", data, 8)[0]
    offsets_end = 12 + font_count * 4
    if offsets_end > len(data):
        return ()
    return tuple(struct.unpack_from(">I", data, 12 + index * 4)[0] for index in range(font_count))


def _sfnt_tables(data: bytes, sfnt_offset: int = 0) -> dict[bytes, tuple[int, int]]:
    """TTF의 SFNT 테이블 디렉터리를 최소 파싱."""
    if sfnt_offset < 0 or sfnt_offset + 12 > len(data):
        return {}
    table_count = struct.unpack_from(">H", data, sfnt_offset + 4)[0]
    tables: dict[bytes, tuple[int, int]] = {}
    for index in range(table_count):
        record_offset = sfnt_offset + 12 + index * 16
        if record_offset + 16 > len(data):
            return {}
        tag, _, offset, length = struct.unpack_from(">4sIII", data, record_offset)
        if offset <= len(data) and length <= len(data) - offset:
            tables[tag] = (offset, length)
    return tables


def _has_hangul_cmap(data: bytes, table: tuple[int, int]) -> bool:
    """cmap에 한글 자모 또는 완성형 한글 범위가 하나라도 있는지 확인."""
    cmap_offset, cmap_length = table
    if cmap_length < 4:
        return False
    table_count = struct.unpack_from(">H", data, cmap_offset + 2)[0]
    ranges = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7A3))

    for index in range(table_count):
        record_offset = cmap_offset + 4 + index * 8
        if record_offset + 8 > cmap_offset + cmap_length:
            break
        _, _, relative_offset = struct.unpack_from(">HHI", data, record_offset)
        subtable_offset = cmap_offset + relative_offset
        if subtable_offset + 2 > len(data):
            continue
        fmt = struct.unpack_from(">H", data, subtable_offset)[0]

        if fmt == 4 and subtable_offset + 14 <= len(data):
            subtable_length = struct.unpack_from(">H", data, subtable_offset + 2)[0]
            subtable_end = min(subtable_offset + subtable_length, len(data))
            segment_count = struct.unpack_from(">H", data, subtable_offset + 6)[0] // 2
            ends_offset = subtable_offset + 14
            starts_offset = ends_offset + segment_count * 2 + 2
            if starts_offset + segment_count * 2 > subtable_end:
                continue
            for segment in range(segment_count):
                end = struct.unpack_from(">H", data, ends_offset + segment * 2)[0]
                start = struct.unpack_from(">H", data, starts_offset + segment * 2)[0]
                if any(start <= range_end and end >= range_start for range_start, range_end in ranges):
                    return True

        if fmt == 12 and subtable_offset + 16 <= len(data):
            group_count = struct.unpack_from(">I", data, subtable_offset + 12)[0]
            groups_offset = subtable_offset + 16
            if groups_offset + group_count * 12 > len(data):
                continue
            for group in range(group_count):
                start, end, _ = struct.unpack_from(">III", data, groups_offset + group * 12)
                if any(start <= range_end and end >= range_start for range_start, range_end in ranges):
                    return True
    return False


def _decode_name(platform_id: int, raw: bytes) -> str | None:
    try:
        if platform_id in (0, 3):
            return raw.decode("utf-16-be").strip("\x00 ")
        if platform_id == 1:
            return raw.decode("mac_roman").strip("\x00 ")
    except (UnicodeDecodeError, LookupError):
        return None
    return None


def _font_names(
    data: bytes,
    table: tuple[int, int],
    tables: dict[bytes, tuple[int, int]],
) -> tuple[str, str] | None:
    """TTF name 테이블에서 대표 family/subfamily 이름을 선택."""
    name_offset, name_length = table
    if name_length < 6:
        return None
    record_count, strings_offset = struct.unpack_from(">HH", data, name_offset + 2)
    records_end = name_offset + 6 + record_count * 12
    if records_end > name_offset + name_length:
        return None

    names: dict[int, list[tuple[int, str]]] = {1: [], 2: [], 16: [], 17: []}
    for index in range(record_count):
        record_offset = name_offset + 6 + index * 12
        platform_id, _, language_id, name_id, length, offset = struct.unpack_from(
            ">HHHHHH", data, record_offset
        )
        if name_id not in names:
            continue
        value_offset = name_offset + strings_offset + offset
        value_end = value_offset + length
        if value_offset < name_offset or value_end > name_offset + name_length:
            continue
        value = _decode_name(platform_id, data[value_offset:value_end])
        if not value:
            continue
        score = 0
        if platform_id == 3:
            score += 4
        if language_id in (0, 0x0409):
            score += 2
        if value.isascii():
            score += 1
        names[name_id].append((score, value))

    def best(name_id: int) -> str | None:
        choices = names[name_id]
        return max(choices, key=lambda item: item[0])[1] if choices else None

    # 가변 폰트는 preferred subfamily가 축의 최소값일 수 있으므로 legacy 이름 사용.
    is_variable = b"fvar" in tables
    family = best(1) if is_variable else (best(16) or best(1))
    subfamily = best(2) if is_variable else (best(17) or best(2) or "Regular")
    if not family:
        return None
    return family, subfamily or "Regular"


@lru_cache(maxsize=4096)
def _cached_font_file_aliases(
    path_text: str,
    modified_ns: int,
    size: int,
    require_hangul: bool,
) -> tuple[str, ...]:
    """변경되지 않은 폰트의 메타데이터 파싱 결과를 재사용."""
    del modified_ns, size
    path = Path(path_text)
    aliases: set[str] = set()
    stem_aliases = _font_name_aliases(path.stem)
    if not require_hangul:
        aliases.update(stem_aliases)

    try:
        data = path.read_bytes()
    except OSError:
        return ()

    has_usable_face = False
    for sfnt_offset in _sfnt_offsets(data):
        tables = _sfnt_tables(data, sfnt_offset)
        if b"name" not in tables or b"cmap" not in tables:
            continue
        if require_hangul and not _has_hangul_cmap(data, tables[b"cmap"]):
            continue
        has_usable_face = True
        names = _font_names(data, tables[b"name"], tables)
        if names is None:
            continue
        family, subfamily = names
        for family_alias in _font_name_aliases(family):
            aliases.add(family_alias)
            for subfamily_alias in _font_name_aliases(subfamily):
                if subfamily_alias in {"regular", "normal", "roman"}:
                    continue
                suffix = f"_{subfamily_alias}"
                styled_alias = family_alias
                if not styled_alias.endswith(suffix):
                    styled_alias += suffix
                aliases.add(styled_alias)

    if require_hangul:
        if not has_usable_face:
            return ()
        aliases.update(stem_aliases)
    return tuple(sorted(aliases))


def _font_file_aliases(path: Path, *, require_hangul: bool) -> tuple[str, ...]:
    """폰트 파일의 stem/family/subfamily 별칭을 추출."""
    try:
        stat = path.stat()
    except OSError:
        return ()
    return _cached_font_file_aliases(
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        require_hangul,
    )


def discover_local_font_aliases(
    font_directories: tuple[Path, ...] | None = None,
) -> dict[str, str]:
    """사용자/Windows Fonts에서 한글 cmap을 가진 실존 폰트만 등록."""
    aliases: dict[str, str] = {}
    directories = font_directories or _font_scan_locations()[2:]
    for directory in directories:
        for path in _font_files(directory):
            resolved = path.resolve().as_posix()
            for alias in _font_file_aliases(path, require_hangul=True):
                aliases.setdefault(alias, resolved)
    return aliases


FONT_ALIASES: dict[str, str] = _build_bundled_font_aliases()
BUNDLED_FONT_ALIASES = FONT_ALIASES
LOCAL_FONT_ALIASES: dict[str, str] = {}


def _bundled_aliases_by_resource_id() -> dict[str, list[str]]:
    aliases_by_id: dict[str, list[str]] = {}
    for alias, member_name in BUNDLED_FONT_ALIASES.items():
        resource_id = str(cc.FontType[member_name].value.resource_id or "")
        if resource_id:
            aliases_by_id.setdefault(resource_id, []).append(alias)
    return aliases_by_id


@lru_cache(maxsize=32)
def _discover_available_fonts_at(
    cache_dir_text: str,
    system_font_dir_text: str,
    user_font_dir_text: str,
    windows_font_dir_text: str,
) -> dict[str, dict[str, str]]:
    """한 실행 환경의 네 로컬 위치를 한 번 스캔해 별칭을 구성."""
    cache_dir = Path(cache_dir_text)
    system_font_dir = Path(system_font_dir_text)
    user_font_dir = Path(user_font_dir_text)
    windows_font_dir = Path(windows_font_dir_text)
    available: dict[str, dict[str, str]] = {}
    bundled_by_id = _bundled_aliases_by_resource_id()

    def register(alias: str, path: Path, resource_id: str) -> None:
        key = normalize_font_alias(alias)
        if not key:
            return
        available.setdefault(
            key,
            {
                "font_path": path.resolve().as_posix(),
                "font_resource_id": resource_id,
            },
        )

    # 1) 다운로드한 CapCut 폰트. effect 바로 아래 폴더명이 resource_id다.
    for path in _font_files(cache_dir):
        try:
            relative_parts = path.relative_to(cache_dir).parts
        except ValueError:
            continue
        if not relative_parts:
            continue
        resource_id = relative_parts[0]
        for alias in bundled_by_id.get(resource_id, []):
            register(alias, path, resource_id)
        for alias in _font_file_aliases(path, require_hangul=False):
            register(alias, path, resource_id)

    # 2) CapCut 기본 SystemFont. resource_id는 존재하지 않는다.
    for path in _font_files(system_font_dir):
        for alias in _font_file_aliases(path, require_hangul=False):
            register(alias, path, "")

    # 3) 사용자 Fonts. 현재 계정이 명시적으로 설치한 버전을 우선하기 위해
    # Windows Fonts보다 먼저 등록한다. register()의 setdefault가 중복 별칭을 막는다.
    for path in _font_files(user_font_dir):
        for alias in _font_file_aliases(path, require_hangul=True):
            register(alias, path, "")

    # 4) Windows Fonts. 사용자 폰트와 동일하게 한글 cmap 파일만 등록한다.
    for path in _font_files(windows_font_dir):
        for alias in _font_file_aliases(path, require_hangul=True):
            register(alias, path, "")

    return available


def _discover_available_fonts() -> dict[str, dict[str, str]]:
    """현재 실행 시점 환경의 네 로컬 폰트 위치를 스캔."""
    locations = _font_scan_locations()
    return _discover_available_fonts_at(*(str(path.resolve()) for path in locations))


def _unique_token_match(
    key: str,
    available: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """번들 별칭 토큰과 일치하는 로컬 파일이 하나뿐일 때만 선택."""
    key_tokens = tuple(token for token in key.split("_") if token)
    if not key_tokens:
        return None
    matches: dict[tuple[str, str], dict[str, str]] = {}
    for alias, resolved in available.items():
        alias_tokens = tuple(token for token in alias.split("_") if token)
        width = len(key_tokens)
        if any(
            alias_tokens[index:index + width] == key_tokens
            for index in range(len(alias_tokens) - width + 1)
        ):
            match_key = (resolved["font_path"], resolved["font_resource_id"])
            matches[match_key] = resolved
    if len(matches) == 1:
        return dict(next(iter(matches.values())))
    return None


def resolve_font(name_or_alias: str) -> dict[str, str]:
    """별칭을 이 PC에 존재하는 폰트 파일 경로와 resource_id로 해석."""
    key = normalize_font_alias(name_or_alias)
    available = _discover_available_fonts()
    LOCAL_FONT_ALIASES.clear()
    LOCAL_FONT_ALIASES.update(
        {alias: resolved["font_path"] for alias, resolved in available.items()}
    )
    resolved = available.get(key)
    if resolved is not None and Path(resolved["font_path"]).is_file():
        return dict(resolved)

    if key in BUNDLED_FONT_ALIASES:
        token_match = _unique_token_match(key, available)
        if token_match is not None and Path(token_match["font_path"]).is_file():
            return token_match
        raise KeyError(
            f"CapCut에 아직 다운로드되지 않은 폰트입니다: '{name_or_alias}'. "
            "CapCut에서 한 번 사용하면 캐시에 받아진 뒤 쓸 수 있습니다."
        )

    raise KeyError(
        f"알 수 없거나 이 PC에서 폰트 파일을 찾을 수 없습니다: '{name_or_alias}'. "
        "CapCut 캐시, CapCut SystemFont 또는 사용자/Windows Fonts의 로컬 별칭을 사용하세요."
    )

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
