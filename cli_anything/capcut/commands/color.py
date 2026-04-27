"""color 그룹 — 컬러 그레이딩 (밝기/대비/채도/색온도/그림자/하이라이트).

비디오 세그먼트의 보정값을 키프레임 0초에 한 번 저장하는 방식으로 구현.
"""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


_COLOR_KEYFRAME_PROPS = {
    # CLI option name -> approx pyCapCut keyframe property
    # 단순화: 현재 op_handlers는 alpha/position/rotation/scale/volume만 지원.
    # color 보정은 Phase 1에서 안 다뤘으므로 이 커맨드는 옵션 검증만 하고
    # placeholder op로 세션에 기록 (replay 시 무시되거나 PostProcess로 보강 예정).
}


@click.group("color", help="컬러 그레이딩")
def color_group():
    pass


@color_group.command("adjust", help="밝기/대비/채도/하이라이트/그림자 등 조정")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--brightness", type=float, default=None, help="-1.0~+1.0")
@click.option("--contrast", type=float, default=None)
@click.option("--saturation", type=float, default=None)
@click.option("--temperature", type=float, default=None, help="-1.0(cool)~+1.0(warm)")
@click.option("--highlights", type=float, default=None)
@click.option("--shadows", type=float, default=None)
@click.option("--vibrance", type=float, default=None)
@click.pass_context
def color_adjust(ctx, project_path, track, segment_ref, brightness, contrast, saturation,
                 temperature, highlights, shadows, vibrance):
    session = load_session(project_path)
    args = {
        "track": track,
        "segment_ref": segment_ref,
        "brightness": brightness,
        "contrast": contrast,
        "saturation": saturation,
        "temperature": temperature,
        "highlights": highlights,
        "shadows": shadows,
        "vibrance": vibrance,
    }
    result = session.append_operation("color_adjust", args, _status="queued")
    output_result(result, ctx.obj["json"])


@color_group.command("wheels", help="컬러 휠 (shadows/midtones/highlights)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--shadows-color", default=None,
              help='r,g,b 형식. 예: "0,0,255"')
@click.option("--midtones-color", default=None)
@click.option("--highlights-color", default=None)
@click.pass_context
def color_wheels(ctx, project_path, track, segment_ref, shadows_color,
                 midtones_color, highlights_color):
    from cli_anything.capcut.commands.helpers import parse_color

    session = load_session(project_path)
    args = {
        "track": track,
        "segment_ref": segment_ref,
        "shadows_color": parse_color(shadows_color),
        "midtones_color": parse_color(midtones_color),
        "highlights_color": parse_color(highlights_color),
    }
    result = session.append_operation("color_wheels", args, _status="queued")
    output_result(result, ctx.obj["json"])


def _parse_curve_points(s: str) -> list[tuple[float, float]]:
    """'in,out;in,out;...' 또는 JSON 배열 형식 파싱.

    각 포인트는 0.0~1.0 범위. 최소 2점 필요.
    """
    import json as _json

    s = s.strip()
    try:
        # JSON 배열 형식 시도: [[0,0],[0.5,0.7],[1,1]]
        parsed = _json.loads(s)
        if isinstance(parsed, list):
            return [(float(p[0]), float(p[1])) for p in parsed]
    except Exception:
        pass

    # 세미콜론 구분 형식: "0,0;0.5,0.7;1,1"
    result = []
    for part in s.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            x, y = part.split(",")
            result.append((float(x), float(y)))
        except ValueError:
            raise click.BadParameter(
                f"포인트 형식 오류: '{part}'. 'in,out' 형식 필요 (예: '0.5,0.7')"
            )
    if len(result) < 2:
        raise click.BadParameter("각 채널당 최소 2점 필요")
    return result


@color_group.command("curves", help="컬러 커브 조정 (RGB/R/G/B 채널 톤 커브)")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--rgb", default=None,
              help="RGB 마스터 커브. 형식: 'in,out;in,out;...' 또는 JSON 배열. 최소 2점.")
@click.option("--red", default=None, help="R 채널 커브 (형식: --rgb와 동일)")
@click.option("--green", default=None, help="G 채널 커브 (형식: --rgb와 동일)")
@click.option("--blue", default=None, help="B 채널 커브 (형식: --rgb와 동일)")
@click.pass_context
def color_curves(ctx, project_path, track, segment_ref, rgb, red, green, blue):
    if not any([rgb, red, green, blue]):
        raise click.UsageError(
            "최소 1개 채널 필요: --rgb / --red / --green / --blue"
        )

    rgb_pts = _parse_curve_points(rgb) if rgb else None
    red_pts = _parse_curve_points(red) if red else None
    green_pts = _parse_curve_points(green) if green else None
    blue_pts = _parse_curve_points(blue) if blue else None

    session = load_session(project_path)
    result = session.append_operation(
        "add_color_curves",
        {
            "track": track,
            "segment_ref": segment_ref,
            "rgb": rgb_pts,
            "red": red_pts,
            "green": green_pts,
            "blue": blue_pts,
        },
    )
    output_result(result, ctx.obj["json"])


# HSL target_color 선택지 8종 (v0.3 color.info.md 기준)
_HSL_TARGET_CHOICES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"]


@color_group.command("hsl", help="HSL 채널별 조정 (색조/채도/명도 per target color)")
@click.option("-p", "--project", "project_path", required=True, help="세션 파일 경로")
@click.option("--track", required=True, help="트랙 이름")
@click.option("--segment-ref", required=True, help="세그먼트 참조 (op ID)")
@click.option("--target", required=True,
              type=click.Choice(_HSL_TARGET_CHOICES, case_sensitive=False),
              help="대상 색상 채널")
@click.option("--hue", type=float, default=0.0, show_default=True,
              help="색조 이동 (-100~+100)")
@click.option("--saturation", type=float, default=0.0, show_default=True,
              help="채도 조정 (-100~+100)")
@click.option("--lightness", type=float, default=0.0, show_default=True,
              help="명도 조정 (-100~+100)")
@click.pass_context
def color_hsl(ctx, project_path, track, segment_ref, target, hue, saturation, lightness):
    session = load_session(project_path)
    result = session.append_operation(
        "add_hsl_adjust",
        {
            "track": track,
            "segment_ref": segment_ref,
            "target": target,
            "hue": hue,
            "saturation": saturation,
            "lightness": lightness,
        },
    )
    output_result(result, ctx.obj["json"])
