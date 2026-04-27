"""preview 커맨드 — self-contained HTML 간트차트 미리보기 생성.

CapCut을 열지 않고도 세션의 트랙/세그먼트/겹침/갭을 시각적으로 검토할 수 있도록
외부 의존성 0개의 단일 HTML 파일을 만든다. ``--thumbs`` 옵션을 주면 ffmpeg로
각 비디오/이미지 세그먼트의 첫 프레임을 base64 인라인으로 삽입한다.
"""

from __future__ import annotations

import base64
import html as _html
import json
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.op_registry import CREATION_OPS
from cli_anything.capcut.core.time_utils import (
    SEC,
    format_duration,
    format_us,
    parse_time_value,
)


# =========================================================================
# 색상 팔레트 (다크 테마)
# =========================================================================

_COLORS = {
    "bg": "#1a1a1a",
    "panel": "#242424",
    "border": "#333",
    "text": "#e5e5e5",
    "muted": "#9ca3af",
    "video": "#4a9eff",
    "audio": "#2dd4bf",
    "text_seg": "#fb923c",
    "sticker": "#f472b6",
    "effect": "#a78bfa",
    "filter": "#64748b",
    "overlap": "#ef4444",
    "track_row": "#1e1e1e",
}


# op -> (segment_type, color_key)
_OP_TO_TYPE = {
    "add_video": ("video", "video"),
    "add_image": ("video", "video"),
    "add_audio": ("audio", "audio"),
    "add_text": ("text", "text_seg"),
    "add_sticker": ("sticker", "sticker"),
    "add_effect": ("effect", "effect"),
    "add_filter": ("filter", "filter"),
}


# =========================================================================
# 공개 헬퍼
# =========================================================================


def _collect_segments(session) -> list[dict]:
    """session에서 세그먼트 정보 추출.

    반환 항목: ``{track, type, color, start_us, end_us, duration_us, file, op, op_id, index}``.
    """
    segs: list[dict] = []
    for i, op in enumerate(session.data.get("operations", [])):
        op_name = op.get("op", "")
        if op_name not in CREATION_OPS:
            continue
        args = op.get("args", {}) or {}
        start_us = parse_time_value(args.get("start", 0))
        dur_us = parse_time_value(args.get("duration", 0))
        end_us = start_us + dur_us
        seg_type, color_key = _OP_TO_TYPE.get(op_name, ("other", "filter"))
        track = args.get("track") or "_default_"
        segs.append({
            "index": i,
            "op_id": op.get("id"),
            "op": op_name,
            "type": seg_type,
            "color": _COLORS[color_key],
            "track": str(track),
            "start_us": int(start_us),
            "end_us": int(end_us),
            "duration_us": int(dur_us),
            "file": args.get("file") or args.get("text") or "",
            "args": args,
        })
    return segs


def _compute_gaps_overlaps(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    """트랙별 갭과 겹침 계산."""
    by_track: dict[str, list[dict]] = {}
    for s in segments:
        by_track.setdefault(s["track"], []).append(s)

    gaps: list[dict] = []
    overlaps: list[dict] = []
    overlap_ids: set[str] = set()

    for track, segs in by_track.items():
        segs_sorted = sorted(segs, key=lambda x: x["start_us"])
        for prev, cur in zip(segs_sorted, segs_sorted[1:]):
            if cur["start_us"] > prev["end_us"]:
                gaps.append({
                    "track": track,
                    "start_us": prev["end_us"],
                    "end_us": cur["start_us"],
                    "gap_us": cur["start_us"] - prev["end_us"],
                })
            elif cur["start_us"] < prev["end_us"]:
                overlaps.append({
                    "track": track,
                    "a_id": prev["op_id"],
                    "b_id": cur["op_id"],
                    "overlap_us": prev["end_us"] - cur["start_us"],
                })
                overlap_ids.add(prev["op_id"])
                overlap_ids.add(cur["op_id"])

    # segments에 overlap 플래그 주입
    for s in segments:
        s["overlap"] = s["op_id"] in overlap_ids

    return gaps, overlaps


def _extract_thumbnail(file: str, time_s: float, cache_dir: Path | None = None) -> str | None:
    """ffmpeg로 첫 프레임 뽑아 base64 data URL 반환. 실패 시 None.

    ``cache_dir``이 주어지면 같은 (파일, 시간) 조합의 썸네일을 캐시에 재사용한다.
    """
    if not shutil.which("ffmpeg"):
        return None
    if not file or not os.path.exists(file):
        return None

    cache_key = None
    if cache_dir is not None:
        safe = Path(file).name.replace(" ", "_")
        cache_key = cache_dir / f"{safe}_{int(time_s * 1000)}ms.jpg"
        if cache_key.exists():
            try:
                data = cache_key.read_bytes()
                if data:
                    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
            except OSError:
                pass

    # 시작 지점이 너무 크면 미디어 끝을 넘을 수 있음 — ffmpeg가 알아서 fail
    ss = max(0.0, time_s)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{ss:.3f}",
        "-i", file,
        "-frames:v", "1",
        "-vf", "scale=120:-1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None

    data = result.stdout
    if cache_key is not None:
        try:
            cache_key.parent.mkdir(parents=True, exist_ok=True)
            cache_key.write_bytes(data)
        except OSError:
            pass
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _default_thumb_cache() -> Path:
    return Path.home() / ".capcut_cli" / "thumbs"


# =========================================================================
# SVG 렌더링
# =========================================================================


def _track_sort_key(name: str) -> tuple[int, str]:
    """V1, V2, A1, A2, T1 ... 순서로 정렬하기 위한 키."""
    order = {"V": 0, "A": 1, "T": 2, "S": 3, "E": 4, "F": 5}
    if name and len(name) >= 1 and name[0].upper() in order:
        return (order[name[0].upper()], name)
    return (99, name)


def _render_gantt_svg(segments: list[dict], total_us: int, tracks: list[str]) -> str:
    """SVG 간트차트 문자열 반환."""
    # 레이아웃 상수
    left_gutter = 80        # 트랙 라벨 영역
    right_pad = 20
    track_height = 44
    top_pad = 30            # X축 눈금 영역
    bottom_pad = 10
    svg_width = 1200        # viewBox 기준 (CSS로 스케일)
    content_w = svg_width - left_gutter - right_pad

    if not tracks:
        tracks = ["_default_"]
    height = top_pad + track_height * len(tracks) + bottom_pad

    # total_us가 0이면 스케일 계산 불가 — 최소 1초로 대체
    effective_total = max(total_us, SEC)

    def x_for(us: int) -> float:
        return left_gutter + (us / effective_total) * content_w

    parts: list[str] = []
    parts.append(
        f'<svg id="gantt" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_width} {height}" '
        f'preserveAspectRatio="xMinYMid meet" role="img" aria-label="Timeline gantt chart">'
    )

    # 배경
    parts.append(
        f'<rect x="0" y="0" width="{svg_width}" height="{height}" '
        f'fill="{_COLORS["bg"]}"/>'
    )

    # 빗금 패턴 (갭 표시용)
    parts.append(
        '<defs>'
        '<pattern id="gapStripes" patternUnits="userSpaceOnUse" width="8" height="8" '
        'patternTransform="rotate(45)">'
        '<rect width="8" height="8" fill="#2a2a2a"/>'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#3a3a3a" stroke-width="3"/>'
        '</pattern>'
        '</defs>'
    )

    # X축 눈금 (최대 10개)
    n_ticks = 10
    for i in range(n_ticks + 1):
        frac = i / n_ticks
        tus = int(effective_total * frac)
        tx = x_for(tus)
        parts.append(
            f'<line x1="{tx:.1f}" y1="{top_pad - 6}" x2="{tx:.1f}" y2="{height - bottom_pad}" '
            f'stroke="{_COLORS["border"]}" stroke-width="0.5"/>'
        )
        label = format_us(tus)
        parts.append(
            f'<text x="{tx:.1f}" y="{top_pad - 10}" fill="{_COLORS["muted"]}" '
            f'font-size="10" text-anchor="middle" font-family="monospace">{_html.escape(label)}</text>'
        )

    # 트랙별 행
    track_to_y: dict[str, float] = {}
    for idx, track in enumerate(tracks):
        y = top_pad + idx * track_height
        track_to_y[track] = y
        # 홀수 행 배경
        if idx % 2 == 0:
            parts.append(
                f'<rect x="{left_gutter}" y="{y}" width="{content_w}" height="{track_height}" '
                f'fill="{_COLORS["track_row"]}"/>'
            )
        # 라벨
        parts.append(
            f'<text x="{left_gutter - 10}" y="{y + track_height / 2 + 4}" fill="{_COLORS["text"]}" '
            f'font-size="13" text-anchor="end" font-family="monospace" font-weight="bold">'
            f'{_html.escape(track)}</text>'
        )

        # 트랙별 갭을 빗금으로
        track_segs = sorted(
            [s for s in segments if s["track"] == track],
            key=lambda x: x["start_us"],
        )
        for prev, cur in zip(track_segs, track_segs[1:]):
            if cur["start_us"] > prev["end_us"]:
                gx = x_for(prev["end_us"])
                gw = x_for(cur["start_us"]) - gx
                if gw > 1:
                    parts.append(
                        f'<rect x="{gx:.1f}" y="{y + 4}" width="{gw:.1f}" '
                        f'height="{track_height - 8}" fill="url(#gapStripes)" '
                        f'opacity="0.55"/>'
                    )

    # 세그먼트 박스
    for seg in segments:
        y = track_to_y.get(seg["track"])
        if y is None:
            continue
        x = x_for(seg["start_us"])
        w = max(2.0, x_for(seg["end_us"]) - x)
        stroke = _COLORS["overlap"] if seg.get("overlap") else "#0000"
        stroke_width = 2 if seg.get("overlap") else 0
        file_short = Path(seg["file"]).name if seg["file"] else seg["op"]
        parts.append(
            f'<g class="seg" data-op-id="{_html.escape(str(seg["op_id"]))}" '
            f'data-track="{_html.escape(seg["track"])}" '
            f'data-start-us="{seg["start_us"]}" data-end-us="{seg["end_us"]}" '
            f'data-file="{_html.escape(file_short)}" '
            f'data-op="{_html.escape(seg["op"])}" '
            f'data-overlap="{str(bool(seg.get("overlap"))).lower()}">'
        )
        parts.append(
            f'<rect x="{x:.1f}" y="{y + 6}" width="{w:.1f}" height="{track_height - 12}" '
            f'rx="3" ry="3" fill="{seg["color"]}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" '
            f'style="cursor:pointer; transition:opacity .15s;"/>'
        )
        # 텍스트 라벨 (박스 너비가 충분할 때만)
        if w > 30:
            label = file_short[:40]
            parts.append(
                f'<text x="{x + 5:.1f}" y="{y + track_height / 2 + 4}" fill="#0a0a0a" '
                f'font-size="11" font-family="sans-serif" style="pointer-events:none; font-weight:600;">'
                f'{_html.escape(label)}</text>'
            )
        parts.append('</g>')

    parts.append('</svg>')
    return "".join(parts)


# =========================================================================
# HTML 빌드
# =========================================================================


def _render_header(session, segments: list[dict], total_us: int, tracks: list[str]) -> str:
    name = _html.escape(session.draft_name)
    w = session.data.get("width", 0)
    h = session.data.get("height", 0)
    fps = session.data.get("fps", 0)
    duration = format_duration(total_us) if total_us else "0s"
    return (
        f'<header class="hdr">'
        f'<h1>{name}</h1>'
        f'<div class="meta">'
        f'<span><b>Resolution:</b> {w}&times;{h}</span>'
        f'<span><b>FPS:</b> {fps}</span>'
        f'<span><b>Duration:</b> {_html.escape(duration)}</span>'
        f'<span><b>Tracks:</b> {len(tracks)}</span>'
        f'<span><b>Segments:</b> {len(segments)}</span>'
        f'</div>'
        f'</header>'
    )


def _render_segment_table(segments: list[dict], thumbnails: dict[str, str | None]) -> str:
    rows: list[str] = []
    for seg in segments:
        file_short = Path(seg["file"]).name if seg["file"] else ""
        thumb_html = ""
        thumb_url = thumbnails.get(seg["op_id"])
        if thumb_url:
            thumb_html = f'<img class="thumb" src="{thumb_url}" alt=""/>'
        elif thumb_url is None and seg["type"] == "video":
            # --thumbs 켰는데 실패한 경우 placeholder
            if "thumbs_requested" in thumbnails:
                thumb_html = '<span class="thumb-placeholder">&#9634;</span>'
        overlap_badge = (
            '<span class="badge badge-overlap">OVERLAP</span>' if seg.get("overlap") else ""
        )
        rows.append(
            f'<tr data-op-id="{_html.escape(str(seg["op_id"]))}">'
            f'<td>{thumb_html}</td>'
            f'<td><code>{_html.escape(str(seg["op_id"]))}</code></td>'
            f'<td>{_html.escape(seg["op"])}</td>'
            f'<td>{_html.escape(seg["track"])}</td>'
            f'<td>{_html.escape(format_us(seg["start_us"]))}</td>'
            f'<td>{_html.escape(format_us(seg["end_us"]))}</td>'
            f'<td>{_html.escape(format_us(seg["duration_us"]))}</td>'
            f'<td class="file">{_html.escape(file_short)}</td>'
            f'<td>{overlap_badge}</td>'
            f'</tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="9" class="empty">(no segments)</td></tr>')
    return (
        '<section class="table-wrap"><h2>Segments</h2>'
        '<table class="seg-table"><thead><tr>'
        '<th>Thumb</th><th>ID</th><th>Op</th><th>Track</th>'
        '<th>Start</th><th>End</th><th>Duration</th><th>File</th><th></th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table></section>'
    )


def _render_gap_overlap_summary(gaps: list[dict], overlaps: list[dict]) -> str:
    if not gaps and not overlaps:
        return '<section class="issues ok">No gaps or overlaps detected.</section>'
    parts: list[str] = ['<section class="issues">']
    if overlaps:
        parts.append('<h2>Overlaps</h2><ul>')
        for o in overlaps:
            parts.append(
                f'<li>Track <b>{_html.escape(o["track"])}</b>: '
                f'<code>{_html.escape(str(o["a_id"]))}</code> &harr; '
                f'<code>{_html.escape(str(o["b_id"]))}</code> '
                f'({_html.escape(format_us(o["overlap_us"]))})</li>'
            )
        parts.append('</ul>')
    if gaps:
        parts.append('<h2>Gaps</h2><ul>')
        for g in gaps:
            parts.append(
                f'<li>Track <b>{_html.escape(g["track"])}</b>: '
                f'{_html.escape(format_us(g["start_us"]))} &rarr; '
                f'{_html.escape(format_us(g["end_us"]))} '
                f'({_html.escape(format_us(g["gap_us"]))})</li>'
            )
        parts.append('</ul>')
    parts.append('</section>')
    return "".join(parts)


_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
  background: #1a1a1a;
  color: #e5e5e5;
}
.container { max-width: 1400px; margin: 0 auto; padding: 24px; }
.hdr { border-bottom: 1px solid #333; padding-bottom: 16px; margin-bottom: 24px; }
.hdr h1 { margin: 0 0 12px 0; font-size: 24px; }
.meta { display: flex; flex-wrap: wrap; gap: 20px; color: #9ca3af; font-size: 14px; }
.meta b { color: #e5e5e5; font-weight: 600; }
.gantt-wrap {
  background: #242424;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin-bottom: 24px;
}
#gantt { width: 100%; height: auto; min-width: 900px; display: block; }
.legend {
  display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px;
  font-size: 12px; color: #9ca3af;
}
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-box {
  display: inline-block; width: 14px; height: 14px; border-radius: 2px;
  vertical-align: middle;
}
.seg rect.highlight {
  stroke: #fde047 !important;
  stroke-width: 3 !important;
}
.seg:hover rect { opacity: 0.75; }
#tooltip {
  position: fixed;
  pointer-events: none;
  background: #0a0a0a;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.4;
  color: #e5e5e5;
  display: none;
  z-index: 100;
  max-width: 320px;
}
#tooltip b { color: #fde047; }
.table-wrap { background: #242424; border: 1px solid #333; border-radius: 6px; padding: 16px; }
.table-wrap h2 { margin: 0 0 12px 0; font-size: 16px; }
.seg-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.seg-table th, .seg-table td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #2a2a2a; }
.seg-table th { background: #1e1e1e; color: #9ca3af; font-weight: 600; position: sticky; top: 0; }
.seg-table tbody tr { cursor: pointer; transition: background .1s; }
.seg-table tbody tr:hover { background: #2a2a2a; }
.seg-table tbody tr.selected { background: #323232; }
.seg-table .file { color: #9ca3af; font-family: monospace; font-size: 12px; }
.seg-table .empty { color: #666; text-align: center; padding: 24px 0; }
.thumb { width: 80px; height: 45px; object-fit: cover; border-radius: 2px; }
.thumb-placeholder {
  display: inline-block; width: 80px; height: 45px; text-align: center;
  line-height: 45px; background: #333; color: #666; border-radius: 2px; font-size: 20px;
}
.badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.badge-overlap { background: #ef4444; color: #fff; }
.issues { background: #242424; border: 1px solid #333; border-radius: 6px; padding: 16px; margin-bottom: 24px; }
.issues.ok { color: #2dd4bf; }
.issues h2 { font-size: 14px; margin: 0 0 8px 0; color: #ef4444; }
.issues ul { margin: 0; padding-left: 20px; }
.issues li { margin-bottom: 4px; font-size: 13px; }
code { background: #1e1e1e; padding: 1px 6px; border-radius: 3px; font-size: 12px; }
"""


_JS = r"""
(function () {
  var tooltip = document.getElementById('tooltip');
  var segs = document.querySelectorAll('#gantt .seg');
  var rows = document.querySelectorAll('.seg-table tbody tr');

  function showTooltip(e, g) {
    var opId = g.getAttribute('data-op-id') || '';
    var track = g.getAttribute('data-track') || '';
    var file = g.getAttribute('data-file') || '';
    var op = g.getAttribute('data-op') || '';
    var s = parseInt(g.getAttribute('data-start-us') || '0', 10);
    var e2 = parseInt(g.getAttribute('data-end-us') || '0', 10);
    var dur = e2 - s;
    var overlap = g.getAttribute('data-overlap') === 'true';
    function fmt(us) {
      if (!us) return '0s';
      var sec = us / 1e6;
      return sec >= 0.01 ? sec.toFixed(2) + 's' : us + 'us';
    }
    tooltip.innerHTML =
      '<b>' + op + '</b><br/>' +
      'id: ' + opId + '<br/>' +
      'track: ' + track + '<br/>' +
      'file: ' + file + '<br/>' +
      'start: ' + fmt(s) + '<br/>' +
      'end: ' + fmt(e2) + '<br/>' +
      'duration: ' + fmt(dur) +
      (overlap ? '<br/><span style="color:#ef4444"><b>OVERLAP</b></span>' : '');
    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top = (e.clientY + 14) + 'px';
  }

  segs.forEach(function (g) {
    g.addEventListener('mouseenter', function (e) { showTooltip(e, g); });
    g.addEventListener('mousemove', function (e) { showTooltip(e, g); });
    g.addEventListener('mouseleave', function () { tooltip.style.display = 'none'; });
    g.addEventListener('click', function () { selectById(g.getAttribute('data-op-id')); });
  });

  rows.forEach(function (tr) {
    tr.addEventListener('click', function () { selectById(tr.getAttribute('data-op-id')); });
  });

  function selectById(opId) {
    rows.forEach(function (r) { r.classList.toggle('selected', r.getAttribute('data-op-id') === opId); });
    segs.forEach(function (g) {
      var rect = g.querySelector('rect');
      if (!rect) return;
      rect.classList.toggle('highlight', g.getAttribute('data-op-id') === opId);
    });
  }
})();
"""


def build_preview_html(session, *, include_thumbs: bool = False) -> str:
    """세션 전체에 대한 self-contained HTML을 문자열로 반환."""
    segments = _collect_segments(session)
    gaps, overlaps = _compute_gaps_overlaps(segments)

    total_us = max((s["end_us"] for s in segments), default=0)

    # 트랙 순서 — op 출현 순서 유지 + V/A/T 정렬 적용
    seen_tracks: list[str] = []
    for s in segments:
        if s["track"] not in seen_tracks:
            seen_tracks.append(s["track"])
    tracks = sorted(seen_tracks, key=_track_sort_key)

    # 썸네일 추출
    thumbnails: dict[str, Any] = {}
    if include_thumbs:
        if not shutil.which("ffmpeg"):
            click.echo("[warn] ffmpeg not found on PATH — skipping thumbnails", err=True)
        else:
            thumbnails["thumbs_requested"] = True
            cache_dir = _default_thumb_cache()
            for seg in segments:
                if seg["type"] != "video":
                    continue
                f = seg.get("file")
                if not f:
                    continue
                thumb = _extract_thumbnail(f, time_s=0.0, cache_dir=cache_dir)
                thumbnails[seg["op_id"]] = thumb

    gantt_svg = _render_gantt_svg(segments, total_us, tracks)
    header_html = _render_header(session, segments, total_us, tracks)
    issues_html = _render_gap_overlap_summary(gaps, overlaps)
    table_html = _render_segment_table(segments, thumbnails)

    legend_html = (
        '<div class="legend">'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["video"]}"></span>Video/Image</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["audio"]}"></span>Audio</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["text_seg"]}"></span>Text</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["sticker"]}"></span>Sticker</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["effect"]}"></span>Effect</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["filter"]}"></span>Filter</span>'
        f'<span class="legend-item"><span class="legend-box" style="background:{_COLORS["overlap"]}; border:2px solid {_COLORS["overlap"]}"></span>Overlap</span>'
        '<span class="legend-item"><span class="legend-box" style="background:repeating-linear-gradient(45deg,#2a2a2a,#2a2a2a 3px,#3a3a3a 3px,#3a3a3a 6px)"></span>Gap</span>'
        '</div>'
    )

    title = _html.escape(f"CapCut Preview — {session.draft_name}")
    html_doc = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f'<title>{title}</title>\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n'
        '<body>\n'
        '<div id="tooltip"></div>\n'
        '<div class="container">\n'
        f'{header_html}\n'
        '<section class="gantt-wrap">\n'
        f'{legend_html}\n'
        f'{gantt_svg}\n'
        '</section>\n'
        f'{issues_html}\n'
        f'{table_html}\n'
        '</div>\n'
        f'<script>{_JS}</script>\n'
        '</body>\n'
        '</html>\n'
    )
    return html_doc


# =========================================================================
# click 커맨드
# =========================================================================


@click.command("preview", help="세션의 트랙/세그먼트 구조를 self-contained HTML 간트차트로 미리보기")
@click.option("-p", "--project", "project_path", required=True, help="세션 JSON 경로")
@click.option("-o", "--output", "output_path", default=None,
              help="HTML 저장 경로 (기본: 세션 파일 옆 <name>.preview.html)")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="저장 후 기본 브라우저로 자동 열기")
@click.option("--thumbs/--no-thumbs", default=False,
              help="각 비디오/이미지 첫 프레임을 ffmpeg로 추출해 인라인 (느림)")
@click.pass_context
def preview_cmd(ctx, project_path, output_path, open_browser, thumbs):
    session = load_session(project_path)

    if output_path:
        out = Path(output_path)
    else:
        out = session.path.with_suffix("").with_suffix(".preview.html")
        # 세션 경로가 ``.session.json`` 2중 suffix인 경우 정리
        # with_suffix 2회 호출로 ``.session`` 도 제거됨 — 위에서 처리

    html_doc = build_preview_html(session, include_thumbs=thumbs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")

    if open_browser:
        webbrowser.open(f"file://{out.resolve().as_posix()}")

    result = {
        "status": "ok",
        "output": str(out.resolve()),
        "bytes": out.stat().st_size,
        "segments": sum(1 for op in session.data.get("operations", []) if op.get("op") in CREATION_OPS),
        "thumbs": bool(thumbs),
    }
    output_result(result, ctx.obj["json"])
