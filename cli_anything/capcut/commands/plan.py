"""plan 커맨드 — 자연어 → 레시피 JSON.

사용자의 한글 지시를 Claude API 로 ``cli-anything-capcut import-recipe`` 용
JSON 레시피로 변환한다. 출력은 ``validate_recipe()`` 로 검증하고 실패하면
에러 메시지를 LLM 에 돌려주고 한 번 재시도.

키 설계:
- ``build_system_prompt()`` / ``extract_json_block()`` / ``build_asset_listing()``
  같은 순수 함수를 분리해 테스트 가능하게 유지
- API 호출 자체는 ``_call_claude()`` 가 담당
- 호출 실패/SDK 부재 시 친절한 안내
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

import click

from cli_anything.capcut.commands.helpers import output_result
from cli_anything.capcut.core.recipe import validate_recipe

# cli_anything/capcut/core/op_handlers.py 의 _OP_HANDLERS 가 진짜 소스.
# LLM 에게 "이 이름 중에서만 골라!" 라고 못 박기 위해 런타임에 가져옴.
from cli_anything.capcut.core.op_handlers import list_ops as _list_handler_ops


# =========================================================================
# op 스펙 — LLM 에게 알려줄 "허용된 행동 목록"
# =========================================================================


# op_handlers 의 실제 핸들러 이름을 기본으로 잡고, 설명을 덧붙임.
_OP_DESCRIPTIONS: dict[str, str] = {
    "add_track": "트랙 생성. args: {type: 'video'|'audio'|'text'|'effect'|'filter'|'sticker', name}",
    "add_video": "비디오 세그먼트. args: {file, start, duration, track, clip_settings?}",
    "add_image": "이미지 세그먼트. args: {file, start, duration, track, clip_settings?}",
    "add_audio": "오디오 세그먼트. args: {file, start, duration, track, volume?}",
    "add_text": "텍스트 세그먼트. args: {text, start, duration, track, font?, size?, color?, border?, shadow?, clip_settings?}",
    "add_sticker": "스티커 세그먼트. args: {resource_id, start, duration, track}",
    "add_effect": "effect 트랙 세그먼트. args: {name, start, duration, track}",
    "add_filter": "filter 트랙 세그먼트. args: {name, start, duration, track, intensity?}",
    "add_video_transition": "두 세그먼트 사이 전환. args: {track, segment_ref, name, duration}",
    "add_video_fade": "비디오 페이드. args: {track, segment_ref, in_duration?, out_duration?}",
    "add_video_animation": "비디오 세그먼트 애니메이션. args: {track, segment_ref, role(intro|outro|loop), name, duration}",
    "add_text_animation": "텍스트 애니메이션. args: {track, segment_ref, role, name, duration}",
    "add_keyframe": "속성 키프레임. args: {track, segment_ref, property, time, value}",
    "add_audio_fade": "오디오 페이드. args: {track, segment_ref, in_duration?, out_duration?}",
    "add_audio_effect": "오디오 이펙트. args: {track, segment_ref, name, params?}",
    "add_mask": "세그먼트 마스크. args: {track, segment_ref, name, size?, center_x?, center_y?}",
    "add_background": "세그먼트 배경 채움. args: {track, segment_ref, fill_type('blur'|'color'), blur?, color?}",
}


def known_ops() -> list[str]:
    """실제 핸들러에 등록된 op 이름만 (postprocess/noop 포함)."""
    return sorted(_list_handler_ops())


def _op_spec_lines() -> list[str]:
    """LLM 프롬프트에 넣을 op 이름 + 1줄 설명."""
    ops = known_ops()
    lines: list[str] = []
    for op in ops:
        desc = _OP_DESCRIPTIONS.get(op, "(no description)")
        lines.append(f"- {op}: {desc}")
    return lines


# =========================================================================
# 에셋 디렉토리 스캔
# =========================================================================


_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def build_asset_listing(assets_dir: str | Path | None, limit: int = 30) -> str:
    """--assets-dir 지정 시 파일들을 카테고리별 목록 문자열로 변환.

    LLM 에 "이 중에서만 file 로 써!" 라고 못 박기 위한 용도.
    """
    if not assets_dir:
        return ""
    root = Path(assets_dir)
    if not root.exists() or not root.is_dir():
        return f"(assets-dir '{assets_dir}' 폴더 없음 — 플레이스홀더 파일명 사용)"

    videos, images, audios = [], [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in _VIDEO_EXTS:
            videos.append(str(p))
        elif ext in _IMAGE_EXTS:
            images.append(str(p))
        elif ext in _AUDIO_EXTS:
            audios.append(str(p))

    def _fmt(title: str, items: list[str]) -> str:
        if not items:
            return f"{title}: (없음)"
        shown = items[:limit]
        extra = f" ... ({len(items) - limit}개 더)" if len(items) > limit else ""
        return f"{title}:\n  " + "\n  ".join(shown) + extra

    return (
        "사용 가능한 에셋 (이 파일들만 file 인자로 사용 가능):\n"
        f"{_fmt('Videos', videos)}\n"
        f"{_fmt('Images', images)}\n"
        f"{_fmt('Audios', audios)}\n"
    )


# =========================================================================
# 시스템 프롬프트 조립
# =========================================================================


_EXAMPLE_RECIPE_SIMPLE = {
    "name": "hotel-promo-30s",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "operations": [
        {"op": "add_track", "args": {"type": "video", "name": "V1"}},
        {"op": "add_track", "args": {"type": "audio", "name": "BGM"}},
        {"op": "add_track", "args": {"type": "text", "name": "sub"}},
        {"op": "add_image", "args": {"file": "intro.jpg", "start": "0s", "duration": "2s", "track": "V1"}},
        {"op": "add_image", "args": {"file": "main.jpg", "start": "2s", "duration": "25s", "track": "V1"}},
        {"op": "add_image", "args": {"file": "outro.jpg", "start": "27s", "duration": "3s", "track": "V1"}},
        {"op": "add_audio", "args": {"file": "bgm.mp3", "start": "0s", "duration": "30s", "track": "BGM", "volume": 0.4}},
        {"op": "add_text", "args": {"text": "브랜드 이름", "start": "3s", "duration": "20s", "track": "sub",
                                      "size": 6.0, "color": [1, 1, 1],
                                      "clip_settings": {"transform_x": 0.0, "transform_y": -0.75}}},
    ],
}


_EXAMPLE_RECIPE_LYRIC = {
    "name": "lyric-short",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "operations": [
        {"op": "add_track", "args": {"type": "video", "name": "V1"}},
        {"op": "add_track", "args": {"type": "audio", "name": "A1"}},
        {"op": "add_track", "args": {"type": "text", "name": "lyrics"}},
        {"op": "add_image", "args": {"file": "bg.jpg", "start": "0s", "duration": "15s", "track": "V1"}},
        {"op": "add_audio", "args": {"file": "song.mp3", "start": "0s", "duration": "15s", "track": "A1"}},
        {"op": "add_text", "args": {"text": "첫 줄", "start": "0s", "duration": "5s", "track": "lyrics",
                                      "size": 7.0, "color": [1, 1, 1]}},
        {"op": "add_text", "args": {"text": "둘째 줄", "start": "5s", "duration": "5s", "track": "lyrics",
                                      "size": 7.0, "color": [1, 1, 1]}},
    ],
}


def build_system_prompt(width: int = 1080, height: int = 1920, fps: int = 30) -> str:
    """LLM 시스템 프롬프트.

    포함: op 이름 목록, 규칙, few-shot 예시 2개.
    """
    op_lines = "\n".join(_op_spec_lines())
    ex1 = json.dumps(_EXAMPLE_RECIPE_SIMPLE, ensure_ascii=False, indent=2)
    ex2 = json.dumps(_EXAMPLE_RECIPE_LYRIC, ensure_ascii=False, indent=2)
    return f"""You are a CapCut recipe generator for the `cli-anything-capcut` CLI.
Your task: turn a natural language Korean/English instruction into a valid
recipe JSON that can be fed into `cli-anything-capcut import-recipe`.

HARD RULES:
1. Output MUST be a single JSON object. No prose, no markdown — just JSON.
2. Top-level keys: "name" (string), "width" (int), "height" (int),
   "fps" (int), "operations" (array).
3. Default canvas: width={width}, height={height}, fps={fps}. Only change
   if the user explicitly asks.
4. Every element of "operations" is {{"op": <op_name>, "args": {{...}}}}.
5. "op" MUST be one of the allowed names below. NEVER invent new op names.
6. Before any add_video/add_image/add_audio/add_text/add_sticker/add_effect/add_filter,
   there MUST be a corresponding add_track in the operations list.
7. Times use strings like "0s", "2s", "500ms", "1m30s", "3000000us".
8. Colors use arrays of 3 floats in 0.0~1.0 range (e.g., [1.0, 1.0, 1.0] = white).
9. `file` fields: if the user provided an assets listing, use ONLY those paths.
   Otherwise use short filenames like "intro.mp4" as placeholders.
10. For subtitle position, use clip_settings transform_x/y
    (e.g., bottom sub = {{"transform_x": 0.0, "transform_y": -0.75}}).

ALLOWED OPS:
{op_lines}

EXAMPLE 1 — 30s hotel promo shorts with BGM+text:
{ex1}

EXAMPLE 2 — lyric video with audio and text per line:
{ex2}

Respond with ONLY the JSON recipe.
"""


# =========================================================================
# JSON 추출
# =========================================================================


_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


def extract_json_block(text: str) -> str:
    """LLM 응답에서 JSON 블록만 추출.

    1. ```json ... ``` 코드펜스가 있으면 그 안쪽
    2. 아니면 첫 ``{`` ~ 마지막 ``}`` 사이
    3. 그것도 아니면 원문 그대로 (호출자가 json.loads 시 에러로 전파)
    """
    if not isinstance(text, str):
        return ""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    stripped = text.strip()
    # 양 끝에서 중괄호 찾기
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start:end + 1]
    return stripped


# =========================================================================
# Claude API 호출
# =========================================================================


def _call_claude(
    system: str, user: str, *, model: str, max_tokens: int = 4096,
    extra_user: str = "",
) -> str:
    """Claude API 호출. SDK/키 부재 시 ClickException."""
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise click.ClickException(
            "anthropic SDK 가 설치되어 있지 않음. "
            "`pip install anthropic` 후 다시 시도."
        ) from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise click.ClickException(
            "ANTHROPIC_API_KEY 환경변수가 비어있음. "
            "콘솔에서 `setx ANTHROPIC_API_KEY sk-ant-...` 후 새 셸에서 재시도."
        )

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": user + ("\n\n" + extra_user if extra_user else "")}]
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    # 표준 응답 포맷: content=[{type: 'text', text: '...'}]
    parts: list[str] = []
    for blk in getattr(resp, "content", []):
        if isinstance(blk, dict):
            if blk.get("type") == "text":
                parts.append(blk.get("text", ""))
        else:
            # anthropic.types.TextBlock
            t = getattr(blk, "text", None)
            if t:
                parts.append(t)
    return "".join(parts)


# =========================================================================
# CLI 진입점
# =========================================================================


def _parse_size_spec(
    width: int, height: int, fps: int, duration: str | None
) -> tuple[int, int, int, str | None]:
    """옵션 기본값 보정."""
    return width, height, fps, duration


@click.command("plan", help="자연어 지시를 CapCut 레시피 JSON으로 변환 (Claude API)")
@click.argument("instruction")
@click.option("-o", "--output", default=None,
              help="파일로 저장. 생략 시 stdout.")
@click.option("--model", default="claude-sonnet-4-5",
              help="Claude 모델 이름", show_default=True)
@click.option("--duration", default=None, help="원하는 총 길이 (예: '30s')")
@click.option("--width", type=int, default=1080, show_default=True)
@click.option("--height", type=int, default=1920, show_default=True)
@click.option("--fps", type=int, default=30, show_default=True)
@click.option("--assets-dir", default=None,
              type=click.Path(exists=False, file_okay=False),
              help="LLM 에 주입할 에셋 폴더. 이 폴더의 파일만 file 인자로 사용됨")
@click.option("--max-tokens", type=int, default=4096, show_default=True)
@click.option("--no-retry", is_flag=True, default=False,
              help="validate 실패해도 재시도하지 않음")
@click.pass_context
def plan_cmd(ctx, instruction, output, model, duration, width, height, fps,
             assets_dir, max_tokens, no_retry):
    system = build_system_prompt(width=width, height=height, fps=fps)

    asset_section = build_asset_listing(assets_dir)
    duration_hint = f"\n원하는 총 길이: {duration}" if duration else ""
    user_prompt = (
        f"지시: {instruction}{duration_hint}\n\n"
        f"{asset_section}"
        "\n위 지시를 정확히 반영하는 recipe JSON 을 출력해."
    )

    raw = _call_claude(system, user_prompt, model=model, max_tokens=max_tokens)
    json_text = extract_json_block(raw)

    try:
        recipe = json.loads(json_text)
    except json.JSONDecodeError as e:
        if no_retry:
            raise click.ClickException(f"LLM 응답 JSON 파싱 실패: {e}\n원문: {raw[:500]}")
        # 재시도 — 파싱 에러 알려주고 다시 받기
        retry = _call_claude(
            system, user_prompt, model=model, max_tokens=max_tokens,
            extra_user=f"이전 응답 JSON 파싱 실패: {e}. JSON 객체만 출력해.",
        )
        json_text = extract_json_block(retry)
        try:
            recipe = json.loads(json_text)
        except json.JSONDecodeError as e2:
            raise click.ClickException(
                f"재시도 후에도 JSON 파싱 실패: {e2}\n원문: {retry[:500]}"
            )

    # 레시피 구조 검증
    report = validate_recipe(recipe)
    if not report["valid"] and not no_retry:
        # 에러 알려주고 한번 더
        err_txt = "; ".join(report["errors"])
        retry = _call_claude(
            system, user_prompt, model=model, max_tokens=max_tokens,
            extra_user=(
                f"이전 recipe 구조 검증 실패: {err_txt}. "
                "허용된 op 이름만 쓰고, operations 배열 안에 넣어."
            ),
        )
        json_text2 = extract_json_block(retry)
        try:
            recipe2 = json.loads(json_text2)
            report2 = validate_recipe(recipe2)
            if report2["valid"]:
                recipe, report = recipe2, report2
        except json.JSONDecodeError:
            pass

    if not report["valid"]:
        raise click.ClickException(
            "생성된 레시피가 유효하지 않음: " + "; ".join(report["errors"])
        )

    out_json = json.dumps(recipe, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(out_json, encoding="utf-8")
        output_result(
            {
                "status": "planned",
                "path": output,
                "op_count": report["op_count"],
                "warnings": report["warnings"],
            },
            ctx.obj.get("json", False),
        )
    else:
        click.echo(out_json)


# =========================================================================
# plan-refine — 피드백 루프
# =========================================================================


def build_refine_system_prompt(existing: dict, feedback: str) -> str:
    """기존 레시피 + 피드백을 기반으로 수정본 생성용 시스템 프롬프트.

    기존 ``build_system_prompt()`` 의 규칙/op 목록을 재사용하되,
    "이 레시피를 피드백대로 수정해" 라는 지시를 덧붙인다.
    """
    width = int(existing.get("width") or 1080)
    height = int(existing.get("height") or 1920)
    fps = int(existing.get("fps") or 30)
    base = build_system_prompt(width=width, height=height, fps=fps)

    existing_json = json.dumps(existing, ensure_ascii=False, indent=2)
    refine_block = (
        "\n\n=== REFINE MODE ===\n"
        "아래는 수정해야 할 기존 레시피다. 사용자 피드백에 맞춰 이 레시피를\n"
        "수정한 새 레시피를 출력해라. 전체 구조는 유지하되, 피드백이 명시적으로\n"
        "지시한 op/인자만 변경/추가/삭제. 필요 없는 변경은 하지 말 것.\n\n"
        "EXISTING RECIPE:\n"
        f"{existing_json}\n\n"
        "USER FEEDBACK (Korean or English):\n"
        f"{feedback.strip()}\n\n"
        "HARD RULES (동일):\n"
        "- 출력은 수정된 recipe JSON 객체 단 하나.\n"
        "- op 이름은 허용된 목록에서만.\n"
        "- 기존 op 의 id 필드가 있으면 가능한 한 유지 (변경이 꼭 필요할 때만).\n"
    )
    return base + refine_block


@click.command("plan-refine", help="기존 레시피를 자연어 피드백으로 수정 (Claude API)")
@click.option("-i", "--input", "input_path", required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="수정 대상 레시피 JSON 파일")
@click.option("-o", "--output", required=True,
              type=click.Path(dir_okay=False),
              help="수정된 레시피를 저장할 경로")
@click.option("--feedback", required=True, help="자연어 피드백 (한국어/영어)")
@click.option("--model", default="claude-sonnet-4-5",
              help="Claude 모델 이름", show_default=True)
@click.option("--max-tokens", type=int, default=4096, show_default=True)
@click.option("--no-retry", is_flag=True, default=False,
              help="validate 실패해도 재시도하지 않음")
@click.pass_context
def plan_refine_cmd(ctx, input_path, output, feedback, model, max_tokens, no_retry):
    # 1) 기존 레시피 로드
    try:
        existing = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"입력 레시피 JSON 파싱 실패: {e}")
    if not isinstance(existing, dict) or "operations" not in existing:
        raise click.ClickException("입력 레시피에 'operations' 없음 — 올바른 레시피 파일인지 확인.")

    # 2) 시스템 프롬프트 빌드
    system = build_refine_system_prompt(existing, feedback)
    user_prompt = (
        "위 레시피를 피드백대로 수정한 JSON 을 출력해. "
        "JSON 객체 하나만, 다른 설명은 넣지 말 것."
    )

    # 3) API 호출
    raw = _call_claude(system, user_prompt, model=model, max_tokens=max_tokens)
    json_text = extract_json_block(raw)

    # 4) 파싱 (재시도 1회)
    try:
        recipe = json.loads(json_text)
    except json.JSONDecodeError as e:
        if no_retry:
            raise click.ClickException(
                f"LLM 응답 JSON 파싱 실패: {e}\n원문: {raw[:500]}"
            )
        retry = _call_claude(
            system, user_prompt, model=model, max_tokens=max_tokens,
            extra_user=f"이전 응답 JSON 파싱 실패: {e}. JSON 객체 하나만 출력해.",
        )
        json_text = extract_json_block(retry)
        try:
            recipe = json.loads(json_text)
        except json.JSONDecodeError as e2:
            raise click.ClickException(
                f"재시도 후에도 JSON 파싱 실패: {e2}\n원문: {retry[:500]}"
            )

    # 5) 검증 + 재시도
    report = validate_recipe(recipe)
    if not report["valid"] and not no_retry:
        err_txt = "; ".join(report["errors"])
        retry = _call_claude(
            system, user_prompt, model=model, max_tokens=max_tokens,
            extra_user=(
                f"이전 응답 구조 검증 실패: {err_txt}. "
                "허용된 op 이름만, operations 배열 안에 넣어."
            ),
        )
        json_text2 = extract_json_block(retry)
        try:
            recipe2 = json.loads(json_text2)
            report2 = validate_recipe(recipe2)
            if report2["valid"]:
                recipe, report = recipe2, report2
        except json.JSONDecodeError:
            pass

    if not report["valid"]:
        raise click.ClickException(
            "수정된 레시피가 유효하지 않음: " + "; ".join(report["errors"])
        )

    # 6) 저장
    Path(output).write_text(
        json.dumps(recipe, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_result(
        {
            "status": "refined",
            "input": input_path,
            "path": output,
            "op_count": report["op_count"],
            "warnings": report["warnings"],
        },
        ctx.obj.get("json", False),
    )
