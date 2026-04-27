"""review 커맨드 — 세션 자동 리뷰.

``validate``가 "replay 가능?"을 본다면, ``review``는 그 위에서 사용자에게
사전 경고 + 수정 제안을 낸다. 체크 항목은 서로 독립이라 선별 가능.

지원 체크
---------

- ``gaps``        : 트랙 내 갭 (1s+ warning, 5s+ error)
- ``overlaps``    : 같은 트랙 세그먼트 겹침 (error)
- ``volume``      : 오디오 합산 볼륨 클리핑 (1.0+ warning, 1.5+ error)
- ``subtitles``   : 자막 읽기 속도/길이 (초당 글자수 / 최소/최대 duration)
- ``media``       : 미디어 파일 존재 / staging 추천
- ``resolution``  : 프로젝트 해상도 vs 소스 (ffprobe 있을 때만)
- ``duration``    : 플랫폼별 길이 적합성 (9:16 / 16:9 / 총 0초)
- ``render``      : render-headless 호환성
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.op_registry import CREATION_OPS
from cli_anything.capcut.core.session import Session
from cli_anything.capcut.core.time_utils import (
    format_us,
    get_media_duration,
    is_ffprobe_available,
    parse_time_value,
)

SEC = 1_000_000  # 마이크로초 단위

# 심각도 순서
_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

# 체크 이름 alias — CLI --only 에서 축약 허용
_CHECK_ALIASES: dict[str, str] = {
    "gap": "gaps",
    "overlap": "overlaps",
    "audio": "volume",
    "volume_clipping": "volume",
    "subtitle": "subtitles",
    "subs": "subtitles",
    "text": "subtitles",
    "files": "media",
    "resolutions": "resolution",
    "durations": "duration",
    "length": "duration",
    "renderable": "render",
    "render_headless": "render",
}

# 지원 체크 이름 (_run_checks 에서 자동 채움)
_ALL_CHECKS: list[str] = [
    "gaps",
    "overlaps",
    "volume",
    "subtitles",
    "media",
    "resolution",
    "duration",
    "render",
]


# =========================================================================
# Finding 구조
# =========================================================================


@dataclass
class Finding:
    check: str
    severity: str  # "error" | "warning" | "info"
    message: str
    hint: str | None = None
    location: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # None 필드 제거
        return {k: v for k, v in d.items() if v is not None}


# =========================================================================
# 체크 함수들 (각 체크는 독립적 — session만 받아 list[Finding] 반환)
# =========================================================================


def check_gaps(session: Session) -> list[Finding]:
    """트랙별 갭. 1s+ warning, 5s+ error."""
    findings: list[Finding] = []
    # 모든 트랙에 대해 갭 검사
    for track in _iter_tracks(session):
        for gap in session.gap_detect(track):
            gap_s = gap["gap_us"] / SEC
            if gap_s < 1.0:
                continue  # 1초 미만은 무시 (의도적일 가능성 높음)
            severity = "error" if gap_s >= 5.0 else "warning"
            start_s = gap["start_us"] / SEC
            end_s = gap["end_us"] / SEC
            findings.append(
                Finding(
                    check="gaps",
                    severity=severity,
                    message=f"{track} 트랙 {start_s:.1f}s~{end_s:.1f}s 구간 갭 ({gap_s:.1f}s)",
                    hint=(
                        "인트로/아웃트로 세그먼트를 추가하거나 다음 세그먼트 시작 시간을 당기세요."
                        if severity == "error"
                        else "의도적이면 무시해도 됩니다."
                    ),
                    location={
                        "track": track,
                        "start_us": gap["start_us"],
                        "end_us": gap["end_us"],
                    },
                )
            )
    return findings


def check_overlaps(session: Session) -> list[Finding]:
    """같은 트랙 내 겹침 → error."""
    findings: list[Finding] = []
    for track in _iter_tracks(session):
        for ov in session.overlap_detect(track):
            a, b = ov["a"], ov["b"]
            overlap_s = ov["overlap_us"] / SEC
            findings.append(
                Finding(
                    check="overlaps",
                    severity="error",
                    message=(
                        f"{track} 트랙에서 op {a['id']}와 op {b['id']}가 "
                        f"{overlap_s:.2f}s 겹침"
                    ),
                    hint="CapCut에서 뒤 세그먼트가 앞 세그먼트를 덮어쓸 수 있습니다. start 시간을 조정하세요.",
                    location={
                        "track": track,
                        "op_a_id": a["id"],
                        "op_b_id": b["id"],
                        "overlap_us": ov["overlap_us"],
                    },
                )
            )
    return findings


def check_volume_clipping(session: Session) -> list[Finding]:
    """오디오 합산 볼륨 > 1.0 → warning, > 1.5 → error.

    동시에 활성인 모든 오디오 세그먼트의 volume을 합산. 각 경계점(start/end)에서
    검사하면 전체 구간을 커버할 수 있음.
    """
    audio_segs = _audio_segments(session)
    if len(audio_segs) < 2:
        return []

    # 경계점 수집 (각 세그먼트의 start/end 바로 뒤)
    boundaries: set[int] = set()
    for seg in audio_segs:
        boundaries.add(seg["start_us"])
        boundaries.add(seg["end_us"] - 1)

    findings: list[Finding] = []
    reported_keys: set[tuple[str, ...]] = set()
    for t in sorted(boundaries):
        if t < 0:
            continue
        active = [s for s in audio_segs if s["start_us"] <= t < s["end_us"]]
        if len(active) < 2:
            continue
        total = sum(s["volume"] for s in active)
        if total <= 1.0 + 1e-9:
            continue
        # 중복 리포팅 방지: 동일 조합(세그먼트 id 집합)이면 한 번만.
        key = tuple(sorted(s["id"] for s in active))
        if key in reported_keys:
            continue
        reported_keys.add(key)
        severity = "error" if total > 1.5 + 1e-9 else "warning"
        track_names = " + ".join(sorted({s["track"] or "?" for s in active}))
        findings.append(
            Finding(
                check="volume",
                severity=severity,
                message=(
                    f"{track_names} 합산 {total:.2f} "
                    f"({format_us(t)} 근방) — "
                    f"{'심각한 ' if severity == 'error' else ''}클리핑 위험"
                ),
                hint=(
                    "각 오디오 트랙 volume을 낮추거나 ducking(겹치는 시점만 한쪽을 줄임)을 적용하세요."
                ),
                location={
                    "time_us": t,
                    "segment_ids": list(key),
                    "total_volume": round(total, 3),
                },
            )
        )
    return findings


def check_subtitle_pacing(session: Session) -> list[Finding]:
    """텍스트(T*) 트랙 읽기 속도 체크."""
    findings: list[Finding] = []
    for op in session.data["operations"]:
        if op["op"] != "add_text":
            continue
        args = op.get("args", {}) or {}
        text = (args.get("text") or "").strip()
        if not text:
            continue
        dur_us = parse_time_value(args.get("duration", 0))
        if dur_us <= 0:
            # duration 없으면 검사 불가
            continue
        dur_s = dur_us / SEC
        # 가시 글자수 (공백/줄바꿈은 제외)
        char_count = sum(1 for c in text if not c.isspace())
        cps = char_count / dur_s if dur_s > 0 else 0

        # 표시용 preview
        preview = text.replace("\n", " ")
        if len(preview) > 24:
            preview = preview[:22] + "…"

        op_id = op.get("id")
        track = args.get("track")
        location = {
            "op_id": op_id,
            "track": track,
            "duration_us": dur_us,
            "chars": char_count,
            "cps": round(cps, 2),
        }

        # duration 너무 짧음
        if dur_s < 0.8 and char_count >= 2:
            findings.append(
                Finding(
                    check="subtitles",
                    severity="warning",
                    message=(
                        f'{op_id} "{preview}" duration {dur_s:.2f}s — 너무 짧아서 읽기 어려움'
                    ),
                    hint=f"최소 0.8s 이상으로 늘리세요 (권장 {char_count / 7:.1f}s).",
                    location=location,
                )
            )
        # 너무 빠름 (초당 8자 초과)
        if cps > 8.0:
            severity = "warning"
            findings.append(
                Finding(
                    check="subtitles",
                    severity=severity,
                    message=f'{op_id} "{preview}" 초당 {cps:.1f}자 — 한국어 권장 6~8자 초과',
                    hint="자막을 2개로 분할하거나 duration을 1.5배로 늘리세요.",
                    location=location,
                )
            )
        # 너무 긴 자막
        if dur_s > 10.0:
            findings.append(
                Finding(
                    check="subtitles",
                    severity="info",
                    message=f'{op_id} "{preview}" duration {dur_s:.1f}s — 긴 자막',
                    hint="10초 넘는 자막은 2~3개로 분할하는 편이 가독성에 유리합니다.",
                    location=location,
                )
            )
    return findings


def check_media_files(session: Session) -> list[Finding]:
    """add_video/image/audio op의 file 경로 실존 확인.

    경로에 한글/공백/비ASCII가 있고 staging 비활성이면 info 힌트.
    """
    import os

    findings: list[Finding] = []
    staging_disabled = _is_staging_disabled()

    for op in session.data["operations"]:
        if op["op"] not in ("add_video", "add_image", "add_audio"):
            continue
        args = op.get("args", {}) or {}
        path = args.get("file")
        if not path:
            continue
        op_id = op.get("id")
        location = {"op_id": op_id, "op": op["op"], "file": path}

        if not Path(path).exists():
            findings.append(
                Finding(
                    check="media",
                    severity="error",
                    message=f"파일 누락: {path}",
                    hint="경로 오타 확인. 외장 드라이브면 연결 상태 확인.",
                    location=location,
                )
            )
            continue

        # ASCII 외 문자 감지 (한글 / 공백 / 기호) — staging이 꺼져 있으면 info
        if staging_disabled and _has_non_ascii_or_space(path):
            findings.append(
                Finding(
                    check="media",
                    severity="info",
                    message=f"비ASCII/공백 경로: {os.path.basename(path)} (staging 비활성)",
                    hint="CAPCUT_NO_STAGING=1 을 끄거나 영문 경로로 복사하세요.",
                    location=location,
                )
            )
    return findings


def check_resolution_mismatch(session: Session) -> list[Finding]:
    """프로젝트 해상도 vs 미디어 해상도. ffprobe 없으면 skip."""
    if not is_ffprobe_available():
        return [
            Finding(
                check="resolution",
                severity="info",
                message="ffprobe 미설치 — 해상도 체크 skip",
                hint="ffmpeg/ffprobe를 설치하면 소스 해상도 비교가 가능합니다.",
                location={"skip_reason": "ffprobe_not_available"},
            )
        ]

    findings: list[Finding] = []
    proj_h = session.height
    # 중복 파일은 한 번만 리포트
    seen_files: set[str] = set()
    for op in session.data["operations"]:
        if op["op"] not in ("add_video", "add_image"):
            continue
        args = op.get("args", {}) or {}
        f = args.get("file")
        if not f or f in seen_files:
            continue
        seen_files.add(f)
        if not Path(f).exists():
            continue  # media check가 잡음
        meta = get_media_duration(f)
        if not meta or not meta.get("has_video"):
            continue
        src_h = meta.get("height") or 0
        if src_h <= 0:
            continue
        if src_h < proj_h:
            findings.append(
                Finding(
                    check="resolution",
                    severity="info",
                    message=(
                        f"{Path(f).name}: 소스 {meta.get('width')}x{src_h} "
                        f"< 프로젝트 {session.width}x{proj_h} — 업스케일 (품질 저하)"
                    ),
                    hint="가능하면 더 높은 해상도 소스를 확보하세요.",
                    location={"file": f, "src_height": src_h, "project_height": proj_h},
                )
            )
        elif src_h > proj_h * 1.5:
            findings.append(
                Finding(
                    check="resolution",
                    severity="info",
                    message=(
                        f"{Path(f).name}: 소스 {meta.get('width')}x{src_h} "
                        f"> 프로젝트 {session.width}x{proj_h} — 다운스케일 (성능 최적화 기회)"
                    ),
                    hint="원본을 미리 프로젝트 해상도로 줄이면 렌더가 빨라집니다.",
                    location={"file": f, "src_height": src_h, "project_height": proj_h},
                )
            )
    return findings


def check_duration(session: Session) -> list[Finding]:
    """플랫폼별 길이 권장 + 빈 프로젝트 에러."""
    findings: list[Finding] = []
    stats = session.stats()
    total_us = stats["duration_us"]
    if total_us <= 0:
        findings.append(
            Finding(
                check="duration",
                severity="error",
                message="빈 프로젝트 — 총 길이 0",
                hint="add_video/image/audio/text 로 세그먼트를 추가하세요.",
                location={"duration_us": 0},
            )
        )
        return findings

    total_s = total_us / SEC
    w, h = session.width, session.height
    is_vertical = h > w  # 9:16 류
    is_horizontal = w > h  # 16:9 류

    def _add(severity: str, message: str, hint: str | None = None) -> None:
        findings.append(
            Finding(
                check="duration",
                severity=severity,
                message=message,
                hint=hint,
                location={
                    "duration_us": total_us,
                    "duration_s": round(total_s, 2),
                    "width": w,
                    "height": h,
                },
            )
        )

    if is_vertical:
        if total_s < 15:
            _add("info", f"9:16 / {total_s:.1f}s — TikTok·Instagram Reels 최적 길이")
        elif total_s <= 60:
            _add("info", f"9:16 / {total_s:.1f}s — 숏폼 표준 길이")
        elif total_s <= 90:
            _add(
                "info",
                f"9:16 / {total_s:.1f}s — 길이 경계 (60~90s). 플랫폼별 허용 여부 확인",
            )
        else:
            _add(
                "warning",
                f"9:16 / {total_s:.1f}s — 숏폼 플랫폼 대부분 한계 초과 (보통 ≤90s)",
                hint="분할 업로드하거나 핵심 구간만 남기세요.",
            )
    elif is_horizontal:
        if total_s < 30:
            _add("info", f"16:9 / {total_s:.1f}s — 짧은 유튜브/광고 구간")
        elif total_s <= 600:
            _add("info", f"16:9 / {total_s:.1f}s — 일반 YouTube 길이")
        elif total_s <= 1800:
            _add("info", f"16:9 / {total_s:.1f}s — 중장편 YouTube")
        else:
            _add(
                "info",
                f"16:9 / {total_s:.1f}s — 롱폼 (≥30분). 렌더/업로드 시간 주의",
                hint="프리뷰는 구간별로 나눠 확인하세요.",
            )
    else:
        # 1:1 등
        _add("info", f"1:1 / {total_s:.1f}s — 정사각형 비율")

    return findings


def check_unsupported_for_render(session: Session) -> list[Finding]:
    """render-headless 호환성 — analyze_session_for_render 재사용."""
    # 지연 import로 render_headless 내 import 체인 타지 않음
    try:
        from cli_anything.capcut.commands.render_headless import (
            analyze_session_for_render,
        )
    except Exception as e:  # pragma: no cover
        return [
            Finding(
                check="render",
                severity="info",
                message=f"render-headless 모듈 로드 실패 — 체크 skip ({e})",
            )
        ]

    analysis = analyze_session_for_render(session)
    unsupported = analysis.get("unsupported_ops") or []
    if not unsupported:
        return []
    findings: list[Finding] = []
    # 같은 op 이름은 하나로 묶기
    grouped: dict[str, list[dict]] = {}
    for u in unsupported:
        grouped.setdefault(u["op"], []).append(u)
    for op_name, items in grouped.items():
        ids = [it.get("id") for it in items if it.get("id")]
        findings.append(
            Finding(
                check="render",
                severity="info",
                message=(
                    f"render-headless는 '{op_name}' op를 지원하지 않음 "
                    f"({len(items)}건)"
                ),
                hint="CapCut GUI로 저장 후 수동 렌더를 사용하세요.",
                location={"op": op_name, "op_ids": ids},
            )
        )
    return findings


# =========================================================================
# 메인 오케스트레이션
# =========================================================================


_CHECK_FUNCS: dict[str, Any] = {
    "gaps": check_gaps,
    "overlaps": check_overlaps,
    "volume": check_volume_clipping,
    "subtitles": check_subtitle_pacing,
    "media": check_media_files,
    "resolution": check_resolution_mismatch,
    "duration": check_duration,
    "render": check_unsupported_for_render,
}


def run_review(
    session: Session, *, only: list[str] | None = None
) -> list[Finding]:
    """모든 체크 실행. only 지정 시 해당 체크만."""
    if only:
        wanted = _normalize_check_names(only)
    else:
        wanted = list(_ALL_CHECKS)

    findings: list[Finding] = []
    for name in wanted:
        fn = _CHECK_FUNCS.get(name)
        if fn is None:
            findings.append(
                Finding(
                    check="review",
                    severity="warning",
                    message=f"알 수 없는 체크: {name} (무시)",
                    hint=f"지원 체크: {', '.join(_ALL_CHECKS)}",
                )
            )
            continue
        try:
            findings.extend(fn(session) or [])
        except Exception as e:  # pragma: no cover
            findings.append(
                Finding(
                    check=name,
                    severity="warning",
                    message=f"{name} 체크 실행 중 예외: {type(e).__name__}: {e}",
                )
            )
    return findings


def filter_by_severity(
    findings: list[Finding], min_severity: str
) -> list[Finding]:
    """min_severity 이상만 남김. order: info < warning < error."""
    threshold = _SEVERITY_ORDER.get(min_severity, 0)
    return [
        f for f in findings if _SEVERITY_ORDER.get(f.severity, 0) >= threshold
    ]


def summarize_findings(findings: list[Finding]) -> dict:
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        if f.severity in counts:
            counts[f.severity] += 1
    if counts["error"]:
        status = "error"
    elif counts["warning"]:
        status = "warning"
    else:
        status = "ok"
    return {"status": status, "finding_count": counts}


def format_findings_human(findings: list[Finding]) -> str:
    """사람 친화 출력 (색상/이모지 없이). 심각도 순 정렬."""
    if not findings:
        return "리뷰 통과 — 지적 사항 없음."
    # error 먼저, 그 다음 warning, 그 다음 info
    ordered = sorted(
        findings, key=lambda f: (-_SEVERITY_ORDER.get(f.severity, 0), f.check)
    )
    lines: list[str] = []
    for f in ordered:
        sev = f.severity.upper().ljust(7)
        check_tag = f"[{f.check}]".ljust(13)
        lines.append(f"{sev} {check_tag} {f.message}")
        if f.hint:
            lines.append(f"  → 힌트: {f.hint}")
    return "\n".join(lines)


# =========================================================================
# 내부 헬퍼
# =========================================================================


def _iter_tracks(session: Session) -> list[str]:
    """세션에서 쓰이는 트랙 이름들 (세그먼트 op 기준)."""
    tracks: list[str] = []
    seen: set[str] = set()
    for op in session.data["operations"]:
        if op["op"] not in CREATION_OPS:
            continue
        a = op.get("args", {}) or {}
        t = a.get("track")
        if t and t not in seen:
            seen.add(t)
            tracks.append(t)
    return tracks


def _audio_segments(session: Session) -> list[dict]:
    out: list[dict] = []
    for op in session.data["operations"]:
        if op["op"] != "add_audio":
            continue
        a = op.get("args", {}) or {}
        start = parse_time_value(a.get("start", 0))
        dur = parse_time_value(a.get("duration", 0))
        if dur <= 0:
            continue
        out.append(
            {
                "id": op.get("id"),
                "track": a.get("track"),
                "start_us": start,
                "end_us": start + dur,
                "volume": float(a.get("volume", 1.0) or 1.0),
            }
        )
    return out


def _has_non_ascii_or_space(path: str) -> bool:
    """staging 필요성 추정 — 비 ASCII나 공백이 있으면 True."""
    try:
        path.encode("ascii")
    except UnicodeEncodeError:
        return True
    return " " in path


def _is_staging_disabled() -> bool:
    import os

    val = os.environ.get("CAPCUT_NO_STAGING")
    return bool(val) and val not in ("0", "", "false", "False")


def _normalize_check_names(names: list[str]) -> list[str]:
    out: list[str] = []
    for raw in names:
        n = raw.strip().lower()
        n = _CHECK_ALIASES.get(n, n)
        if n and n not in out:
            out.append(n)
    return out


# =========================================================================
# CLI 커맨드
# =========================================================================


@click.command(
    "review",
    help="세션 자동 리뷰 (갭/겹침/볼륨/자막속도/미디어/해상도/길이/렌더호환)",
)
@click.option("-p", "--project", "project_path", required=True,
              help="세션 JSON 파일 경로")
@click.option(
    "--severity",
    type=click.Choice(["info", "warning", "error"]),
    default="info",
    show_default=True,
    help="이 심각도 이상만 출력",
)
@click.option(
    "--only",
    default=None,
    help="특정 체크만 (쉼표 구분): gaps,overlaps,volume,subtitles,media,resolution,duration,render",
)
@click.option(
    "--fail-on-warning",
    is_flag=True,
    default=False,
    help="warning만 있어도 종료 코드 1 (error면 언제나 2)",
)
@click.pass_context
def review_cmd(ctx, project_path, severity, only, fail_on_warning):
    session = load_session(project_path)

    only_list = None
    if only:
        only_list = [p for p in only.split(",") if p.strip()]

    findings = run_review(session, only=only_list)
    findings = filter_by_severity(findings, severity)
    summary = summarize_findings(findings)

    as_json = ctx.obj.get("json", False)
    if as_json:
        output_result(
            {
                **summary,
                "findings": [f.to_dict() for f in findings],
            },
            True,
        )
    else:
        click.echo(format_findings_human(findings))
        click.echo("")
        c = summary["finding_count"]
        click.echo(
            f"status={summary['status']}  "
            f"error={c['error']}  warning={c['warning']}  info={c['info']}"
        )

    # 종료 코드
    if summary["status"] == "error":
        sys.exit(2)
    if fail_on_warning and summary["status"] == "warning":
        sys.exit(1)
