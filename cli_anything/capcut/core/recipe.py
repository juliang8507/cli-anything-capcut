"""레시피 (JSON 배치) 지원.

레시피는 세션을 한 번에 구성하는 선언형 JSON::

    {
      "name": "music-video",
      "width": 1080, "height": 1080, "fps": 30,
      "operations": [
        { "op": "add_track", "args": { "type": "video", "name": "V1" } },
        { "op": "add_image", "args": { "file": "...", "track": "V1",
                                        "start": "0s", "duration": "5s" } }
      ]
    }

CLI에서 `import-recipe`로 일괄 적용, `export-recipe`로 덤프.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli_anything.capcut.core.session import Session
from cli_anything.capcut.core.time_utils import resolve_start_time


class RecipeError(RuntimeError):
    """레시피 로드/적용 실패."""


def load_recipe(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise RecipeError(f"레시피 파일 없음: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RecipeError(f"레시피 JSON 파싱 실패: {e}") from e


def validate_recipe(recipe: dict) -> dict:
    """레시피 구조 검증 (실제 replay 없이)."""
    errors: list[str] = []
    warnings: list[str] = []

    if "operations" not in recipe:
        errors.append("'operations' 배열 필요")
        return {"valid": False, "errors": errors, "warnings": warnings}

    ops = recipe["operations"]
    if not isinstance(ops, list):
        errors.append("'operations' 는 리스트여야 함")
        return {"valid": False, "errors": errors, "warnings": warnings}

    for i, item in enumerate(ops):
        if not isinstance(item, dict):
            errors.append(f"operations[{i}]: dict 여야 함")
            continue
        if "op" not in item:
            errors.append(f"operations[{i}]: 'op' 필드 없음")

    # 옛 CLI 1.0.0의 22개 버그 중 권장사항 — 트랙 수동 추가 확인 (#4, #9, #14)
    has_track_op = any(o.get("op") == "add_track" for o in ops)
    has_media_op = any(o.get("op", "").startswith("add_") and o.get("op") != "add_track" for o in ops)
    if has_media_op and not has_track_op:
        warnings.append(
            "레시피에 add_track op가 없음. 미디어 op 전에 트랙을 명시하면 안정성↑."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "op_count": len(ops),
    }


def apply_recipe(session: Session, recipe: dict, *, skip_errors: bool = False) -> dict:
    """레시피의 operations를 세션에 순차 추가. ``"auto"``/상대 표현은 추가 시점에 해석."""
    results: list[dict] = []
    errors: list[dict] = []

    with session.batch():
        for idx, item in enumerate(recipe.get("operations", [])):
            op_name = item.get("op")
            args = dict(item.get("args", {}))
            # start 해석 (auto / +... 절대값으로 고정)
            if "start" in args and "track" in args:
                args["start"] = resolve_start_time(
                    session.data, args["start"], track_name=args.get("track")
                )
            try:
                results.append(session.append_operation(op_name, args))
            except Exception as e:
                err = {"index": idx, "op": op_name, "args": args, "error": str(e)}
                errors.append(err)
                if not skip_errors:
                    raise RecipeError(
                        f"recipe[{idx}] ({op_name}) 실패: {type(e).__name__}: {e}"
                    ) from e

    return {
        "applied": len(results),
        "errors": errors,
        "operations": results,
    }
