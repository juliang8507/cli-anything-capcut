"""이벤트 소스 세션 관리.

``ScriptFile``은 직접 직렬화 불가능하므로, 모든 사용자 커맨드를 JSON op log로
기록하고 매 호출마다 전체 log를 처음부터 replay해서 최종 ``ScriptFile``을 만든다.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
from typing import Any, Iterator

import pycapcut as cc

from cli_anything.capcut.core import op_handlers as _oh
from cli_anything.capcut.core.op_registry import (
    CREATION_OPS,
    MODIFIER_OPS,
    TIMED_SEGMENT_OPS,
)
from cli_anything.capcut.core.segment_utils import resolve_segment_ref
from cli_anything.capcut.core.time_utils import (
    format_duration,
    format_us,
    parse_time_value,
)

SESSION_SUFFIX = ".session.json"
SCHEMA_VERSION = 2


class SessionError(RuntimeError):
    """세션 로드/저장/replay 실패."""


class Session:
    """이벤트 소스 CapCut 세션."""

    def __init__(self, path: Path, data: dict):
        self.path = Path(path)
        self.data = data
        self._modified = False
        self._batch_depth = 0

    # ------------------------------------------------------------ lifecycle

    @classmethod
    def create(
        cls,
        draft_folder: str,
        draft_name: str,
        *,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        output: str | Path | None = None,
    ) -> "Session":
        session_path = _make_session_path(output, draft_name)
        data = {
            "schema_version": SCHEMA_VERSION,
            "draft_folder": str(draft_folder),
            "draft_name": draft_name,
            "width": width,
            "height": height,
            "fps": fps,
            "operations": [],
        }
        session = cls(session_path, data)
        session._auto_save()
        return session

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        path = Path(path)
        if not path.exists():
            raise SessionError(
                f"세션 파일을 찾을 수 없음: {path}\n"
                "  project new --name <name> 으로 새로 만들거나 경로 확인."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SessionError(f"세션 JSON 파싱 실패: {e}") from e
        _migrate_v1_to_v2(data)
        return cls(path, data)

    def save(self) -> None:
        """디스크에 기록 + modified 플래그 리셋."""
        self._auto_save()
        self._modified = False

    def _auto_save(self) -> None:
        """원자적 쓰기 — 같은 디렉토리에 temp 파일을 쓰고 rename.

        프로세스 크래시 시 반쯤 쓰여진 세션 JSON으로 복구 불가능해지는 문제 방지.
        """
        if self._batch_depth > 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Windows에서는 os.replace로 같은 경로 덮어쓰기가 원자적으로 동작
        os.replace(tmp, self.path)

    @contextlib.contextmanager
    def batch(self) -> Iterator[None]:
        """블록 안에서는 디스크 기록 미루고 마지막에 한 번만 저장."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._auto_save()

    # ------------------------------------------------------------ mutations

    def append_operation(self, op: str, args: dict, *, _status: str = "added") -> dict:
        clean_args = {k: v for k, v in (args or {}).items() if v is not None}
        op_id = _next_op_id(self.data)
        record = {"id": op_id, "op": op, "args": clean_args}
        self.data["operations"].append(record)
        self._modified = True
        self._auto_save()
        return {
            "status": _status,
            "type": op,
            "id": op_id,
            "operation_index": len(self.data["operations"]) - 1,
            **clean_args,
        }

    def undo(self, count: int = 1, op_type: str | None = None) -> list[dict]:
        ops = self.data["operations"]
        removed: list[dict] = []
        i = len(ops) - 1
        while i >= 0 and len(removed) < count:
            if op_type is None or op_type in ops[i]["op"]:
                removed.append(ops.pop(i))
            i -= 1
        if removed:
            self._modified = True
            self._auto_save()
        return removed

    def edit_operation(self, index: int, new_args: dict) -> dict:
        """op.args를 partial 업데이트. 반환: 업데이트된 op + warnings."""
        ops = self.data["operations"]
        if not 0 <= index < len(ops):
            raise SessionError(f"Operation index {index} out of range (0-{len(ops) - 1})")
        warnings: list[str] = []
        old_id = ops[index].get("id")
        ops[index]["args"].update({k: v for k, v in new_args.items() if v is not None})
        # id를 바꾸려 하면, 이 op를 segment_ref로 참조하는 다른 op 경고
        new_id = new_args.get("id")
        if new_id and new_id != old_id:
            for other in ops:
                if other.get("args", {}).get("segment_ref") == old_id:
                    warnings.append(
                        f"Op {other.get('id')} references '{old_id}' via segment_ref; "
                        f"changing id to '{new_id}' will break that reference."
                    )
            ops[index]["id"] = new_id
        self._modified = True
        self._auto_save()
        return {"edited": ops[index], "warnings": warnings}

    def delete_operation(self, index: int) -> dict:
        ops = self.data["operations"]
        if not 0 <= index < len(ops):
            raise SessionError(f"Operation index {index} out of range")
        removed = ops.pop(index)
        # 남은 op 중 이 op의 id를 참조하는 게 있으면 경고
        warnings = []
        rid = removed.get("id")
        for other in ops:
            if other.get("args", {}).get("segment_ref") == rid:
                warnings.append(f"Op {other.get('id')} references deleted op {rid} via segment_ref")
        self._modified = True
        self._auto_save()
        return {"deleted": removed, "warnings": warnings}

    def reorder_operation(self, from_index: int, to_index: int) -> dict:
        ops = self.data["operations"]
        if not 0 <= from_index < len(ops) or not 0 <= to_index < len(ops):
            raise SessionError(
                f"index out of range (from_index={from_index}, to_index={to_index}, len={len(ops)})"
            )
        op = ops.pop(from_index)
        ops.insert(to_index, op)
        # forward-reference 경고
        warnings = []
        id_to_index = {o.get("id"): i for i, o in enumerate(ops)}
        for i, o in enumerate(ops):
            ref = o.get("args", {}).get("segment_ref")
            if ref and id_to_index.get(ref, -1) > i:
                warnings.append(
                    f"Op {o.get('id')} at index {i} now forward-references {ref}"
                )
        self._modified = True
        self._auto_save()
        return {"reordered": op, "from_index": from_index, "to_index": to_index, "warnings": warnings}

    def do_batch(self, operations: list[dict], skip_errors: bool = False) -> dict:
        """여러 op를 한 번에 실행."""
        results: list[dict] = []
        errors: list[dict] = []
        with self.batch():
            for item in operations:
                op = item.get("op")
                args = item.get("args", {})
                try:
                    results.append(self.append_operation(op, args))
                except Exception as e:  # pragma: no cover
                    if skip_errors:
                        errors.append({"op": op, "args": args, "error": str(e)})
                    else:
                        raise
        return {"results": results, "errors": errors}

    # ------------------------------------------------------------ replay

    def replay(self) -> cc.ScriptFile:
        """전체 op log를 replay해서 ScriptFile 재구성."""
        script = cc.ScriptFile(self.data["width"], self.data["height"], self.data["fps"])
        ctx: dict[str, Any] = {"session_data": self.data}
        for idx, op in enumerate(self.data["operations"]):
            try:
                _oh.apply_operation(script, op["op"], op.get("args", {}), ctx)
            except Exception as e:
                raise SessionError(
                    f"Replay failed at op #{idx} ({op['op']}): {type(e).__name__}: {e}"
                ) from e
        return script

    def replay_skip_errors(self) -> tuple[cc.ScriptFile, list[dict]]:
        """에러 나는 op는 건너뛰고 계속. (index, op, error) 리스트 반환."""
        script = cc.ScriptFile(self.data["width"], self.data["height"], self.data["fps"])
        ctx: dict[str, Any] = {"session_data": self.data}
        errors: list[dict] = []
        for idx, op in enumerate(self.data["operations"]):
            try:
                _oh.apply_operation(script, op["op"], op.get("args", {}), ctx)
            except Exception as e:
                errors.append({"index": idx, "op": op, "error": f"{type(e).__name__}: {e}"})
        return script, errors

    def validate(self) -> dict:
        try:
            script = self.replay()
        except SessionError as e:
            return {
                "valid": False,
                "error": str(e),
                "operation_count": len(self.data["operations"]),
            }
        return {
            "valid": True,
            "operation_count": len(self.data["operations"]),
            "duration_us": int(script.duration),
            "duration_human": format_duration(int(script.duration)),
            "tracks": list(script.tracks.keys()),
        }

    # ------------------------------------------------------------ analysis

    def summary(self) -> dict:
        ops = self.data["operations"]
        op_types: dict[str, int] = {}
        for o in ops:
            op_types[o["op"]] = op_types.get(o["op"], 0) + 1
        return {
            "path": str(self.path),
            "draft_name": self.draft_name,
            "draft_folder": self.draft_folder,
            "width": self.data["width"],
            "height": self.data["height"],
            "fps": self.data["fps"],
            "operation_count": len(ops),
            "op_types": op_types,
            "modified": self._modified,
        }

    def history(self, filter_op: str | None = None) -> list[dict]:
        out: list[dict] = []
        for i, op in enumerate(self.data.get("operations", [])):
            if filter_op and filter_op not in op.get("op", ""):
                continue
            out.append(
                {
                    "index": i,
                    "id": op.get("id"),
                    "op": op.get("op"),
                    "args": op.get("args", {}),
                }
            )
        return out

    def segments_at_time(self, time_us: int) -> list[dict]:
        """time_us 시점에 겹치는 모든 세그먼트 op를 찾아 반환."""
        hits: list[dict] = []
        for i, op in enumerate(self.data["operations"]):
            if op["op"] not in CREATION_OPS:
                continue
            args = op.get("args", {})
            s = parse_time_value(args.get("start", 0))
            d = parse_time_value(args.get("duration", 0))
            if s <= time_us < s + d:
                hits.append(
                    {
                        "index": i,
                        "id": op["id"],
                        "op": op["op"],
                        "track": args.get("track"),
                        "start_us": s,
                        "end_us": s + d,
                    }
                )
        return hits

    def gap_detect(self, track_name: str | None = None) -> list[dict]:
        """트랙 내 인접 세그먼트 사이의 갭 찾기."""
        segs = self._track_segments(track_name)
        segs.sort(key=lambda x: x["start_us"])
        gaps: list[dict] = []
        for prev, cur in zip(segs, segs[1:]):
            if cur["start_us"] > prev["end_us"]:
                gap = cur["start_us"] - prev["end_us"]
                gaps.append(
                    {
                        "start_us": prev["end_us"],
                        "end_us": cur["start_us"],
                        "gap_us": gap,
                        "gap_human": format_us(gap),
                    }
                )
        return gaps

    def overlap_detect(self, track_name: str | None = None) -> list[dict]:
        """트랙 내 겹치는 세그먼트 쌍 찾기."""
        segs = self._track_segments(track_name)
        segs.sort(key=lambda x: x["start_us"])
        overlaps: list[dict] = []
        for prev, cur in zip(segs, segs[1:]):
            if cur["start_us"] < prev["end_us"]:
                overlaps.append({"a": prev, "b": cur, "overlap_us": prev["end_us"] - cur["start_us"]})
        return overlaps

    def timeline(self, width: int = 60) -> dict:
        """ASCII 타임라인. 각 트랙을 한 줄로."""
        ops = [o for o in self.data["operations"] if o["op"] in CREATION_OPS]
        total_end = 0
        tracks: dict[str, list[dict]] = {}
        for op in ops:
            a = op.get("args", {})
            s = parse_time_value(a.get("start", 0))
            d = parse_time_value(a.get("duration", 0))
            t = a.get("track") or "_default_"
            tracks.setdefault(t, []).append({"s": s, "e": s + d, "op": op["op"], "id": op["id"]})
            total_end = max(total_end, s + d)
        if total_end == 0:
            return {"timeline_text": "(no segments)", "duration_us": 0}

        lines = []
        lines.append(f"Timeline (total: {format_duration(total_end)})")
        for track, segs in tracks.items():
            segs.sort(key=lambda x: x["s"])
            row = ["."] * width
            for seg in segs:
                sp = int(seg["s"] / total_end * width)
                ep = max(sp + 1, int(seg["e"] / total_end * width))
                label = seg["op"].replace("add_", "")[:3]
                for i in range(sp, min(ep, width)):
                    row[i] = label[0] if i == sp else "="
            lines.append(f"  {track:10} |{''.join(row)}|")
        return {"timeline_text": "\n".join(lines), "duration_us": total_end}

    def stats(self) -> dict:
        ops = self.data["operations"]
        tracks: dict[str, int] = {}
        media_files: set[str] = set()
        total_end = 0
        for op in ops:
            a = op.get("args", {})
            if op["op"] in CREATION_OPS:
                t = a.get("track") or "_default_"
                tracks[t] = tracks.get(t, 0) + 1
                s = parse_time_value(a.get("start", 0))
                d = parse_time_value(a.get("duration", 0))
                total_end = max(total_end, s + d)
            if "file" in a and a["file"]:
                media_files.add(a["file"])
        return {
            "operation_count": len(ops),
            "duration_us": total_end,
            "duration_human": format_duration(total_end),
            "tracks": tracks,
            "media_files": sorted(media_files),
            "media_file_count": len(media_files),
        }

    def diff(self, other: "Session") -> dict:
        """다른 세션과 op 수준에서 비교."""
        a_by_id = {o["id"]: o for o in self.data["operations"]}
        b_by_id = {o["id"]: o for o in other.data["operations"]}
        a_ids = set(a_by_id)
        b_ids = set(b_by_id)
        added = [b_by_id[k] for k in b_ids - a_ids]
        removed = [a_by_id[k] for k in a_ids - b_ids]
        changed: list[dict] = []
        for k in a_ids & b_ids:
            if a_by_id[k] != b_by_id[k]:
                changed.append({"id": k, "before": a_by_id[k], "after": b_by_id[k]})
        return {"added": added, "removed": removed, "changed": changed}

    def status(self) -> dict:
        """AI 에이전트 친화 종합 상태."""
        s = self.summary()
        s["validation"] = self.validate()
        s["gaps"] = self.gap_detect()
        s["overlaps"] = self.overlap_detect()
        return s

    # ------------------------------------------------------------ merge / clone

    def clone(self, output_path: str | Path) -> "Session":
        new_data = copy.deepcopy(self.data)
        new_path = Path(output_path)
        new_session = Session(new_path, new_data)
        new_session._auto_save()
        return new_session

    def merge(self, other: "Session", offset_us: int = 0) -> dict:
        """다른 세션의 op들을 이 세션에 합침. offset_us>0이면 시간 이동."""
        merged = 0
        id_map: dict[str, str] = {}
        with self.batch():
            for op in other.data["operations"]:
                new_args = dict(op.get("args", {}))
                if offset_us:
                    # time-based 필드들 이동
                    if "start" in new_args and op["op"] in TIMED_SEGMENT_OPS:
                        s_us = parse_time_value(new_args["start"])
                        new_args["start"] = f"{s_us + offset_us}us"
                if "segment_ref" in new_args and new_args["segment_ref"] in id_map:
                    new_args["segment_ref"] = id_map[new_args["segment_ref"]]
                new_id = _next_op_id(self.data)
                id_map[op["id"]] = new_id
                self.data["operations"].append({"id": new_id, "op": op["op"], "args": new_args})
                merged += 1
        self._modified = True
        return {"merged": merged, "id_map": id_map}

    # ------------------------------------------------------------ export

    def export_script(self, cli_cmd: str = "cli-anything-capcut") -> str:
        """세션을 재현 가능한 CLI 커맨드 문자열로 출력."""
        cli_cmd = os.environ.get("CAPCUT_CLI_CMD", cli_cmd)
        lines = [f"# CapCut CLI session: {self.draft_name}"]
        session_path = str(self.path).replace("\\", "/")
        lines.append(
            f'{cli_cmd} project new --name "{self.draft_name}" '
            f'--width {self.data["width"]} --height {self.data["height"]} --fps {self.data["fps"]}'
        )
        for op in self.data["operations"]:
            lines.append(_op_to_cli_command(op["op"], op.get("args", {}), session_path, cli_cmd))
        return "\n".join(lines)

    def export_recipe(self) -> dict:
        """세션을 JSON 레시피로 직렬화 (import-recipe로 재실행 가능)."""
        return {
            "name": self.draft_name,
            "width": self.data["width"],
            "height": self.data["height"],
            "fps": self.data["fps"],
            "operations": [
                {"id": op["id"], "op": op["op"], "args": op.get("args", {})}
                for op in self.data["operations"]
            ],
        }

    # ------------------------------------------------------------ properties

    @property
    def draft_folder(self) -> str:
        return self.data["draft_folder"]

    @property
    def draft_name(self) -> str:
        return self.data["draft_name"]

    @property
    def width(self) -> int:
        return self.data["width"]

    @property
    def height(self) -> int:
        return self.data["height"]

    @property
    def fps(self) -> int:
        return self.data["fps"]

    @property
    def operation_count(self) -> int:
        return len(self.data["operations"])

    @property
    def modified(self) -> bool:
        return self._modified

    # ------------------------------------------------------------ internal

    def _track_segments(self, track_name: str | None) -> list[dict]:
        out: list[dict] = []
        for i, op in enumerate(self.data["operations"]):
            if op["op"] not in CREATION_OPS:
                continue
            a = op.get("args", {})
            if track_name and a.get("track") != track_name:
                continue
            s = parse_time_value(a.get("start", 0))
            d = parse_time_value(a.get("duration", 0))
            out.append({"index": i, "id": op["id"], "start_us": s, "end_us": s + d})
        return out


# =========================================================================
# helpers
# =========================================================================


def _make_session_path(output: str | Path | None, draft_name: str) -> Path:
    if output:
        p = Path(output)
        if p.is_dir():
            return p / f"{draft_name}{SESSION_SUFFIX}"
        return p
    return Path.cwd() / f"{draft_name}{SESSION_SUFFIX}"


def _migrate_v1_to_v2(data: dict) -> None:
    if data.get("schema_version") == SCHEMA_VERSION:
        return
    data.setdefault("schema_version", SCHEMA_VERSION)
    for i, op in enumerate(data.get("operations", [])):
        op.setdefault("id", f"op_{i + 1}")


def _next_op_id(data: dict) -> str:
    used = {op.get("id") for op in data.get("operations", [])}
    i = len(data.get("operations", [])) + 1
    while f"op_{i}" in used:
        i += 1
    return f"op_{i}"


# 간단한 op → CLI 역변환 (핵심 op만). 원본은 더 풍부했지만 MVP 용도로 충분.
def _op_to_cli_command(op: str, args: dict, session_path: str, cli_cmd: str) -> str:
    sp = f'-p "{session_path}"'
    if op == "add_track":
        return f'{cli_cmd} track add {sp} --type {args.get("type", "video")} --name {args.get("name", "")}'
    if op == "add_image":
        return (
            f'{cli_cmd} image add {sp} -f "{args.get("file", "")}" '
            f'--start {args.get("start", "auto")} --duration {args.get("duration", "3s")} '
            f'--track {args.get("track", "")}'
        )
    if op == "add_video":
        return (
            f'{cli_cmd} video add {sp} -f "{args.get("file", "")}" '
            f'--start {args.get("start", "auto")} --duration {args.get("duration", "")} '
            f'--track {args.get("track", "")}'
        )
    if op == "add_audio":
        return (
            f'{cli_cmd} audio add {sp} -f "{args.get("file", "")}" '
            f'--start {args.get("start", "auto")} --duration {args.get("duration", "")} '
            f'--track {args.get("track", "")}'
        )
    # fallback: JSON으로 표현
    return f"# {op} {json.dumps(args, ensure_ascii=False)}"
