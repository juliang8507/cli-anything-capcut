"""sticker 그룹 — 스티커 세그먼트."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import (
    load_session,
    output_result,
    resolve_clip_settings,
)
from cli_anything.capcut.core.time_utils import resolve_start_time


@click.group("sticker", help="스티커 세그먼트")
def sticker_group():
    pass


@sticker_group.command("add", help="이미지를 스티커로 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default="3s", show_default=True)
@click.option("--track", default=None)
@click.option("--clip-settings", default=None, help="프리셋 또는 JSON")
@click.pass_context
def sticker_add(ctx, project_path, file, start, duration, track, clip_settings):
    session = load_session(project_path)
    args = {
        "file": file,
        "start": resolve_start_time(session.data, start, track_name=track),
        "duration": duration,
        "track": track,
        "clip_settings": resolve_clip_settings(clip_settings),
    }
    result = session.append_operation("add_sticker", args)
    output_result(result, ctx.obj["json"])
