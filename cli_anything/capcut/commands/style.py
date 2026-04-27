"""style 그룹 — 스타일 프리셋 저장/조회/삭제/백업/일괄적용.

v0.4.1: 카테고리 ``text`` / ``video`` / ``audio`` 지원 + ``apply-video``,
``apply-audio`` 서브커맨드 신규.

저장 위치: ``~/.capcut_cli/styles.json`` (JSON, 의존성 없음).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import (
    load_session,
    output_result,
    parse_color,
    parse_json_option,
    resolve_clip_settings,
)
from cli_anything.capcut.core import style_registry

_CATEGORY_CHOICE = click.Choice(list(style_registry.CATEGORIES))


@click.group("style", help="스타일 프리셋 (text/video/audio) 저장·조회·삭제·일괄적용")
def style_group():
    pass


# =========================================================================
# list / show
# =========================================================================


@style_group.command("list", help="저장된 + 내장 스타일 목록 (--category 로 필터)")
@click.option("--category", type=_CATEGORY_CHOICE, default=None,
              help="text/video/audio. 생략 시 전체")
@click.pass_context
def style_list(ctx, category):
    rows = style_registry.list_styles(category)
    if ctx.obj.get("json"):
        output_result(rows, True)
        return
    if not rows:
        click.echo("(저장된 스타일 없음)")
        return

    # 카테고리별로 나눠 출력
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    for cat in style_registry.CATEGORIES:
        section = by_cat.get(cat, [])
        if not section:
            continue
        click.echo(f"== {cat.upper()} ==")
        if cat == "text":
            click.echo(f"  {'NAME':<22} {'BUILTIN':<8} {'FONT':<16} {'SIZE':<6} COLOR")
            for r in section:
                color = r.get("color")
                color_s = ",".join(str(c) for c in color) if isinstance(color, (list, tuple)) else "-"
                click.echo(
                    f"  {r['name']:<22} "
                    f"{'yes' if r['builtin'] else 'no':<8} "
                    f"{str(r.get('font') or '-'):<16} "
                    f"{str(r.get('size') or '-'):<6} "
                    f"{color_s}"
                )
        elif cat == "video":
            click.echo(f"  {'NAME':<22} {'BUILTIN':<8} {'FILTER':<14} {'INTRO':<10} {'OUTRO':<10} COLOR")
            for r in section:
                click.echo(
                    f"  {r['name']:<22} "
                    f"{'yes' if r['builtin'] else 'no':<8} "
                    f"{str(r.get('filter') or '-'):<14} "
                    f"{str(r.get('intro') or '-'):<10} "
                    f"{str(r.get('outro') or '-'):<10} "
                    f"{'yes' if r.get('has_color') else 'no'}"
                )
        elif cat == "audio":
            click.echo(f"  {'NAME':<22} {'BUILTIN':<8} {'VOL':<6} {'FADE_IN':<10} {'FADE_OUT':<10} EFFECT")
            for r in section:
                click.echo(
                    f"  {r['name']:<22} "
                    f"{'yes' if r['builtin'] else 'no':<8} "
                    f"{str(r.get('volume') or '-'):<6} "
                    f"{str(r.get('fade_in') or '-'):<10} "
                    f"{str(r.get('fade_out') or '-'):<10} "
                    f"{str(r.get('effect') or '-')}"
                )
        click.echo("")


@style_group.command("show", help="스타일 상세 JSON")
@click.argument("name")
@click.option("--category", type=_CATEGORY_CHOICE, default="text", show_default=True)
@click.pass_context
def style_show(ctx, name, category):
    try:
        spec = style_registry.get_style(name, category=category)
    except KeyError:
        raise click.ClickException(f"스타일 '{name}' (카테고리 {category}) 없음")
    output_result(spec, ctx.obj.get("json", False))


# =========================================================================
# save
# =========================================================================


@style_group.command("save", help="스타일 저장 (옵션들을 한 프리셋으로 묶기)")
@click.argument("name")
@click.option("--category", type=_CATEGORY_CHOICE, default="text", show_default=True,
              help="text/video/audio 중 어느 카테고리에 저장할지")
# --- text 전용 옵션 ---
@click.option("--font", default=None)
@click.option("--size", type=float, default=None)
@click.option("--bold/--no-bold", default=None)
@click.option("--italic/--no-italic", default=None)
@click.option("--underline/--no-underline", default=None)
@click.option("--align", type=click.Choice(["left", "center", "right"]), default=None)
@click.option("--color", default=None, help='예: "255,255,255" 또는 "[1,1,1]"')
@click.option("--letter-spacing", type=float, default=None)
@click.option("--line-spacing", type=float, default=None)
@click.option("--border", default=None, help='JSON: \'{"alpha":1.0,"color":[0,0,0],"width":0.08}\'')
@click.option("--shadow", default=None, help='JSON: \'{"alpha":0.9,"color":[0,0,0],"distance":5,"angle":315}\'')
@click.option("--clip-settings", default=None, help="프리셋(subtitle-bottom 등) 또는 JSON")
# --- video 전용 옵션 ---
@click.option("--filter", "filter_json", default=None,
              help='(video) JSON: \'{"name":"cinematic","intensity":40}\'')
@click.option("--animation-intro", default=None,
              help='(video) JSON: \'{"name":"fade_in","duration":"0.5s"}\'')
@click.option("--animation-outro", default=None,
              help='(video) JSON: \'{"name":"fade_out","duration":"0.5s"}\'')
@click.option("--color-json", default=None,
              help='(video) color_adjust JSON: \'{"brightness":5,"contrast":10}\'')
# --- audio 전용 옵션 ---
@click.option("--volume", type=float, default=None, help="(audio) 0.0~1.0")
@click.option("--fade-in", default=None, help="(audio) 예: '0.3s'")
@click.option("--fade-out", default=None, help="(audio) 예: '0.5s'")
@click.option("--effect", "effect_json", default=None,
              help='(audio) JSON: \'{"name":"noise-reduction"}\'')
# --- 공통 ---
@click.option("--description", default=None, help="주석 — list에서 보여짐")
@click.option("--overwrite", is_flag=True, default=False)
@click.pass_context
def style_save(ctx, name, category,
               font, size, bold, italic, underline, align, color,
               letter_spacing, line_spacing, border, shadow, clip_settings,
               filter_json, animation_intro, animation_outro, color_json,
               volume, fade_in, fade_out, effect_json,
               description, overwrite):
    spec: dict = {}

    if category == "text":
        if font is not None:
            spec["font"] = font
        if size is not None:
            spec["size"] = size
        if bold is not None:
            spec["bold"] = bold
        if italic is not None:
            spec["italic"] = italic
        if underline is not None:
            spec["underline"] = underline
        if align is not None:
            spec["align"] = align

        color_arr = parse_color(color)
        if color_arr is not None:
            spec["color"] = color_arr
        if letter_spacing is not None:
            spec["letter_spacing"] = letter_spacing
        if line_spacing is not None:
            spec["line_spacing"] = line_spacing

        border_dict = parse_json_option(border, "border")
        if border_dict is not None:
            spec["border"] = border_dict
        shadow_dict = parse_json_option(shadow, "shadow")
        if shadow_dict is not None:
            spec["shadow"] = shadow_dict

        clip_dict = resolve_clip_settings(clip_settings)
        if clip_dict is not None:
            spec["clip_settings"] = clip_dict

    elif category == "video":
        filt = parse_json_option(filter_json, "filter")
        if filt is not None:
            spec["filter"] = filt
        intro = parse_json_option(animation_intro, "animation-intro")
        if intro is not None:
            spec["animation_intro"] = intro
        outro = parse_json_option(animation_outro, "animation-outro")
        if outro is not None:
            spec["animation_outro"] = outro
        cj = parse_json_option(color_json, "color-json")
        if cj is not None:
            spec["color"] = cj

    elif category == "audio":
        if volume is not None:
            spec["volume"] = volume
        if fade_in is not None:
            spec["fade_in"] = fade_in
        if fade_out is not None:
            spec["fade_out"] = fade_out
        eff = parse_json_option(effect_json, "effect")
        if eff is not None:
            spec["effect"] = eff

    if description is not None:
        spec["description"] = description

    if not spec:
        raise click.ClickException(
            f"저장할 속성이 없음 (category={category}). "
            "카테고리에 맞는 옵션을 하나 이상 지정."
        )

    try:
        saved = style_registry.save_style(
            name, spec, category=category, overwrite=overwrite,
        )
    except ValueError as e:
        raise click.ClickException(str(e))

    output_result(
        {"status": "saved", "name": name, "category": category, "spec": saved},
        ctx.obj.get("json", False),
    )


# =========================================================================
# delete
# =========================================================================


@style_group.command("delete", help="사용자 저장 스타일 삭제 (내장은 삭제 불가)")
@click.argument("name")
@click.option("--category", type=_CATEGORY_CHOICE, default="text", show_default=True)
@click.pass_context
def style_delete(ctx, name, category):
    ok = style_registry.delete_style(name, category=category)
    if not ok:
        raise click.ClickException(
            f"삭제 실패: '{name}' (카테고리 {category}) 이 없거나 내장 프리셋임."
        )
    output_result(
        {"status": "deleted", "name": name, "category": category},
        ctx.obj.get("json", False),
    )


# =========================================================================
# export / import
# =========================================================================


@style_group.command("export", help="사용자 저장분 JSON 파일로 백업")
@click.option("-o", "--output", required=True, type=click.Path(dir_okay=False))
@click.option("--category", type=_CATEGORY_CHOICE, default=None,
              help="특정 카테고리만 export. 생략 시 전체")
@click.pass_context
def style_export(ctx, output, category):
    if category is None:
        payload = style_registry.load_styles()
        count = sum(len(v) for v in payload.values())
    else:
        # 단일 카테고리만 export — 여전히 카테고리 스키마로 저장해 import 호환 유지
        payload = {c: {} for c in style_registry.CATEGORIES}
        payload[category] = style_registry.load_styles(category)
        count = len(payload[category])

    Path(output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    output_result(
        {"status": "exported", "path": output, "count": count,
         "category": category or "all"},
        ctx.obj.get("json", False),
    )


@style_group.command("import", help="백업 JSON에서 스타일 복원 (기존과 머지)")
@click.option("-i", "--input", "input_path", required=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--overwrite", is_flag=True, default=False,
              help="중복 이름은 덮어쓰기 (기본: 건너뛰기)")
@click.option("--category", type=_CATEGORY_CHOICE, default=None,
              help="플랫 스키마 파일을 특정 카테고리로 import. "
                   "카테고리 스키마 파일은 이 옵션 무시")
@click.pass_context
def style_import(ctx, input_path, overwrite, category):
    raw = Path(input_path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"JSON 파싱 실패: {e}")
    if not isinstance(data, dict):
        raise click.ClickException("import 파일은 dict 여야 함.")

    imported: list[dict] = []
    skipped: list[dict] = []

    # 스키마 감지
    is_category_schema = all(k in style_registry.CATEGORIES for k in data.keys()) and bool(data)
    if is_category_schema:
        sections = data
    else:
        # 플랫 스키마 → category 지정 없으면 기본 text
        target = category or "text"
        sections = {target: data}

    for cat, entries in sections.items():
        if cat not in style_registry.CATEGORIES or not isinstance(entries, dict):
            continue
        for name, spec in entries.items():
            if not isinstance(spec, dict):
                skipped.append({"name": name, "category": cat,
                                 "reason": "spec 이 dict 아님"})
                continue
            try:
                style_registry.save_style(
                    name, spec, category=cat, overwrite=overwrite,
                )
                imported.append({"name": name, "category": cat})
            except ValueError as e:
                skipped.append({"name": name, "category": cat,
                                 "reason": str(e)})

    output_result(
        {
            "status": "imported",
            "imported_count": len(imported),
            "imported": imported,
            "skipped": skipped,
        },
        ctx.obj.get("json", False),
    )


# =========================================================================
# apply-video / apply-audio — 일괄 적용
# =========================================================================


@style_group.command("apply-video", help="비디오 스타일을 세그먼트에 일괄 적용 "
                                          "(filter + intro/outro + color)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True, help="대상 트랙")
@click.option("--segment-ref", required=True, help="대상 세그먼트 op id")
@click.option("--style", "style_name", required=True, help="적용할 video 프리셋 이름")
@click.option("--override", default=None,
              help='프리셋 필드 오버라이드 JSON 예: '
                   '\'{"filter":{"name":"bw","intensity":50}}\'')
@click.pass_context
def style_apply_video(ctx, project_path, track, segment_ref, style_name, override):
    session = load_session(project_path)
    overrides = parse_json_option(override, "override") or {}

    try:
        appended = style_registry.apply_video_style(
            session, track, segment_ref, style_name, user_overrides=overrides,
        )
    except KeyError as e:
        raise click.ClickException(f"스타일 '{style_name}' (video) 없음")
    except Exception as e:
        raise click.ClickException(f"apply-video 실패: {type(e).__name__}: {e}")

    output_result(
        {
            "status": "applied",
            "style": style_name,
            "category": "video",
            "track": track,
            "segment_ref": segment_ref,
            "ops_added": len(appended),
            "ops": appended,
        },
        ctx.obj.get("json", False),
    )


@style_group.command("apply-audio", help="오디오 스타일을 세그먼트에 일괄 적용 "
                                          "(volume + fade + effect)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--track", required=True, help="대상 트랙")
@click.option("--segment-ref", required=True, help="대상 세그먼트 op id")
@click.option("--style", "style_name", required=True, help="적용할 audio 프리셋 이름")
@click.option("--override", default=None,
              help='프리셋 필드 오버라이드 JSON 예: \'{"volume":0.5}\'')
@click.pass_context
def style_apply_audio(ctx, project_path, track, segment_ref, style_name, override):
    session = load_session(project_path)
    overrides = parse_json_option(override, "override") or {}

    try:
        appended = style_registry.apply_audio_style(
            session, track, segment_ref, style_name, user_overrides=overrides,
        )
    except KeyError as e:
        raise click.ClickException(
            f"스타일 '{style_name}' (audio) 없음 또는 segment_ref 미매칭: {e}"
        )
    except Exception as e:
        raise click.ClickException(f"apply-audio 실패: {type(e).__name__}: {e}")

    output_result(
        {
            "status": "applied",
            "style": style_name,
            "category": "audio",
            "track": track,
            "segment_ref": segment_ref,
            "ops_added": len(appended),
            "ops": appended,
        },
        ctx.obj.get("json", False),
    )
