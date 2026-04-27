"""mask/background 그룹 — 비디오 세그먼트 마스크/배경."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


@click.group("mask", help="마스크 (원형/사각/하트 등)")
def mask_group():
    pass


@mask_group.command("add", help="비디오 세그먼트에 마스크 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--name", required=True,
              help="마스크 타입 (circle, rectangle, heart, star, linear, mirror)")
@click.option("--center-x", type=float, default=None, help="마스크 중심 X (픽셀)")
@click.option("--center-y", type=float, default=None, help="마스크 중심 Y (픽셀)")
@click.option("--size", type=float, default=None, help="주요 크기 (0~1, 기본 0.5)")
@click.option("--rotation", type=float, default=None, help="회전 각도")
@click.option("--feather", type=float, default=None, help="페더 0~100")
@click.option("--invert", is_flag=True, default=None)
@click.option("--rect-width", type=float, default=None,
              help="사각 마스크 너비 (사각 전용)")
@click.option("--round-corner", type=float, default=None,
              help="사각 마스크 라운드 0~100 (사각 전용)")
@click.pass_context
def mask_add(ctx, project_path, track, segment_ref, name, center_x, center_y, size,
             rotation, feather, invert, rect_width, round_corner):
    session = load_session(project_path)
    args = {
        "track": track,
        "segment_ref": segment_ref,
        "name": name,
        "center_x": center_x,
        "center_y": center_y,
        "size": size,
        "rotation": rotation,
        "feather": feather,
        "invert": invert,
        "rect_width": rect_width,
        "round_corner": round_corner,
    }
    result = session.append_operation("add_mask", args)
    output_result(result, ctx.obj["json"])


@click.group("background", help="비디오 세그먼트 배경 채우기")
def background_group():
    pass


@background_group.command("add", help="blur 또는 color 배경 채우기")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--fill-type", type=click.Choice(["blur", "color"]), default="blur")
@click.option("--blur", type=float, default=0.0625,
              help="블러 강도 0~1 (fill_type=blur)")
@click.option("--color", default="#00000000",
              help='배경색 hex (fill_type=color). 예: "#ff0000ff"')
@click.pass_context
def background_add(ctx, project_path, track, segment_ref, fill_type, blur, color):
    session = load_session(project_path)
    args = {
        "track": track,
        "segment_ref": segment_ref,
        "fill_type": fill_type,
        "blur": blur,
        "color": color,
    }
    result = session.append_operation("add_background", args)
    output_result(result, ctx.obj["json"])
