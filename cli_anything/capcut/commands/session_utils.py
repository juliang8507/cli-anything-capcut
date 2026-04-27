"""session 유틸 — compact / find-replace-media / watch."""

from __future__ import annotations

import re
import time
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


@click.group("session", help="세션 유틸리티")
def session_group():
    pass


@session_group.command("compact", help="undo된 자취나 중복 op 정리 (파괴적)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--dry-run", is_flag=True, default=False,
              help="실제로 수정하지 않고 미리보기")
@click.option("-y", "--yes", is_flag=True, default=False,
              help="확인 프롬프트 건너뛰기")
@click.pass_context
def session_compact(ctx, project_path, dry_run, yes):
    session = load_session(project_path)
    ops = session.data["operations"]

    # 중복 add_track 제거 (같은 type + name)
    seen_tracks: set[tuple[str, str | None]] = set()
    kept: list[dict] = []
    removed: list[dict] = []
    for op in ops:
        if op["op"] == "add_track":
            a = op.get("args", {})
            key = (a.get("type"), a.get("name"))
            if key in seen_tracks:
                removed.append(op)
                continue
            seen_tracks.add(key)
        kept.append(op)

    # ID 리넘버링 (빈틈 없이 op_1..op_N)
    id_map: dict[str, str] = {}
    for i, op in enumerate(kept, start=1):
        old_id = op.get("id", "")
        new_id = f"op_{i}"
        if old_id != new_id:
            id_map[old_id] = new_id
            op["id"] = new_id
    # segment_ref도 갱신
    for op in kept:
        a = op.get("args", {})
        ref = a.get("segment_ref")
        if ref and ref in id_map:
            a["segment_ref"] = id_map[ref]

    if not dry_run:
        if not yes and not ctx.obj.get("json") and (removed or id_map):
            click.echo(f"[compact] {len(removed)}개 op 제거 + {len(id_map)}개 ID 리넘버링.")
            click.confirm("세션을 수정할까요?", abort=True)
        session.data["operations"] = kept
        session.save()

    output_result(
        {"status": "compacted" if not dry_run else "dry_run",
         "removed": len(removed), "renumbered": len(id_map),
         "final_count": len(kept)},
        ctx.obj["json"],
    )


@session_group.command("find-replace-media",
                       help="세션의 미디어 파일 경로를 일괄 치환 (파괴적)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--pattern", required=True,
              help='정규식 또는 리터럴. --regex 없으면 literal 매치')
@click.option("--replacement", required=True)
@click.option("--regex/--literal", default=False)
@click.option("--dry-run", is_flag=True, default=False,
              help="실제로 수정하지 않고 미리보기")
@click.option("-y", "--yes", is_flag=True, default=False,
              help="확인 프롬프트 건너뛰기")
@click.pass_context
def find_replace_media(ctx, project_path, pattern, replacement, regex, dry_run, yes):
    session = load_session(project_path)
    changes: list[dict] = []
    if regex:
        rx = re.compile(pattern)
    for op in session.data["operations"]:
        a = op.get("args", {})
        f = a.get("file")
        if not f:
            continue
        new_f = rx.sub(replacement, f) if regex else f.replace(pattern, replacement)
        if new_f != f:
            changes.append({"op_id": op["id"], "from": f, "to": new_f})
            if not dry_run:
                a["file"] = new_f
    if not dry_run and changes:
        if not yes and not ctx.obj.get("json"):
            click.echo(f"[find-replace] {len(changes)}개 경로 변경 예정.")
            click.confirm("세션을 수정할까요?", abort=True)
        session.save()
    output_result(
        {"status": "replaced" if not dry_run else "dry_run",
         "count": len(changes), "changes": changes},
        ctx.obj["json"],
    )


@session_group.command("watch", help="세션 파일 변경을 감시하여 자동 save")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--interval", type=float, default=1.0)
@click.option("--max-iterations", type=int, default=0,
              help="0 = 무한. 테스트용으로 유한 반복 가능.")
@click.pass_context
def session_watch(ctx, project_path, interval, max_iterations):
    import pycapcut as cc

    from cli_anything.capcut.core.postprocess import apply_postprocess

    path = Path(project_path)
    if not path.exists():
        raise click.ClickException(f"세션 파일 없음: {path}")

    last_mtime = path.stat().st_mtime
    click.echo(f"[watch] {path} 감시 시작. Ctrl+C로 종료.")
    click.echo(f"[watch] 초기 mtime: {last_mtime}")

    count = 0
    try:
        while True:
            time.sleep(interval)
            if not path.exists():
                continue
            m = path.stat().st_mtime
            if m != last_mtime:
                last_mtime = m
                click.echo(f"[watch] 변경 감지 → save 시도")
                try:
                    session = load_session(str(path))
                    script = session.replay()
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
                    apply_postprocess(target, session.data)
                    click.echo(f"[watch] 저장 완료: {target}")
                except Exception as e:
                    click.echo(f"[watch] 에러: {e}", err=True)
            count += 1
            if max_iterations and count >= max_iterations:
                break
    except KeyboardInterrupt:
        click.echo("[watch] 종료.")
