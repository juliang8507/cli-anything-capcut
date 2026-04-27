"""세그먼트 참조 인덱싱 유틸.

세션 op가 `segment_ref` (예: `"op_5"`)로 다른 op가 만든 세그먼트를 참조할 때,
트랙 상의 위치 인덱스(0-based)로 변환해서 pyCapCut의 ScriptFile에 전달해야 함.
"""

from __future__ import annotations

from typing import Any

from cli_anything.capcut.core.op_registry import CREATION_OPS


def build_segment_ref_index(session_data: dict) -> dict[str, dict[str, Any]]:
    """op_id → {track, index, op_type} 매핑 테이블.

    replay 중 `segment_ref="op_5"` 같은 참조를 트랙 내 세그먼트 인덱스로 빠르게
    변환할 수 있도록 세션 시작 시 미리 만들어 쓴다.
    """
    index: dict[str, dict[str, Any]] = {}
    # 트랙별로 세그먼트 순서를 카운트
    counter: dict[str, int] = {}
    for op in session_data.get("operations", []):
        if op.get("op") not in CREATION_OPS:
            continue
        args = op.get("args", {}) or {}
        track = args.get("track") or "_default_"
        idx = counter.get(track, 0)
        index[op["id"]] = {
            "track": args.get("track"),
            "index": idx,
            "op_type": op["op"],
        }
        counter[track] = idx + 1
    return index


def resolve_segment_ref(
    session_data: dict,
    segment_ref: str,
    track: str | None = None,
    *,
    cache: dict | None = None,
) -> int:
    """segment_ref (op ID)를 트랙 내 positional index (0-based)로 변환.

    반복 호출 시(예: replay 루프) ``cache`` 로 dict 하나를 주면 인덱스를 캐시.
    매 호출마다 전체 operations 배열을 재순회하는 O(N²) 패턴을 O(N)로 축소.

    Raises:
        ValueError: 참조되는 op가 없거나 세그먼트 생성 op가 아닐 때.
    """
    if cache is not None and "segment_ref_index" in cache:
        ix = cache["segment_ref_index"]
    else:
        ix = build_segment_ref_index(session_data)
        if cache is not None:
            cache["segment_ref_index"] = ix

    if segment_ref not in ix:
        raise ValueError(
            f"segment_ref '{segment_ref}' not found. "
            "Check that the referenced operation exists and creates a segment."
        )
    entry = ix[segment_ref]
    if track is not None and entry["track"] != track:
        raise ValueError(
            f"segment_ref '{segment_ref}' belongs to track "
            f"'{entry['track']}', not '{track}'."
        )
    return entry["index"]
