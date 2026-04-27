"""cli-anything-capcut 진입점.

서브커맨드 그룹들은 ``commands/*.py`` 에서 정의되고 여기서 루트 ``cli`` 그룹에
등록된다. 그룹마다 독립적이라 추가/제거가 쉽다.

빠른 사용::

    cli-anything-capcut project new --name my-draft
    cli-anything-capcut track add -p my-draft.session.json --type video --name V1
    cli-anything-capcut image add -p ... -f clip.png --start auto --duration 3s --track V1
    cli-anything-capcut save -p my-draft.session.json
    cli-anything-capcut repl                 # 인터랙티브 모드
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows 콘솔(cp949) 한글/특수문자 깨짐 방지
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click
import pycapcut as cc

from cli_anything.capcut import __version__
from cli_anything.capcut.commands.agent_cmds import agent_group
from cli_anything.capcut.commands.alias_cmds import alias_group
from cli_anything.capcut.commands.asset import asset_group
from cli_anything.capcut.commands.analysis import (
    gap_detect_cmd,
    history_cmd,
    overlap_detect_cmd,
    segments_at_cmd,
    stats_cmd,
    timeline_cmd,
    undo_cmd,
    validate_cmd,
)
from cli_anything.capcut.commands.color import color_group
from cli_anything.capcut.commands.effect import effect_group
from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.commands.keyframe import keyframe_group
from cli_anything.capcut.commands.mask import background_group, mask_group
from cli_anything.capcut.commands.media import (
    audio_group,
    image_group,
    media_info_cmd,
    staging_group,
    video_group,
)
from cli_anything.capcut.commands.plan import plan_cmd, plan_refine_cmd
from cli_anything.capcut.commands.preset import preset_group
from cli_anything.capcut.commands.preview import preview_cmd
from cli_anything.capcut.commands.project import project_group
from cli_anything.capcut.commands.render import render_cmd
from cli_anything.capcut.commands.render_headless import render_headless_cmd
from cli_anything.capcut.commands.review import review_cmd
from cli_anything.capcut.commands.session_utils import session_group
from cli_anything.capcut.commands.style import style_group
from cli_anything.capcut.commands.recipe_cmds import (
    batch_cmd,
    delete_op_cmd,
    diff_session_cmd,
    edit_op_cmd,
    export_recipe_cmd,
    export_script_cmd,
    import_recipe_cmd,
    merge_session_cmd,
    reorder_op_cmd,
    validate_recipe_cmd,
)
from cli_anything.capcut.commands.sticker import sticker_group
from cli_anything.capcut.commands.text import srt_group, text_group
from cli_anything.capcut.commands.track import track_group
from cli_anything.capcut.core.postprocess import apply_postprocess
from cli_anything.capcut.core.session import SessionError
from cli_anything.capcut.utils.capcut_backend import (
    get_default_draft_folder,
    require_draft_folder,
)


# =========================================================================
# 루트 그룹
# =========================================================================


@click.group(
    invoke_without_command=True,
    help="cli-anything-capcut - scriptable CapCut / JianYing draft generation.\n\n"
         "처음이면: `cli-anything-capcut diagnose` 로 환경 점검 후 "
         "`cli-anything-capcut project new --name X` 로 시작하세요.",
)
@click.version_option(__version__, "-V", "--version", prog_name="cli-anything-capcut")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
@click.option("--debug", is_flag=True, default=False,
              help="내부 동작 로그 출력 (CAPCUT_DEBUG=1 환경변수도 동작)")
@click.pass_context
def cli(ctx: click.Context, as_json: bool, debug: bool):
    import logging
    import os

    level = logging.DEBUG if (debug or os.environ.get("CAPCUT_DEBUG")) else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    ctx.obj["debug"] = debug
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =========================================================================
# save / diagnose / repl
# =========================================================================


@cli.command("save", help="세션 replay → CapCut 드래프트 저장 → postprocess 패치")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--dry-run", is_flag=True, help="저장 없이 replay만")
@click.option("--skip-errors", is_flag=True, help="실패한 op 건너뛰고 계속")
@click.option("--auto-fix", is_flag=True,
              help="실패 op를 격리(quarantine)하고 반복 재replay. --skip-errors 상위 호환")
@click.option("--max-attempts", type=int, default=3, show_default=True,
              help="--auto-fix 재시도 횟수 한도")
@click.pass_context
def save_cmd(ctx, project_path, dry_run, skip_errors, auto_fix, max_attempts):
    from cli_anything.capcut.core.time_utils import format_duration

    session = load_session(project_path)

    if auto_fix:
        from cli_anything.capcut.core.auto_fix import save_with_auto_fix

        try:
            result = save_with_auto_fix(
                session, dry_run=dry_run, max_attempts=max_attempts,
            )
        except SessionError as e:
            raise click.ClickException(str(e))
        output_result(result, ctx.obj["json"])
        return

    try:
        if skip_errors:
            script, replay_errors = session.replay_skip_errors()
        else:
            script = session.replay()
            replay_errors = []
    except SessionError as e:
        raise click.ClickException(str(e))

    if dry_run:
        output_result(
            {
                "status": "dry_run_ok",
                "operation_count": session.operation_count,
                "tracks": list(script.tracks.keys()),
                "duration": format_duration(int(script.duration)),
                "replay_errors": replay_errors,
            },
            ctx.obj["json"],
        )
        return

    Path(session.draft_folder).mkdir(parents=True, exist_ok=True)
    draft_folder_obj = cc.DraftFolder(session.draft_folder)
    fresh = draft_folder_obj.create_draft(
        session.draft_name,
        session.data["width"],
        session.data["height"],
        session.data["fps"],
        allow_replace=True,
    )
    target = Path(fresh.save_path)
    script.dump(str(target))
    session.save()

    # pyCapCut이 못 잡는 필드들 직접 패치
    post = apply_postprocess(target, session.data)

    output_result(
        {
            "status": "saved",
            "draft_path": str(target.parent),
            "draft_content_json": str(target),
            "operation_count": session.operation_count,
            "postprocess_applied": post.get("applied", 0),
            "postprocess_warnings": post.get("warnings", []),
            "replay_errors": replay_errors,
        },
        ctx.obj["json"],
    )


@cli.command("diagnose", help="환경 점검")
@click.pass_context
def diagnose_cmd(ctx):
    from cli_anything.capcut.core.time_utils import is_ffprobe_available

    output_result(
        {
            "cli_version": __version__,
            "pycapcut_version": getattr(cc, "__version__", "unknown"),
            "draft_folder": get_default_draft_folder(),
            "ffprobe_available": is_ffprobe_available(),
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
        ctx.obj["json"],
    )


@cli.command("repl", help="인터랙티브 REPL 모드")
@click.option("--draft-folder", default=None)
@click.pass_context
def repl_cmd(ctx, draft_folder):
    from cli_anything.capcut.utils.repl_skin import run_repl

    folder = draft_folder or get_default_draft_folder()
    run_repl(cli, draft_folder=folder)


# =========================================================================
# 그룹/커맨드 등록
# =========================================================================

# 그룹
cli.add_command(project_group)
cli.add_command(track_group)
cli.add_command(video_group)
cli.add_command(image_group)
cli.add_command(audio_group)
cli.add_command(text_group)
cli.add_command(srt_group)
cli.add_command(sticker_group)
cli.add_command(effect_group)
cli.add_command(keyframe_group)
cli.add_command(mask_group)
cli.add_command(background_group)
cli.add_command(color_group)
cli.add_command(alias_group)
cli.add_command(agent_group)
cli.add_command(asset_group)
cli.add_command(preset_group)
cli.add_command(session_group)
cli.add_command(staging_group)
cli.add_command(style_group)

# 단독 커맨드
cli.add_command(undo_cmd)
cli.add_command(history_cmd)
cli.add_command(validate_cmd)
cli.add_command(timeline_cmd)
cli.add_command(stats_cmd)
cli.add_command(gap_detect_cmd)
cli.add_command(overlap_detect_cmd)
cli.add_command(segments_at_cmd)

cli.add_command(import_recipe_cmd)
cli.add_command(export_recipe_cmd)
cli.add_command(validate_recipe_cmd)
cli.add_command(export_script_cmd)
cli.add_command(edit_op_cmd)
cli.add_command(delete_op_cmd)
cli.add_command(reorder_op_cmd)
cli.add_command(batch_cmd)
cli.add_command(merge_session_cmd)
cli.add_command(diff_session_cmd)

cli.add_command(media_info_cmd)
cli.add_command(render_cmd)
cli.add_command(render_headless_cmd)
cli.add_command(preview_cmd)
cli.add_command(plan_cmd)
cli.add_command(plan_refine_cmd)
cli.add_command(review_cmd)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
