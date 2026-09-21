"""Audit CapCut English aliases against the installed pycapcut enums.

Run from the repository root::

    python scripts/alias_audit.py

`FONT_ALIASES` is intentionally excluded from the alias-dictionary table because
fonts do not use the strict enum-resolution path. Built-in style font references
are still checked through ``resolve_font`` below.
"""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
from importlib import metadata
from pathlib import Path
import re
import sys
from typing import Type


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pycapcut as cc

from cli_anything.capcut.core import alias_map, style_registry


AUDIT_TARGETS: tuple[tuple[str, str], ...] = (
    ("MASK_ALIASES", "MaskType"),
    ("FILTER_ALIASES", "FilterType"),
    ("TRANSITION_ALIASES", "TransitionType"),
    ("INTRO_ALIASES", "IntroType"),
    ("OUTRO_ALIASES", "OutroType"),
    ("GROUP_ANIMATION_ALIASES", "GroupAnimationType"),
    ("TEXT_INTRO_ALIASES", "TextIntro"),
    ("TEXT_OUTRO_ALIASES", "TextOutro"),
    ("TEXT_LOOP_ANIM_ALIASES", "TextLoopAnim"),
    ("VIDEO_SCENE_EFFECT_ALIASES", "VideoSceneEffectType"),
    ("VIDEO_CHARACTER_EFFECT_ALIASES", "VideoCharacterEffectType"),
    ("AUDIO_SCENE_EFFECT_ALIASES", "AudioSceneEffectType"),
)

BUILTIN_REFERENCE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "text": (("font", "FontType"),),
    "video": (
        ("filter", "FilterType"),
        ("animation_intro", "IntroType"),
        ("animation_outro", "OutroType"),
        ("effect", "VideoSceneEffectType"),
    ),
    "audio": (("effect", "AudioSceneEffectType"),),
}


def _normalize(value: str) -> str:
    return re.sub(r"[_\s\-]", "", value).casefold()


def _candidate_replacements(
    target: str,
    enum_cls: Type[Enum],
    *,
    limit: int = 3,
) -> list[str]:
    """Return deterministic name-similarity candidates, never invented names."""
    normalized_target = _normalize(target)
    target_chars = set(normalized_target)
    ranked: list[tuple[float, str]] = []

    for member_name in enum_cls.__members__:
        normalized_member = _normalize(member_name)
        sequence_score = SequenceMatcher(
            None, normalized_target, normalized_member
        ).ratio()
        overlap_score = (
            len(target_chars & set(normalized_member)) / len(target_chars)
            if target_chars
            else 0.0
        )
        contains = (
            normalized_target in normalized_member
            or normalized_member in normalized_target
        )
        score = max(sequence_score, overlap_score * 0.75)
        if contains:
            score += 0.25
        if score >= 0.55:
            ranked.append((score, member_name))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [member_name for _, member_name in ranked[:limit]]


def _builtin_style_references() -> list[tuple[str, str, str, str, str]]:
    """Return every alias-bearing field referenced by the built-in styles."""
    references: list[tuple[str, str, str, str, str]] = []
    for category, styles in style_registry._BUILTIN.items():
        for style_name, spec in styles.items():
            for field, enum_class_name in BUILTIN_REFERENCE_FIELDS.get(category, ()):
                value = spec.get(field)
                if isinstance(value, dict):
                    value = value.get("name")
                if isinstance(value, str) and value:
                    references.append(
                        (category, style_name, field, value, enum_class_name)
                    )
    return references


def _audit_builtin_styles() -> tuple[int, int]:
    """Print and count live/dead aliases referenced by ``_BUILTIN``."""
    references = _builtin_style_references()
    dead = 0

    print("Built-in style references")
    for category, style_name, field, value, enum_class_name in references:
        try:
            if enum_class_name == "FontType":
                alias_map.resolve_font(value)
            else:
                alias_map.resolve_alias(enum_class_name, value)
        except (KeyError, ValueError) as error:
            dead += 1
            status = "dead"
            error_text = f" error={str(error)!r}"
        else:
            status = "alive"
            error_text = ""

        print(
            f"  {status}: style={category}/{style_name} field={field} "
            f"value={value!r} class={enum_class_name}{error_text}"
        )

    print(
        f"BUILTIN_STYLES: total={len(references)} "
        f"alive={len(references) - dead} dead={dead}"
    )
    return len(references), dead


def audit() -> int:
    try:
        version = metadata.version("pycapcut")
    except metadata.PackageNotFoundError:
        version = getattr(cc, "__version__", "unknown")

    audit_time = datetime.now().astimezone().replace(microsecond=0).isoformat()
    print("CapCut alias enum audit")
    print(f"pycapcut version: {version}")
    print(f"audit time: {audit_time}")
    print("FONT_ALIASES: excluded (separate non-strict font path)")

    grand_total = 0
    grand_dead = 0
    for alias_dict_name, enum_class_name in AUDIT_TARGETS:
        aliases = getattr(alias_map, alias_dict_name)
        enum_cls = getattr(cc, enum_class_name)
        member_names = set(enum_cls.__members__)
        dead = [
            (alias, target)
            for alias, target in aliases.items()
            if target not in member_names
        ]
        total = len(aliases)
        alive = total - len(dead)
        grand_total += total
        grand_dead += len(dead)

        print(
            f"{alias_dict_name} ({enum_class_name}): "
            f"total={total} alive={alive} dead={len(dead)}"
        )
        for alias, target in dead:
            candidates = _candidate_replacements(target, enum_cls)
            candidate_text = ", ".join(candidates) if candidates else "<none>"
            print(
                f"  dead: alias={alias!r} target={target!r} "
                f"candidates=[{candidate_text}]"
            )

    _, builtin_dead = _audit_builtin_styles()

    print(
        f"TOTAL: total={grand_total} alive={grand_total - grand_dead} "
        f"dead={grand_dead}"
    )
    return 1 if grand_dead or builtin_dead else 0


if __name__ == "__main__":
    raise SystemExit(audit())
