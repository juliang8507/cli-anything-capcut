"""alias 그룹 — 별칭 조회/검색."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import output_result
from cli_anything.capcut.core.alias_map import (
    list_aliases,
    list_enum_classes,
    resolve_alias,
    search_all_enums,
    search_enum,
)


@click.group("alias", help="enum 별칭 조회/검색")
def alias_group():
    pass


@alias_group.command("classes", help="별칭 지원 enum 카테고리 목록")
@click.pass_context
def alias_classes(ctx):
    output_result(list_enum_classes(), ctx.obj["json"])


@alias_group.command("resolve", help="영어 별칭을 한자 enum 이름으로 변환")
@click.option("--class", "enum_class_name", required=True)
@click.option("--name", required=True)
@click.pass_context
def alias_resolve(ctx, enum_class_name, name):
    try:
        resolved = resolve_alias(enum_class_name, name)
    except KeyError as e:
        raise click.ClickException(str(e))
    output_result({"input": name, "resolved": resolved, "class": enum_class_name},
                  ctx.obj["json"])


@alias_group.command("list", help="특정 enum의 모든 별칭")
@click.option("--class", "enum_class_name", required=True)
@click.pass_context
def alias_list(ctx, enum_class_name):
    try:
        aliases = list_aliases(enum_class_name)
    except KeyError as e:
        raise click.ClickException(str(e))
    output_result(aliases, ctx.obj["json"])


@alias_group.command("search", help="키워드로 enum 검색 (한자/영어 모두)")
@click.option("--class", "enum_class_name", default=None,
              help="특정 카테고리만 (생략 시 전체)")
@click.option("--keyword", "-k", required=True)
@click.option("--limit", type=int, default=20)
@click.pass_context
def alias_search(ctx, enum_class_name, keyword, limit):
    if enum_class_name:
        try:
            result = search_enum(enum_class_name, keyword, limit)
        except KeyError as e:
            raise click.ClickException(str(e))
    else:
        result = search_all_enums(keyword, limit)
    output_result(result, ctx.obj["json"])
