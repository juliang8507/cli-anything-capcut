"""track 그룹 — 트랙 추가."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


@click.group("track", help="트랙 관리")
def track_group():
    pass


@track_group.command("add", help="트랙 생성")
@click.option("-p", "--project", "project_path", required=True)
@click.option(
    "--type", "track_type", required=True,
    type=click.Choice(["video", "audio", "text", "effect", "filter", "sticker"]),
)
@click.option("--name", default=None)
@click.pass_context
def track_add(ctx, project_path, track_type, name):
    session = load_session(project_path)
    result = session.append_operation("add_track", {"type": track_type, "name": name})
    output_result(result, ctx.obj["json"])
