"""시간 계산 유틸리티.

pyCapCut의 ``tim()``은 "3s", "1h5m30s" 같은 단위 있는 문자열만 제대로 파싱하고,
단위 없는 ``"3000000"`` (마이크로초) 같은 raw 숫자 문자열에는 0을 반환하는
버그가 있음. ``parse_time_value()``가 이 케이스를 흡수함.

버그 리포트 #1 대응.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from typing import Any

import pycapcut as cc

SEC = cc.SEC  # = 1_000_000 (microseconds per second)


def parse_time_value(val: Any) -> int:
    """다양한 형식의 시간 입력을 마이크로초(int)로 변환.

    받는 형식:
        - int: 그대로 (마이크로초)
        - 단위 있는 문자열: "3s", "500ms", "1.5s", "2m30s", "1h5m", "500us"
        - raw 마이크로초 정수 문자열: "3000000"
        - 단순 소수 문자열: "3.5" → 초로 해석 (3_500_000us)
        - None / 빈 값 → 0

    pyCapCut의 ``tim()``은 ``ms``/``us`` 단위를 지원하지 않고 bare 숫자 문자열에 0을
    반환하는 버그가 있어서, 여기서 먼저 우리 파서로 처리한다.

    Returns:
        마이크로초 (int).
    """
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    if not isinstance(val, str):
        return 0

    s = val.strip()
    if not s:
        return 0

    sign = 1
    if s[0] in ("+", "-"):
        sign = -1 if s[0] == "-" else 1
        s = s[1:].strip()
    if not s:
        return 0

    # 'us' / 'ms' 먼저 처리 (pyCapCut tim()은 이걸 모름)
    if s.endswith("us"):
        try:
            return int(round(float(s[:-2]))) * sign
        except ValueError:
            return 0
    if s.endswith("ms"):
        try:
            return int(round(float(s[:-2]) * 1000)) * sign
        except ValueError:
            return 0

    # 단위 있는 일반 형식은 tim()에 위임
    try:
        parsed = cc.tim(s)
        if parsed:
            return int(parsed) * sign
    except Exception:
        pass

    # tim()이 0을 반환했다 = 단위 없는 숫자 문자열
    try:
        if "." in s:
            return int(round(float(s) * SEC)) * sign
        return int(s) * sign
    except ValueError:
        return 0


def calc_relative_time(base_us: int, expr: str) -> int:
    """``base_us`` 위에 ``"+2s"`` / ``"-500ms"`` 같은 상대 표현을 적용.

    절대 표현(``"3s"``)이 들어와도 그대로 파싱해서 반환.
    """
    if not expr:
        return base_us
    if expr.startswith(("+", "-")):
        delta = parse_time_value(expr[1:])
        return base_us + (delta if expr[0] == "+" else -delta)
    return parse_time_value(expr)


def calc_auto_start(session_data: dict, track_name: str | None = None) -> int:
    """마지막 세그먼트 뒤에 이어 붙을 마이크로초 위치 계산.

    ``track_name`` 이 주어지면 해당 트랙에 속한 세그먼트만 고려.
    """
    max_end = 0
    for op in session_data.get("operations", []):
        args = op.get("args", {}) or {}
        if track_name and args.get("track") != track_name:
            continue
        start = parse_time_value(args.get("start"))
        dur = parse_time_value(args.get("duration"))
        if dur:
            max_end = max(max_end, start + dur)
    return max_end


def resolve_start_time(
    session_data: dict,
    start: Any,
    track_name: str | None = None,
    gap_ms: int = 0,
) -> str:
    """``"auto"`` / ``"+2s"`` 등을 해석한 시작 시각 반환.

    반환값은 ``tim()`` 호환 문자열 (마이크로초+"s" 꼴) — 세션에 저장 가능하고
    replay 시 다시 ``parse_time_value()``로 풀 수 있음.
    """
    if start is None or start == "auto":
        base = calc_auto_start(session_data, track_name)
        us = base + gap_ms * 1000
        return f"{us}us"
    if isinstance(start, str) and start.startswith(("+", "-")):
        base = calc_auto_start(session_data, track_name)
        us = calc_relative_time(base, start)
        return f"{us}us"
    # 절대 표현 — 그대로 저장 (나중 replay에서 다시 파싱됨)
    return str(start)


def format_us(us: int) -> str:
    """마이크로초를 사람이 읽기 좋은 초 단위 표현으로."""
    if us == 0:
        return "0s"
    s = us / SEC
    return f"{s:.2f}s" if s >= 0.01 else f"{us}us"


def format_duration(us: int) -> str:
    """더 긴 시간을 ``1h5m20s`` 같은 복합 단위로 포매팅."""
    if us <= 0:
        return "0s"
    total_s = us / SEC
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s - h * 3600 - m * 60
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s:.1f}s" if s % 1 else f"{int(s)}s")
    return "".join(parts)


def is_ffprobe_available() -> bool:
    """``ffprobe`` 실행 파일이 PATH에 있는지 검사."""
    return shutil.which("ffprobe") is not None


def _get_wav_duration(file_path: str) -> float | None:
    """ffprobe 없이 Python 표준 ``wave`` 모듈로 WAV 길이만 구함."""
    try:
        with wave.open(file_path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate:
                return frames / rate
    except (wave.Error, FileNotFoundError, OSError):
        return None
    return None


def get_media_duration(file_path: str) -> dict | None:
    """``ffprobe``로 미디어 길이·해상도·fps 메타 조회.

    WAV은 ffprobe가 없어도 ``wave`` 모듈 fallback으로 길이만 반환.
    """
    import os

    if not os.path.exists(file_path):
        return None

    if is_ffprobe_available():
        try:
            import json as _json

            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            out = subprocess.check_output(cmd, timeout=30)
            probe = _json.loads(out)
            dur_s = float(probe.get("format", {}).get("duration", 0) or 0)
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            fps = None
            if video and video.get("r_frame_rate"):
                num, _, den = video["r_frame_rate"].partition("/")
                try:
                    fps = float(num) / float(den) if float(den) else None
                except (ValueError, ZeroDivisionError):
                    fps = None
            return {
                "duration_s": dur_s,
                "duration_us": int(dur_s * SEC),
                "has_video": video is not None,
                "has_audio": audio is not None,
                "width": video.get("width") if video else None,
                "height": video.get("height") if video else None,
                "fps": fps,
                "format": probe.get("format", {}).get("format_name"),
            }
        except (subprocess.SubprocessError, ValueError, KeyError):
            pass

    # WAV fallback
    if file_path.lower().endswith(".wav"):
        dur_s = _get_wav_duration(file_path)
        if dur_s is not None:
            return {
                "duration_s": dur_s,
                "duration_us": int(dur_s * SEC),
                "has_video": False,
                "has_audio": True,
                "width": None,
                "height": None,
                "fps": None,
                "format": "wav",
            }

    return None
