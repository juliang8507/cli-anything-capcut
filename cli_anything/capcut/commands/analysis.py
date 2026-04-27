"""분석 커맨드 — timeline, stats, gap/overlap, segments-at, history."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.time_utils import parse_time_value


@click.command("timeline", help="ASCII 타임라인")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--width", type=int, default=60)
@click.pass_context
def timeline_cmd(ctx, project_path, width):
    session = load_session(project_path)
    result = session.timeline(width)
    if ctx.obj["json"]:
        output_result(result, True)
    else:
        click.echo(result["timeline_text"])


@click.command("stats", help="프로젝트 통계 (지속시간/트랙/미디어 파일)")
@click.option("-p", "--project", "project_path", required=True)
@click.pass_context
def stats_cmd(ctx, project_path):
    session = load_session(project_path)
    output_result(session.stats(), ctx.obj["json"])


@click.command("history", help="op 히스토리")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--filter", "filter_op", default=None, help="op 타입 부분 매치")
@click.pass_context
def history_cmd(ctx, project_path, filter_op):
    session = load_session(project_path)
    output_result(session.history(filter_op), ctx.obj["json"])


@click.command("gap-detect", help="트랙 내 갭 찾기")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", default=None)
@click.pass_context
def gap_detect_cmd(ctx, project_path, track):
    session = load_session(project_path)
    output_result(session.gap_detect(track), ctx.obj["json"])


@click.command("overlap-detect", help="트랙 내 겹침 찾기")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", default=None)
@click.pass_context
def overlap_detect_cmd(ctx, project_path, track):
    session = load_session(project_path)
    output_result(session.overlap_detect(track), ctx.obj["json"])


@click.command("segments-at", help="특정 시각에 활성인 세그먼트")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--time", required=True, help='예: "5s", "1500000us"')
@click.pass_context
def segments_at_cmd(ctx, project_path, time):
    session = load_session(project_path)
    time_us = parse_time_value(time)
    output_result(session.segments_at_time(time_us), ctx.obj["json"])


@click.command("undo", help="마지막 N개 op 제거")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-n", "--count", default=1, type=int)
@click.option("--type", "op_type", default=None)
@click.pass_context
def undo_cmd(ctx, project_path, count, op_type):
    session = load_session(project_path)
    removed = session.undo(count, op_type)
    output_result({"status": "undone", "count": len(removed), "removed": removed},
                  ctx.obj["json"])


@click.command("validate", help="replay dry-run")
@click.option("-p", "--project", "project_path", required=True)
@click.pass_context
def validate_cmd(ctx, project_path):
    session = load_session(project_path)
    output_result(session.validate(), ctx.obj["json"])
