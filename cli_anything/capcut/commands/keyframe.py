"""keyframe 그룹 — 세그먼트 속성 키프레임."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result

PROPERTIES = [
    "alpha",
    "position_x",
    "position_y",
    "rotation",
    "scale_x",
    "scale_y",
    "uniform_scale",
    "volume",
]


@click.group("keyframe", help="키프레임")
def keyframe_group():
    pass


@keyframe_group.command("add", help="세그먼트의 특정 속성 키프레임 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True)
@click.option("--segment-ref", required=True)
@click.option("--property", "prop", required=True,
              type=click.Choice(PROPERTIES))
@click.option("--time", required=True, help='세그먼트 내 상대 시각 (예: "0s", "1s", "500ms")')
@click.option("--value", required=True, type=float)
@click.pass_context
def keyframe_add(ctx, project_path, track, segment_ref, prop, time, value):
    session = load_session(project_path)
    result = session.append_operation(
        "add_keyframe",
        {"track": track, "segment_ref": segment_ref,
         "property": prop, "time": time, "value": value},
    )
    output_result(result, ctx.obj["json"])
