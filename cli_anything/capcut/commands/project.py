"""project 그룹 — 세션 생성/조회/사용/종합."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.session import Session
from cli_anything.capcut.utils.capcut_backend import (
    get_default_draft_folder,
    require_draft_folder,
)

PRESETS = {
    "landscape": (1920, 1080),
    "portrait": (1080, 1920),
    "square": (1080, 1080),
    "4k": (3840, 2160),
    "9x16": (1080, 1920),
    "16x9": (1920, 1080),
    "1x1": (1080, 1080),
}


@click.group("project", help="프로젝트(세션) 생성/조회/관리")
def project_group():
    pass


@project_group.command("new", help="새 세션 생성")
@click.option("--name", "-n", required=True, help="드래프트 이름")
@click.option("--preset", type=click.Choice(list(PRESETS)), default="landscape")
@click.option("--width", type=int, default=None)
@click.option("--height", type=int, default=None)
@click.option("--fps", type=int, default=30, show_default=True)
@click.option("--draft-folder", default=None, help="CapCut 드래프트 루트 폴더")
@click.option("--output", "-o", default=None, help="세션 JSON 저장 위치")
@click.pass_context
def project_new(ctx, name, preset, width, height, fps, draft_folder, output):
    if width is None or height is None:
        w, h = PRESETS[preset]
        width = width or w
        height = height or h
    folder = require_draft_folder(draft_folder)
    session = Session.create(folder, name, width=width, height=height, fps=fps, output=output)
    output_result(
        {
            "status": "created",
            "session_path": str(session.path),
            "draft_folder": folder,
            "draft_name": name,
            "width": width,
            "height": height,
            "fps": fps,
        },
        ctx.obj["json"],
    )


@project_group.command("info", help="세션 요약")
@click.option("-p", "--project", "project_path", required=True)
@click.pass_context
def project_info(ctx, project_path):
    session = load_session(project_path)
    output_result(session.summary(), ctx.obj["json"])


@project_group.command("status", help="검증 + 갭/겹침 분석 포함 상태 (AI친화)")
@click.option("-p", "--project", "project_path", required=True)
@click.pass_context
def project_status(ctx, project_path):
    session = load_session(project_path)
    output_result(session.status(), ctx.obj["json"])


@project_group.command("clone", help="세션을 다른 경로로 복제")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-o", "--output", required=True, help="새 세션 파일 경로")
@click.pass_context
def project_clone(ctx, project_path, output):
    session = load_session(project_path)
    new_session = session.clone(output)
    output_result({"status": "cloned", "new_session_path": str(new_session.path)}, ctx.obj["json"])
