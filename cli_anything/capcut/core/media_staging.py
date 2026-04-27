"""미디어 파일 경로 자동 스테이징.

CapCut/JianYing은 한글 · 공백 · 기타 비ASCII 경로의 미디어 파일을 제대로 못 연다.
이 모듈은 그런 경로를 감지해서 임시 영문 캐시 디렉토리(예: ``%TEMP%/capcut-stage/``)
로 하드링크(불가능하면 copy)하고, 스테이징된 경로를 돌려준다.

전체 흐름
---------

1. 사용자: ``cli-anything-capcut video add -f "D:/media/my-video.mp4" ...``
2. ``commands/media.py`` 의 ``_segment_add`` 가 :func:`stage_media` 를 호출
3. 반환된 영문 경로가 세션 op log 의 ``file`` 필드에 기록됨
4. CapCut 은 영문 경로로 미디어를 읽어 정상 로드

캐시 정책
---------

* 파일명: ``sha1(src_abs + mtime)[:12] + 원본확장자`` — 같은 파일은 재사용, 충돌 방지
* 재스테이징 시 이미 존재하고 mtime 일치하면 skip
* 환경변수 ``CAPCUT_NO_STAGING=1`` 이 켜져 있으면 항상 noop
* 환경변수 ``CAPCUT_STAGE_DIR`` 로 캐시 위치 오버라이드 가능
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


# 스테이징 필요 판정에 사용할 "안전 문자" (ASCII letters/digits + 일부 기호)
_SAFE_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._-/\\:"
)


def _default_cache_dir() -> Path:
    """캐시 디렉토리 결정 — 환경변수 > OS 기본값."""
    env = os.environ.get("CAPCUT_STAGE_DIR")
    if env:
        return Path(env)
    # tempfile.gettempdir() 는 윈도/리눅스 모두 적절히 반환
    return Path(tempfile.gettempdir()) / "capcut-stage"


def _staging_disabled() -> bool:
    val = os.environ.get("CAPCUT_NO_STAGING")
    return bool(val) and val not in ("0", "", "false", "False")


# =========================================================================
# public API
# =========================================================================


def needs_staging(path: str) -> bool:
    """경로에 ASCII 외 문자 또는 공백이 포함되어 있으면 True.

    Windows CapCut / macOS JianYing 공통 문제로, 비-ASCII 나 공백이 포함된 경로는
    미디어 로드가 실패하거나 재생이 안 되는 현상이 보고됨.
    """
    if not path:
        return False
    for ch in str(path):
        if ord(ch) > 127:
            return True
        if ch == " ":
            return True
        # 안전 문자 외 기호 (예: 괄호, 한글 자모 분리 등) — 보수적으로 True
        if ch not in _SAFE_CHARS:
            # 이미 위에서 127 초과는 걸렀으니, 여기서는 프린터블 ASCII 특수문자
            # (예: '(', ')', '[', ']', '{', '}', '+', '#', '&', '@', '!' ...) 만 해당
            # 안전하게 스테이징.
            return True
    return False


def _fingerprint(src_abs: Path) -> str:
    """src_abs + mtime 기반 SHA-1 12자."""
    try:
        mtime = src_abs.stat().st_mtime_ns
    except OSError:
        mtime = 0
    key = f"{str(src_abs).lower()}|{mtime}"
    return hashlib.sha1(key.encode("utf-8", errors="replace")).hexdigest()[:12]


def _staged_name(src_abs: Path) -> str:
    return _fingerprint(src_abs) + src_abs.suffix.lower()


def _try_hardlink(src: Path, dst: Path) -> bool:
    """하드링크 시도. 실패하면 False."""
    try:
        os.link(str(src), str(dst))
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False


def stage_media(src: str, *, cache_dir: Path | None = None) -> tuple[str, dict[str, Any]]:
    """``src`` 를 영문 스테이징 경로로 복사/하드링크하고 (staged_path, info) 반환.

    Parameters
    ----------
    src : str
        원본 미디어 파일 경로.
    cache_dir : Path, optional
        스테이징 캐시 디렉토리 (기본: :func:`_default_cache_dir`).

    Returns
    -------
    (staged_path, info) : tuple
        ``staged_path`` 는 CapCut 이 읽을 수 있는 경로.
        ``info`` 는 다음 키를 가진 dict:

        * ``original`` — 입력 경로 (str)
        * ``staged`` — 결과 경로 (str)
        * ``method`` — ``"hardlink"`` / ``"copy"`` / ``"noop"`` / ``"cached"``
        * ``hash`` — 파일 지문 (SHA-1 12자) 또는 ``None`` (noop)

    Notes
    -----
    * ``needs_staging(src)`` 가 False 면 곧바로 ``method="noop"`` 반환.
    * 환경변수 ``CAPCUT_NO_STAGING`` 이 truthy 이면 경로 상관없이 noop.
    * 이미 스테이징된 파일 (같은 fingerprint) 은 재사용 — ``method="cached"``.
    """
    info: dict[str, Any] = {
        "original": str(src),
        "staged": str(src),
        "method": "noop",
        "hash": None,
    }

    if not src:
        return str(src), info

    if _staging_disabled():
        return str(src), info

    if not needs_staging(src):
        return str(src), info

    src_path = Path(src)
    if not src_path.exists():
        # 존재하지 않는 파일은 스테이징 불가 — 그대로 돌려주어 상위 레이어가 처리
        info["method"] = "missing"
        return str(src), info

    src_abs = src_path.resolve()
    cache = cache_dir or _default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)

    fingerprint = _fingerprint(src_abs)
    staged_name = _staged_name(src_abs)
    dst = cache / staged_name

    # 캐시 히트: 파일이 이미 있고 원본 mtime 이 동일 → 재사용
    if dst.exists():
        info["staged"] = str(dst)
        info["hash"] = fingerprint
        info["method"] = "cached"
        return str(dst), info

    # 하드링크 시도 (같은 볼륨일 때만 성공)
    if _try_hardlink(src_abs, dst):
        info["staged"] = str(dst)
        info["hash"] = fingerprint
        info["method"] = "hardlink"
        return str(dst), info

    # fallback: copy2 (메타데이터 보존)
    try:
        shutil.copy2(str(src_abs), str(dst))
    except OSError as e:  # pragma: no cover - 디스크 풀 / 권한 등
        info["method"] = "failed"
        info["error"] = f"{type(e).__name__}: {e}"
        return str(src), info

    info["staged"] = str(dst)
    info["hash"] = fingerprint
    info["method"] = "copy"
    return str(dst), info


def unstage_all(cache_dir: Path | None = None) -> int:
    """캐시 디렉토리의 모든 파일 삭제. 삭제된 파일 수 반환."""
    cache = cache_dir or _default_cache_dir()
    if not cache.exists():
        return 0
    removed = 0
    for p in cache.iterdir():
        if p.is_file():
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def staging_stats(cache_dir: Path | None = None) -> dict[str, Any]:
    """``{'file_count': N, 'total_bytes': B, 'cache_dir': str}`` 반환."""
    cache = cache_dir or _default_cache_dir()
    count = 0
    total = 0
    if cache.exists():
        for p in cache.iterdir():
            if p.is_file():
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return {
        "file_count": count,
        "total_bytes": total,
        "cache_dir": str(cache),
    }


def staging_list(cache_dir: Path | None = None) -> list[dict[str, Any]]:
    """캐시 내 파일 목록 반환 (name, size, mtime)."""
    cache = cache_dir or _default_cache_dir()
    out: list[dict[str, Any]] = []
    if not cache.exists():
        return out
    for p in sorted(cache.iterdir()):
        if not p.is_file():
            continue
        try:
            st = p.stat()
            out.append({
                "name": p.name,
                "path": str(p),
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
        except OSError:
            continue
    return out
