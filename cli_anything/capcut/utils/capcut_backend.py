"""CapCut 드래프트 폴더 자동 감지.

환경변수 ``CAPCUT_DRAFT_FOLDER``가 있으면 그걸 사용.
없으면 OS별 기본 경로 목록을 순회.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_CANDIDATES_WINDOWS = [
    # CapCut (international)
    r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft",
    # JianYing (中文版)
    r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
]

_CANDIDATES_MAC = [
    "~/Movies/CapCut/User Data/Projects/com.lveditor.draft",
    "~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
]

_CANDIDATES_LINUX: list[str] = []


def get_default_draft_folder() -> str | None:
    """CapCut/剪映 드래프트 폴더 경로를 찾아 반환. 못 찾으면 None."""
    override = os.environ.get("CAPCUT_DRAFT_FOLDER")
    if override:
        return override

    if sys.platform == "win32":
        candidates = _CANDIDATES_WINDOWS
    elif sys.platform == "darwin":
        candidates = _CANDIDATES_MAC
    else:
        candidates = _CANDIDATES_LINUX

    for raw in candidates:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if os.path.exists(expanded):
            return expanded
    return None


def require_draft_folder(explicit: str | None = None) -> str:
    """명시 인자가 있으면 그걸 쓰고, 없으면 자동 감지. 실패 시 에러."""
    if explicit:
        p = Path(explicit).expanduser()
        return str(p)
    found = get_default_draft_folder()
    if found:
        return found
    raise RuntimeError(
        "CapCut 드래프트 폴더를 자동 감지하지 못했습니다. "
        "--draft-folder 인자 또는 CAPCUT_DRAFT_FOLDER 환경변수를 설정하세요."
    )
