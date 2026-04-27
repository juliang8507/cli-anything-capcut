"""Replay 실패 op 자동 격리(quarantine) & 재시도.

장시간 작업한 세션은 op 중 하나가 깨져도(예: 존재하지 않는 ``segment_ref``)
``save`` 전체가 터지곤 한다. 이 모듈은 ``replay_skip_errors`` 로 1차 시도 후,
실패한 op id 들을 격리 세트에 넣고 남은 op 로만 다시 ``replay`` 를 시도한다.

Quarantine 알고리즘
-------------------

1. ``session.replay_skip_errors()`` 호출 → ``(script, errors)``
2. ``errors`` 가 비어있으면 즉시 반환
3. 실패 op 의 ``id`` 를 격리 세트에 추가
4. 격리된 op 를 빼고 세션 데이터의 얕은 사본을 만들어 다시 replay
5. errors 가 계속 나오면 해당 op 도 격리 → 반복 (``max_attempts`` 까지)
6. 최종 script + 전체 fix_report 반환

fix_report 형식
---------------

::

    [
        {"op_id": "op_3", "op": "add_video", "error": "FileNotFoundError: ...",
         "attempt": 1, "args": {...}},
        ...
    ]
"""

from __future__ import annotations

import copy
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from cli_anything.capcut.core.session import Session


def _replay_subset(session_data: dict, skip_ids: set[str]) -> tuple[Any, list[dict]]:
    """session.data 의 얕은 사본을 만들어 skip_ids 제외하고 replay."""
    # 임포트는 함수 내부 — 순환 의존 방지
    import pycapcut as cc

    from cli_anything.capcut.core import op_handlers as _oh

    filtered_ops = [
        op for op in session_data.get("operations", [])
        if op.get("id") not in skip_ids
    ]
    script = cc.ScriptFile(
        session_data["width"], session_data["height"], session_data["fps"]
    )
    ctx: dict[str, Any] = {"session_data": session_data}
    errors: list[dict] = []
    for idx, op in enumerate(filtered_ops):
        try:
            _oh.apply_operation(script, op["op"], op.get("args", {}), ctx)
        except Exception as e:
            errors.append({
                "index": idx,
                "op": op,
                "error": f"{type(e).__name__}: {e}",
            })
    return script, errors


def replay_with_auto_fix(
    session: "Session",
    *,
    max_attempts: int = 3,
) -> tuple[Any, list[dict]]:
    """Replay 하면서 실패 op 를 격리하고 나머지로 재시도.

    Parameters
    ----------
    session : Session
        대상 세션.
    max_attempts : int
        재시도 상한 (기본 3). 각 시도마다 새로 발견된 실패 op 를 격리에 추가.

    Returns
    -------
    (script, fix_report) : tuple
        ``script`` 는 최종 ``cc.ScriptFile``.
        ``fix_report`` 는 격리된 op 들의 상세 목록 (시도 순).
    """
    fix_report: list[dict] = []
    quarantined: set[str] = set()

    # 1차: session 자체의 replay_skip_errors 재사용 (안전)
    script, errors = session.replay_skip_errors()
    attempt = 1
    for e in errors:
        op = e.get("op", {}) or {}
        op_id = op.get("id")
        if op_id is None:
            continue
        quarantined.add(op_id)
        fix_report.append({
            "op_id": op_id,
            "op": op.get("op"),
            "args": op.get("args", {}),
            "error": e.get("error"),
            "attempt": attempt,
        })

    if not errors:
        return script, fix_report

    # 2차 이후: 격리된 op 를 빼고 sub-replay
    session_data = session.data
    while attempt < max_attempts:
        attempt += 1
        script, sub_errors = _replay_subset(session_data, quarantined)
        if not sub_errors:
            break
        new_failures: list[dict] = []
        for e in sub_errors:
            op = e.get("op", {}) or {}
            op_id = op.get("id")
            if op_id is None or op_id in quarantined:
                continue
            quarantined.add(op_id)
            new_failures.append({
                "op_id": op_id,
                "op": op.get("op"),
                "args": op.get("args", {}),
                "error": e.get("error"),
                "attempt": attempt,
            })
        if not new_failures:
            # 새로 격리할 게 없는데도 에러가 남 → 무한 루프 방지
            break
        fix_report.extend(new_failures)

    return script, fix_report


def explain_fix(report: list[dict]) -> str:
    """fix_report 를 사람이 읽을 수 있는 한국어 요약으로 변환."""
    if not report:
        return "자동 수정 없음 — 모든 op 정상 replay."
    lines = [f"자동 수정: {len(report)}개 op 를 격리했습니다."]
    # 같은 op 타입 / 에러 타입으로 그룹화
    by_type: dict[str, list[dict]] = {}
    for item in report:
        key = item.get("op") or "(unknown)"
        by_type.setdefault(key, []).append(item)
    for op_name, items in by_type.items():
        lines.append(f"  - {op_name}: {len(items)}건")
        for it in items[:3]:  # 상위 3개만
            err = (it.get("error") or "").split("\n", 1)[0]
            lines.append(f"      [{it.get('op_id')}] attempt#{it.get('attempt')} {err}")
        if len(items) > 3:
            lines.append(f"      ... 외 {len(items) - 3}건")
    return "\n".join(lines)


def save_with_auto_fix(
    session: "Session",
    draft_folder_path: str | None = None,
    *,
    dry_run: bool = False,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """replay_with_auto_fix → draft 저장 → postprocess 를 한 번에.

    Parameters
    ----------
    session : Session
    draft_folder_path : str, optional
        사용자가 ``--draft-folder`` 로 오버라이드할 때 전달. None 이면 세션에 기록된
        ``session.draft_folder`` 사용.
    dry_run : bool
        True 면 replay 만 하고 draft 는 저장 안 함.
    max_attempts : int
        replay_with_auto_fix 에 전달.

    Returns
    -------
    dict — save_cmd 가 그대로 output 할 수 있는 형태::

        {
            "status": "saved" | "dry_run_ok",
            "draft_path": str | None,
            "draft_content_json": str | None,
            "operation_count": int,
            "fix_report": [...],
            "fix_summary": str,
            "postprocess_applied": int,
            "postprocess_warnings": [...],
            "tracks": [...],
            "duration_us": int,
        }
    """
    # 지연 임포트 — 순환 방지
    from pathlib import Path

    import pycapcut as cc

    from cli_anything.capcut.core.postprocess import apply_postprocess
    from cli_anything.capcut.core.time_utils import format_duration

    script, fix_report = replay_with_auto_fix(session, max_attempts=max_attempts)

    result: dict[str, Any] = {
        "status": "dry_run_ok" if dry_run else "saved",
        "operation_count": session.operation_count,
        "fix_report": fix_report,
        "fix_summary": explain_fix(fix_report),
        "tracks": list(script.tracks.keys()),
        "duration_us": int(script.duration),
        "duration": format_duration(int(script.duration)),
        "postprocess_applied": 0,
        "postprocess_warnings": [],
        "draft_path": None,
        "draft_content_json": None,
    }

    if dry_run:
        return result

    draft_folder = draft_folder_path or session.draft_folder
    Path(draft_folder).mkdir(parents=True, exist_ok=True)
    draft_folder_obj = cc.DraftFolder(draft_folder)
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

    post = apply_postprocess(target, session.data)
    result["draft_path"] = str(target.parent)
    result["draft_content_json"] = str(target)
    result["postprocess_applied"] = post.get("applied", 0)
    result["postprocess_warnings"] = post.get("warnings", [])
    return result
