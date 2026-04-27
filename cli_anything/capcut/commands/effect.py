"""effect 그룹 — 비디오 효과 + 필터."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.time_utils import resolve_start_time


@click.group("effect", help="비디오 효과/필터")
def effect_group():
    pass


@effect_group.command("add", help="씬/캐릭터 효과 추가 (vignette, soft, ...)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--name", required=True, help="효과 이름 (영어 별칭 또는 한자)")
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default="3s", show_default=True)
@click.option("--track", default=None, help="effect 트랙 이름")
@click.pass_context
def effect_add(ctx, project_path, name, start, duration, track):
    session = load_session(project_path)
    args = {
        "name": name,
        "start": resolve_start_time(session.data, start, track_name=track),
        "duration": duration,
        "track": track,
    }
    result = session.append_operation("add_effect", args)
    output_result(result, ctx.obj["json"])


@effect_group.command("add-filter", help="필터 추가 (warm, cinematic, bw, ...)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--name", required=True)
@click.option("-s", "--start", default="auto", show_default=True)
@click.option("-d", "--duration", default="3s", show_default=True)
@click.option("--track", default=None)
@click.option("--intensity", type=float, default=1.0, show_default=True)
@click.pass_context
def effect_add_filter(ctx, project_path, name, start, duration, track, intensity):
    session = load_session(project_path)
    args = {
        "name": name,
        "start": resolve_start_time(session.data, start, track_name=track),
        "duration": duration,
        "track": track,
        "intensity": intensity if intensity != 1.0 else None,
    }
    result = session.append_operation("add_filter", args)
    output_result(result, ctx.obj["json"])
