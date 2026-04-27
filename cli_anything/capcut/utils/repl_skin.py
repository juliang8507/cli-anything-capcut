"""REPL 스킨 — prompt-toolkit 기반 자동완성, 히스토리, 멀티 토큰 입력."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Iterable

import click


def _command_tree(root: click.Group) -> dict[str, list[str]]:
    """루트 그룹에서 {그룹명: [서브커맨드,...]} 사전 만들기."""
    out: dict[str, list[str]] = {}
    for name, cmd in root.commands.items():
        if isinstance(cmd, click.Group):
            out[name] = sorted(cmd.commands)
        else:
            out.setdefault("", []).append(name)
    return out


def run_repl(root: click.Group, draft_folder: str | None = None) -> None:
    """interactive REPL. 빈 줄 / exit / quit 으로 종료."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
    except ImportError:
        click.echo("prompt-toolkit이 필요합니다. pip install prompt-toolkit", err=True)
        return

    history_dir = Path.home() / ".capcut_cli"
    history_dir.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(history_dir / "repl_history"))

    tree = _command_tree(root)
    flat: list[str] = []
    for grp, subs in tree.items():
        if grp:
            flat.append(grp)
            flat.extend(f"{grp} {s}" for s in subs)
        else:
            flat.extend(subs)
    flat.extend(["help", "exit", "quit", "?"])
    completer = WordCompleter(flat, ignore_case=True)

    session = PromptSession(history=history, completer=completer)

    click.echo("cli-anything-capcut REPL — 'help' 도움말, 'exit' 종료.")
    if draft_folder:
        click.echo(f"draft_folder: {draft_folder}")

    while True:
        try:
            line = session.prompt("capcut> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("exit", "quit", ":q"):
            break
        if line in ("help", "?"):
            click.echo("사용 가능 그룹: " + ", ".join(sorted(tree)))
            click.echo("자세한 도움말: '<그룹> --help' 또는 '<그룹> <서브> --help'")
            continue
        try:
            argv = shlex.split(line)
        except ValueError as e:
            click.echo(f"파싱 에러: {e}", err=True)
            continue
        try:
            root.main(argv, standalone_mode=False, prog_name="capcut")
        except click.ClickException as e:
            click.echo(f"에러: {e.format_message()}", err=True)
        except SystemExit:
            pass
        except Exception as e:  # pragma: no cover
            click.echo(f"예외: {type(e).__name__}: {e}", err=True)
    click.echo("종료.")
