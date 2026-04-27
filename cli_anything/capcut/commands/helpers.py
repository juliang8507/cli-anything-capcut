"""commands 공통 헬퍼 — 출력 포매팅, 세션 로드, JSON 옵션 파싱."""

from __future__ import annotations

import json
from typing import Any, Callable

import click

from cli_anything.capcut.core.session import Session, SessionError


def project_option(func: Callable) -> Callable:
    """``-p / --project`` 세션 경로 옵션 공통 데코레이터.

    새 커맨드 추가 시 ``@project_option`` 한 줄로 ``project_path`` 파라미터 주입.
    """
    return click.option("-p", "--project", "project_path", required=True,
                        help="세션 JSON 파일 경로")(func)


def output_result(result: Any, as_json: bool) -> None:
    """JSON 또는 사람-친화 형식 출력."""
    if as_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(result, dict):
        for k, v in result.items():
            if isinstance(v, (list, dict)) and v:
                click.echo(f"{k}:")
                for item in (v if isinstance(v, list) else [f"  {kk}: {vv}" for kk, vv in v.items()]):
                    click.echo(f"  {item}")
            else:
                click.echo(f"{k}: {v}")
    elif isinstance(result, list):
        for item in result:
            click.echo(item)
    else:
        click.echo(str(result))


def load_session(project_path: str) -> Session:
    try:
        return Session.load(project_path)
    except SessionError as e:
        raise click.ClickException(str(e))


def parse_json_option(value: str | None, name: str = "option") -> dict | None:
    """``--border '{...}'`` 같은 JSON 문자열 옵션을 dict로 변환."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"{name}: 유효한 JSON 아님: {e}")
    if not isinstance(result, dict):
        raise click.BadParameter(f"{name}: JSON 객체(dict)여야 함")
    return result


def parse_color(value: str | None) -> list[float] | None:
    """``--color 255,128,0`` 또는 ``--color "[1.0, 0.5, 0.0]"`` 모두 지원."""
    if value is None:
        return None
    value = value.strip()
    if value.startswith(("[", "(")):
        try:
            parsed = json.loads(value.replace("(", "[").replace(")", "]"))
            return [float(c) for c in parsed[:3]]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise click.BadParameter(f"색 JSON 파싱 실패: {e}")
    if "," in value:
        parts = [p.strip() for p in value.split(",")]
        try:
            return [float(p) for p in parts[:3]]
        except ValueError as e:
            raise click.BadParameter(f"색 'r,g,b' 파싱 실패: {e}")
    raise click.BadParameter(f"색 값을 알 수 없음: {value!r}. 'r,g,b' 또는 '[r,g,b]' 형식.")


# 자주 쓰는 클립 세팅 프리셋 (버그 #6/#21 대응)
CLIP_PRESETS: dict[str, dict] = {
    "subtitle-bottom": {"transform_x": 0.0, "transform_y": -0.75},
    "subtitle-top": {"transform_x": 0.0, "transform_y": 0.85},
    "title-top": {"transform_x": 0.0, "transform_y": 0.65},
    "pip-top-right": {"scale_x": 0.35, "scale_y": 0.35, "transform_x": 0.55, "transform_y": 0.65},
    "pip-top-left": {"scale_x": 0.35, "scale_y": 0.35, "transform_x": -0.55, "transform_y": 0.65},
    "pip-bottom-right": {"scale_x": 0.35, "scale_y": 0.35, "transform_x": 0.55, "transform_y": -0.65},
    "pip-bottom-left": {"scale_x": 0.35, "scale_y": 0.35, "transform_x": -0.55, "transform_y": -0.65},
    "center": {"transform_x": 0.0, "transform_y": 0.0},
}


def resolve_clip_settings(value: str | None) -> dict | None:
    """``--clip-settings``: 문자열이면 프리셋 매칭, JSON이면 그대로."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    if value in CLIP_PRESETS:
        return dict(CLIP_PRESETS[value])
    try:
        return parse_json_option(value, "clip-settings")
    except click.BadParameter:
        raise click.BadParameter(
            f"clip-settings: '{value}'는 프리셋도 JSON도 아님. "
            f"프리셋: {', '.join(CLIP_PRESETS)}"
        )
