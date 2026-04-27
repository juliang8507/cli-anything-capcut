"""recipe 그룹 — JSON 레시피 import/export/validate."""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import load_session, output_result
from cli_anything.capcut.core.recipe import (
    RecipeError,
    apply_recipe,
    load_recipe,
    validate_recipe,
)


@click.command("import-recipe", help="JSON 레시피를 세션에 일괄 적용")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--skip-errors", is_flag=True, default=False)
@click.pass_context
def import_recipe_cmd(ctx, project_path, file, skip_errors):
    session = load_session(project_path)
    try:
        recipe = load_recipe(file)
        result = apply_recipe(session, recipe, skip_errors=skip_errors)
    except RecipeError as e:
        raise click.ClickException(str(e))
    output_result(
        {"status": "applied", "applied_count": result["applied"],
         "errors": result["errors"]},
        ctx.obj["json"],
    )


@click.command("export-recipe", help="현재 세션을 JSON 레시피로 출력")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-o", "--output", default=None, help="저장할 파일 경로 (생략 시 stdout)")
@click.pass_context
def export_recipe_cmd(ctx, project_path, output):
    session = load_session(project_path)
    recipe = session.export_recipe()
    if output:
        Path(output).write_text(json.dumps(recipe, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        output_result({"status": "exported", "path": output, "op_count": len(recipe["operations"])},
                      ctx.obj["json"])
    else:
        click.echo(json.dumps(recipe, ensure_ascii=False, indent=2))


@click.command("validate-recipe", help="레시피 구조만 검증 (replay 없이)")
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def validate_recipe_cmd(ctx, file):
    try:
        recipe = load_recipe(file)
    except RecipeError as e:
        raise click.ClickException(str(e))
    output_result(validate_recipe(recipe), ctx.obj["json"])


@click.command("export-script", help="세션을 재현 가능한 CLI 스크립트로 출력")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-o", "--output", default=None)
@click.option("--cli-cmd", default="cli-anything-capcut")
@click.pass_context
def export_script_cmd(ctx, project_path, output, cli_cmd):
    session = load_session(project_path)
    script = session.export_script(cli_cmd=cli_cmd)
    if output:
        Path(output).write_text(script, encoding="utf-8")
        output_result({"status": "exported", "path": output}, ctx.obj["json"])
    else:
        click.echo(script)


# =========================================================================
# Op edit (edit/delete/reorder/batch)
# =========================================================================


@click.command("edit-op", help="op의 args partial 업데이트")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--index", type=int, required=True)
@click.option("--args", "args_json", required=True, help="JSON 형식의 새 args")
@click.pass_context
def edit_op_cmd(ctx, project_path, index, args_json):
    from cli_anything.capcut.commands.helpers import parse_json_option

    session = load_session(project_path)
    new_args = parse_json_option(args_json, "args") or {}
    result = session.edit_operation(index, new_args)
    output_result(result, ctx.obj["json"])


@click.command("delete-op", help="op 삭제")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--index", type=int, required=True)
@click.pass_context
def delete_op_cmd(ctx, project_path, index):
    session = load_session(project_path)
    result = session.delete_operation(index)
    output_result(result, ctx.obj["json"])


@click.command("reorder-op", help="op 순서 이동")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--from", "from_index", type=int, required=True)
@click.option("--to", "to_index", type=int, required=True)
@click.pass_context
def reorder_op_cmd(ctx, project_path, from_index, to_index):
    session = load_session(project_path)
    result = session.reorder_operation(from_index, to_index)
    output_result(result, ctx.obj["json"])


@click.command("batch", help="여러 op를 한 번에 실행 (JSON 파일)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--skip-errors", is_flag=True, default=False)
@click.pass_context
def batch_cmd(ctx, project_path, file, skip_errors):
    session = load_session(project_path)
    operations = json.loads(Path(file).read_text(encoding="utf-8"))
    if not isinstance(operations, list):
        raise click.ClickException("batch 파일은 JSON 배열이어야 함")
    result = session.do_batch(operations, skip_errors=skip_errors)
    output_result(result, ctx.obj["json"])


# =========================================================================
# Session merge
# =========================================================================


@click.command("merge-session", help="다른 세션을 현재 세션에 합치기")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--other", "other_path", required=True, type=click.Path(exists=True))
@click.option("--offset", "offset", default="0s", help="다른 세션의 시간을 이 값만큼 미루기")
@click.pass_context
def merge_session_cmd(ctx, project_path, other_path, offset):
    from cli_anything.capcut.core.time_utils import parse_time_value

    session = load_session(project_path)
    other = load_session(other_path)
    offset_us = parse_time_value(offset)
    result = session.merge(other, offset_us=offset_us)
    output_result(result, ctx.obj["json"])


@click.command("diff-session", help="두 세션 op 비교")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--other", "other_path", required=True, type=click.Path(exists=True))
@click.pass_context
def diff_session_cmd(ctx, project_path, other_path):
    session = load_session(project_path)
    other = load_session(other_path)
    result = session.diff(other)
    output_result(
        {"added": len(result["added"]), "removed": len(result["removed"]),
         "changed": len(result["changed"]), "details": result},
        ctx.obj["json"],
    )
