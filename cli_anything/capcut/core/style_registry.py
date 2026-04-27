"""스타일 프리셋 레지스트리 (v0.4.1: 카테고리 text/video/audio).

자막/텍스트·비디오·오디오 스타일을 카테고리로 분리해 이름으로 저장·재사용.
저장소는 ``~/.capcut_cli/styles.json`` (JSON, 의존성 없음).

스키마::

    {
      "text": {
        "my-sub": { "font": "...", "size": 6.0, ... }
      },
      "video": {
        "cinematic-warm": {
          "filter": {"name": "cinematic", "intensity": 40},
          "animation_intro": {"name": "fade_in", "duration": "0.5s"},
          "animation_outro": {"name": "fade_out", "duration": "0.5s"},
          "color": {"brightness": 5, "contrast": 10}
        }
      },
      "audio": {
        "podcast-voice": {
          "volume": 0.9, "fade_in": "0.3s", "fade_out": "0.5s",
          "effect": {"name": "noise-reduction"}
        }
      }
    }

v0.4.0 이전의 플랫 스키마 (``{"my-sub": {...}}``) 는 로드 시 자동으로
``{"text": {"my-sub": {...}}}`` 로 마이그레이션.

사용자 저장 프리셋은 파일에, 내장 프리셋은 ``builtin_styles()`` 에.
``list_styles()`` 는 두 곳을 합쳐 보여줌.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

__all__ = [
    "STYLE_FILE",
    "CATEGORIES",
    "load_styles",
    "save_style",
    "get_style",
    "delete_style",
    "list_styles",
    "builtin_styles",
    "merge_style_with_overrides",
    "apply_video_style",
    "apply_audio_style",
]


STYLE_FILE: Path = Path.home() / ".capcut_cli" / "styles.json"

# 스타일 이름 유효성. 알파벳/숫자/하이픈/언더스코어만.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")

CATEGORIES: tuple[str, ...] = ("text", "video", "audio")


# =========================================================================
# 내장 프리셋 (카테고리별)
# =========================================================================


_BUILTIN: dict[str, dict[str, dict]] = {
    "text": {
        "lifestyle-brand": {
            "font": "GothicA1-Bold",
            "size": 6.0,
            "bold": True,
            "color": [1.0, 1.0, 1.0],
            "border": {"alpha": 0.9, "color": [13, 13, 38], "width": 0.08},
            "shadow": None,
            "clip_settings": {"transform_x": 0.0, "transform_y": -0.75},
            "align": "center",
            "_builtin": True,
            "_description": "브랜드 자막 — 흰색 고딕, 네이비 테두리, 하단",
        },
        "youtube-subtitle": {
            "font": "arial",
            "size": 5.0,
            "bold": True,
            "color": [1.0, 1.0, 1.0],
            "border": {"alpha": 1.0, "color": [0, 0, 0], "width": 0.06},
            "shadow": None,
            "clip_settings": {"transform_x": 0.0, "transform_y": -0.75},
            "align": "center",
            "_builtin": True,
            "_description": "유튜브 표준 자막 — 흰 Arial bold + 검정 테두리",
        },
        "news-title": {
            "font": "GothicA1-Bold",
            "size": 6.5,
            "bold": True,
            "color": [1.0, 1.0, 1.0],
            "border": {"alpha": 1.0, "color": [200, 30, 30], "width": 0.10},
            "shadow": {"alpha": 0.8, "color": [0, 0, 0], "distance": 6, "angle": 315},
            "clip_settings": {"transform_x": 0.0, "transform_y": 0.55},
            "align": "center",
            "_builtin": True,
            "_description": "뉴스 로어서드 — 빨간 테두리로 헤드라인 느낌",
        },
        "minimal-caption": {
            "font": "arial",
            "size": 4.5,
            "bold": False,
            "color": [1.0, 1.0, 1.0],
            "border": None,
            "shadow": {"alpha": 0.7, "color": [0, 0, 0], "distance": 4, "angle": 315},
            "clip_settings": {"transform_x": 0.0, "transform_y": -0.75},
            "align": "center",
            "_builtin": True,
            "_description": "미니멀 캡션 — 테두리 없이 은은한 그림자만",
        },
        "cinematic": {
            "font": "serif",
            "size": 5.0,
            "bold": False,
            "color": [1.0, 1.0, 1.0],
            "border": None,
            "shadow": {"alpha": 0.5, "color": [0, 0, 0], "distance": 3, "angle": 315},
            "clip_settings": {"transform_x": 0.0, "transform_y": 0.65},
            "align": "center",
            "letter_spacing": 0.12,
            "_builtin": True,
            "_description": "시네마틱 — serif, 옅은 그림자, 중앙 상단",
        },
    },
    "video": {
        "cinematic-warm": {
            "filter": {"name": "cinematic", "intensity": 40},
            "animation_intro": {"name": "fade_in", "duration": "0.5s"},
            "animation_outro": {"name": "fade_out", "duration": "0.5s"},
            "color": {"brightness": 5, "contrast": 10, "temperature": 15},
            "_builtin": True,
            "_description": "따뜻한 시네마틱 룩 — 필터 + 페이드 + 따뜻한 색온도",
        },
        "social-punchy": {
            "filter": {"name": "vivid", "intensity": 60},
            "animation_intro": {"name": "zoom_in", "duration": "0.3s"},
            "color": {"saturation": 15, "contrast": 10},
            "_builtin": True,
            "_description": "SNS 숏폼 — 강렬한 비비드 필터 + 빠른 줌인",
        },
        "corporate-clean": {
            "color": {"brightness": 3, "contrast": 5},
            "_builtin": True,
            "_description": "코퍼레이트 — 밝기/대비만 살짝, 깔끔 유지",
        },
    },
    "audio": {
        "podcast-voice": {
            "volume": 0.9,
            "fade_in": "0.3s",
            "fade_out": "0.5s",
            "effect": {"name": "noise-reduction"},
            "_builtin": True,
            "_description": "팟캐스트 보이스 — 잡음 제거 + 짧은 페이드",
        },
        "bgm-background": {
            "volume": 0.3,
            "fade_in": "1s",
            "fade_out": "2s",
            "_builtin": True,
            "_description": "배경 BGM — 낮은 볼륨 + 긴 페이드",
        },
        "sfx-short": {
            "volume": 1.0,
            "fade_in": "0s",
            "fade_out": "0.1s",
            "_builtin": True,
            "_description": "짧은 효과음 — 풀 볼륨, 끝에만 살짝 페이드",
        },
    },
}


def builtin_styles(category: str | None = None) -> dict:
    """내장 프리셋 반환 (깊은 복사). 호출자가 자유롭게 mutate 해도 안전.

    - ``category=None`` → 전체를 ``{category: {name: spec}}`` 형태로 반환.
    - 카테고리 지정 시 해당 카테고리만 ``{name: spec}``.
    """
    if category is None:
        return {c: {n: deepcopy(s) for n, s in specs.items()}
                for c, specs in _BUILTIN.items()}
    _validate_category(category)
    return {n: deepcopy(s) for n, s in _BUILTIN.get(category, {}).items()}


# =========================================================================
# 파일 I/O
# =========================================================================


def _ensure_dir() -> None:
    STYLE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _empty_store() -> dict[str, dict]:
    return {c: {} for c in CATEGORIES}


def _is_category_schema(data: dict) -> bool:
    """v0.4.1 스키마 감지 — 최상위 키가 카테고리명들 중 하나라도면 OK."""
    if not isinstance(data, dict) or not data:
        return False
    # 모든 키가 카테고리 중 하나이면 새 스키마
    return all(k in CATEGORIES for k in data.keys())


def _migrate_flat_schema(data: dict) -> dict[str, dict]:
    """v0.4.0 플랫 스키마 → v0.4.1 카테고리 스키마.

    플랫 엔트리는 모두 ``text`` 로 이동.
    """
    store = _empty_store()
    for name, spec in data.items():
        if isinstance(name, str) and isinstance(spec, dict):
            store["text"][name] = spec
    return store


def _load_store() -> dict[str, dict]:
    """파일에서 v0.4.1 스키마를 읽어옴. 플랫 스키마는 자동 마이그레이션.

    반환은 항상 ``{category: {name: spec}}`` 모양.
    """
    if not STYLE_FILE.exists():
        return _empty_store()
    try:
        raw = STYLE_FILE.read_text(encoding="utf-8")
    except OSError:
        return _empty_store()
    if not raw.strip():
        return _empty_store()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()

    if _is_category_schema(data):
        store = _empty_store()
        for c in CATEGORIES:
            section = data.get(c, {})
            if isinstance(section, dict):
                store[c] = {
                    k: v for k, v in section.items()
                    if isinstance(k, str) and isinstance(v, dict)
                }
        return store

    # 플랫 스키마 → 텍스트로 이동
    return _migrate_flat_schema(data)


def load_styles(category: str | None = None) -> dict[str, dict]:
    """사용자 저장 스타일 반환 (내장 제외).

    - ``category=None`` → 전체: ``{category: {name: spec}}`` 형태.
    - 카테고리 지정 시 ``{name: spec}`` 형태.
    """
    store = _load_store()
    if category is None:
        return store
    _validate_category(category)
    return store.get(category, {})


def _write_store(store: dict[str, dict]) -> None:
    _ensure_dir()
    STYLE_FILE.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            f"스타일 이름 유효하지 않음: {name!r}. "
            "영문/숫자/'-'/'_' 만, 1~64자, 첫 글자는 영숫자."
        )


def _validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError(
            f"알 수 없는 카테고리: {category!r}. "
            f"허용된 값: {', '.join(CATEGORIES)}"
        )


# =========================================================================
# CRUD
# =========================================================================


def save_style(
    name: str, spec: dict, *, category: str = "text", overwrite: bool = False,
) -> dict:
    """스타일 저장. 내장과 동일한 이름/카테고리는 거부 (혼동 방지).

    반환: 저장된 spec (복사본).
    """
    _validate_name(name)
    _validate_category(category)
    if name in _BUILTIN.get(category, {}):
        raise ValueError(
            f"'{name}' 은 내장 {category} 프리셋 이름. "
            "다른 이름을 쓰거나 먼저 builtin을 피해줘."
        )
    if not isinstance(spec, dict):
        raise ValueError(f"spec 은 dict 여야 함. 받은 타입: {type(spec).__name__}")

    store = _load_store()
    section = store.setdefault(category, {})
    if name in section and not overwrite:
        raise ValueError(f"'{name}' (카테고리 {category}) 이미 존재. --overwrite 로 덮어쓰기.")

    # 저장 전 정규화 — _builtin 같은 내부 마커 제거
    clean = {k: v for k, v in spec.items() if not k.startswith("_")}
    section[name] = clean
    _write_store(store)
    return deepcopy(clean)


def get_style(name: str, category: str = "text") -> dict:
    """사용자 저장 → 내장 순으로 조회. 없으면 KeyError."""
    if not isinstance(name, str) or not name:
        raise KeyError(name)
    _validate_category(category)
    user = load_styles(category)
    if name in user:
        return deepcopy(user[name])
    if name in _BUILTIN.get(category, {}):
        return deepcopy(_BUILTIN[category][name])
    raise KeyError(name)


def delete_style(name: str, category: str = "text") -> bool:
    """사용자 저장만 삭제. 내장은 삭제 불가 (False 반환).

    반환: 삭제 성공 True, 없거나 내장이면 False.
    """
    _validate_category(category)
    if name in _BUILTIN.get(category, {}):
        return False
    store = _load_store()
    section = store.get(category, {})
    if name not in section:
        return False
    del section[name]
    store[category] = section
    _write_store(store)
    return True


def _summary_text(name: str, spec: dict, *, builtin: bool) -> dict:
    return {
        "name": name,
        "category": "text",
        "font": spec.get("font"),
        "size": spec.get("size"),
        "color": spec.get("color"),
        "clip_settings": spec.get("clip_settings"),
        "builtin": builtin,
        "description": spec.get("_description"),
    }


def _summary_video(name: str, spec: dict, *, builtin: bool) -> dict:
    filt = spec.get("filter") or {}
    return {
        "name": name,
        "category": "video",
        "filter": filt.get("name") if isinstance(filt, dict) else None,
        "intro": (spec.get("animation_intro") or {}).get("name")
                 if isinstance(spec.get("animation_intro"), dict) else None,
        "outro": (spec.get("animation_outro") or {}).get("name")
                 if isinstance(spec.get("animation_outro"), dict) else None,
        "has_color": bool(spec.get("color")),
        "builtin": builtin,
        "description": spec.get("_description"),
    }


def _summary_audio(name: str, spec: dict, *, builtin: bool) -> dict:
    eff = spec.get("effect") or {}
    return {
        "name": name,
        "category": "audio",
        "volume": spec.get("volume"),
        "fade_in": spec.get("fade_in"),
        "fade_out": spec.get("fade_out"),
        "effect": eff.get("name") if isinstance(eff, dict) else None,
        "builtin": builtin,
        "description": spec.get("_description"),
    }


_SUMMARY_BUILDERS = {
    "text": _summary_text,
    "video": _summary_video,
    "audio": _summary_audio,
}


def list_styles(category: str | None = None) -> list[dict]:
    """내장 + 사용자 저장. 같은 이름이면 사용자 쪽이 표시됨.

    - ``category=None`` → 모든 카테고리 전체.
    - 카테고리 지정 시 해당 카테고리만.

    반환: 각 스타일 요약 dict 의 리스트, (category, name) 기준 정렬.
    """
    if category is not None:
        _validate_category(category)

    categories = (category,) if category else CATEGORIES
    rows: list[dict] = []
    user_all = _load_store()
    for c in categories:
        merged: dict[str, tuple[dict, bool]] = {}
        for name, spec in _BUILTIN.get(c, {}).items():
            merged[name] = (spec, True)
        for name, spec in user_all.get(c, {}).items():
            merged[name] = (spec, False)
        builder = _SUMMARY_BUILDERS[c]
        for n, (s, b) in sorted(merged.items()):
            rows.append(builder(n, s, builtin=b))
    return rows


# =========================================================================
# Merge
# =========================================================================


def merge_style_with_overrides(
    style_name: str | None, overrides: dict[str, Any], *, category: str = "text",
) -> dict[str, Any]:
    """style 있으면 불러와서 overrides로 덮어쓰기. 없으면 overrides 그대로.

    - overrides 의 None 값은 "미지정" 으로 간주해 base 를 덮지 않음
      (click 이 명시되지 않은 옵션에 None 주는 동작 고려).
    - overrides 의 dict 는 얕은 머지가 아니라 그대로 교체
      (예: ``--border '{...}'`` 통째로 바꾸는 게 의도).
    """
    base: dict[str, Any] = {}
    if style_name:
        base = get_style(style_name, category=category)  # KeyError 가능
        base = {k: v for k, v in base.items() if not k.startswith("_")}

    if not overrides:
        return deepcopy(base)

    merged = deepcopy(base)
    for k, v in overrides.items():
        if v is None:
            continue
        merged[k] = deepcopy(v)
    return merged


# =========================================================================
# Video/Audio 스타일 일괄 적용
# =========================================================================


def _snapshot_ops(session: Any) -> list[str]:
    """Session 의 현재 op id 리스트 스냅샷 (복구 마커용)."""
    return [o.get("id") for o in session.data.get("operations", [])]


def _rollback_to(session: Any, snapshot_ids: list[str]) -> None:
    """snapshot 이후 추가된 op 들을 제거 (undo 대신 직접)."""
    ops = session.data.get("operations", [])
    snap_set = set(snapshot_ids)
    keep = [o for o in ops if o.get("id") in snap_set]
    session.data["operations"] = keep
    # 저장 반영
    if hasattr(session, "_auto_save"):
        session._auto_save()


def apply_video_style(
    session: Any,
    track: str,
    segment_ref: str,
    style_name: str,
    *,
    user_overrides: dict | None = None,
) -> list[dict]:
    """비디오 스타일 프리셋을 세그먼트에 일괄 적용.

    내부 동작:
      - ``filter`` → ``add_filter`` (트랙 이름은 CapCut 필터 트랙이 필요해서
        ``track`` 과 동일하게 사용. 필터 트랙이 따로 있는 경우 사용자가
        track 을 명시)
      - ``animation_intro`` / ``animation_outro`` → ``add_video_animation``
      - ``color`` → ``color_adjust`` (postprocess queued)

    실패 시 이 함수 호출 전 스냅샷으로 롤백.
    """
    spec = get_style(style_name, category="video")
    spec = {k: v for k, v in spec.items() if not k.startswith("_")}
    if user_overrides:
        for k, v in user_overrides.items():
            if v is not None:
                spec[k] = v

    # 세그먼트 실제 시작/길이는 ScriptFile 에 있지만 여기서는 current session
    # operations 만 다룸. animation/filter 는 segment_ref 가 있으면 핸들러가
    # 해당 세그먼트에 붙이므로 문제 없음. add_filter 는 별도 filter 트랙
    # 세그먼트라 start/duration 이 필요 — 원본 세그먼트의 start/duration 을
    # session ops 에서 찾아 사용.
    orig = _find_segment_op(session, segment_ref)

    snapshot = _snapshot_ops(session)
    appended: list[dict] = []
    try:
        with session.batch():
            filt = spec.get("filter")
            if isinstance(filt, dict) and filt.get("name"):
                args = {
                    "name": filt["name"],
                    "track": track,
                    "intensity": filt.get("intensity"),
                }
                if orig:
                    args["start"] = orig.get("args", {}).get("start")
                    args["duration"] = orig.get("args", {}).get("duration")
                appended.append(session.append_operation("add_filter", args))

            intro = spec.get("animation_intro")
            if isinstance(intro, dict) and intro.get("name"):
                appended.append(session.append_operation(
                    "add_video_animation",
                    {
                        "track": track,
                        "segment_ref": segment_ref,
                        "role": "intro",
                        "name": intro["name"],
                        "duration": intro.get("duration", "500ms"),
                    },
                ))

            outro = spec.get("animation_outro")
            if isinstance(outro, dict) and outro.get("name"):
                appended.append(session.append_operation(
                    "add_video_animation",
                    {
                        "track": track,
                        "segment_ref": segment_ref,
                        "role": "outro",
                        "name": outro["name"],
                        "duration": outro.get("duration", "500ms"),
                    },
                ))

            color = spec.get("color")
            if isinstance(color, dict) and color:
                color_args = {"track": track, "segment_ref": segment_ref}
                for k in ("brightness", "contrast", "saturation",
                          "temperature", "highlights", "shadows", "vibrance"):
                    if k in color and color[k] is not None:
                        color_args[k] = color[k]
                appended.append(session.append_operation(
                    "color_adjust", color_args, _status="queued",
                ))
    except Exception:
        _rollback_to(session, snapshot)
        raise

    return appended


def apply_audio_style(
    session: Any,
    track: str,
    segment_ref: str,
    style_name: str,
    *,
    user_overrides: dict | None = None,
) -> list[dict]:
    """오디오 스타일 프리셋을 세그먼트에 일괄 적용.

    내부 동작:
      - ``volume`` → 원본 세그먼트의 args.volume 을 edit (or no-op)
        * 단순화: 새 op 추가 대신 기존 add_audio 의 volume 값을 교체.
          이유: CapCut 에는 "set volume" 단독 op 가 없음.
      - ``fade_in``/``fade_out`` → ``add_audio_fade``
      - ``effect`` → ``add_audio_effect``
    """
    spec = get_style(style_name, category="audio")
    spec = {k: v for k, v in spec.items() if not k.startswith("_")}
    if user_overrides:
        for k, v in user_overrides.items():
            if v is not None:
                spec[k] = v

    snapshot = _snapshot_ops(session)
    appended: list[dict] = []
    try:
        with session.batch():
            # 1) volume — 원본 audio op 의 args.volume 갱신
            volume = spec.get("volume")
            if volume is not None:
                _patch_segment_volume(session, segment_ref, float(volume))

            # 2) fade
            fi = spec.get("fade_in")
            fo = spec.get("fade_out")
            if fi is not None or fo is not None:
                appended.append(session.append_operation(
                    "add_audio_fade",
                    {
                        "track": track,
                        "segment_ref": segment_ref,
                        "fade_in": fi if fi is not None else "0s",
                        "fade_out": fo if fo is not None else "0s",
                    },
                ))

            # 3) effect
            effect = spec.get("effect")
            if isinstance(effect, dict) and effect.get("name"):
                appended.append(session.append_operation(
                    "add_audio_effect",
                    {
                        "track": track,
                        "segment_ref": segment_ref,
                        "name": effect["name"],
                    },
                ))
    except Exception:
        _rollback_to(session, snapshot)
        raise

    return appended


def _find_segment_op(session: Any, op_id: str) -> dict | None:
    """session.data.operations 에서 id 로 op 찾기."""
    for o in session.data.get("operations", []):
        if o.get("id") == op_id:
            return o
    return None


def _patch_segment_volume(session: Any, segment_ref: str, volume: float) -> None:
    """audio 세그먼트 op 의 volume 인자를 덮어씀. 세그먼트 없으면 KeyError."""
    op = _find_segment_op(session, segment_ref)
    if op is None:
        raise KeyError(f"segment_ref '{segment_ref}' op 을 찾을 수 없음")
    op.setdefault("args", {})
    op["args"]["volume"] = volume
    if hasattr(session, "_auto_save"):
        session._auto_save()
