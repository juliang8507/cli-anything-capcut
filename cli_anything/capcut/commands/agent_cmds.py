"""agent 그룹 — AI 에이전트 친화 출력."""

from __future__ import annotations

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


@click.group("agent", help="AI 에이전트 친화 명령")
def agent_group():
    pass


@agent_group.command("status", help="세션 종합 상태 + 다음 추천 작업")
@click.option("-p", "--project", "project_path", required=True)
@click.pass_context
def agent_status(ctx, project_path):
    session = load_session(project_path)
    status = session.status()

    # 추천 다음 작업 산출
    suggestions: list[str] = []
    ops = session.data.get("operations", [])
    if not ops:
        suggestions.append("프로젝트가 비어 있음. 'track add' → 'video/image/audio add'로 시작.")
    else:
        op_types = {o["op"] for o in ops}
        if not any(t.startswith("add_text") for t in op_types):
            suggestions.append("텍스트가 없음. 'text add'로 자막/타이틀 추가 가능.")
        if not any(t in op_types for t in ["add_video_transition", "add_video_fade",
                                            "add_video_animation"]):
            suggestions.append("전환/페이드/애니메이션 없음. 'video add-transition' 또는 'video add-fade' 추가 시 영상이 부드러워짐.")
        if status["validation"].get("valid") is False:
            suggestions.append(
                f"replay 실패: {status['validation'].get('error')}. "
                f"'validate'로 자세히 확인."
            )
        if status["overlaps"]:
            suggestions.append(f"세그먼트 겹침 {len(status['overlaps'])}건 있음. 'overlap-detect' 확인.")
        if status["gaps"]:
            suggestions.append(f"트랙에 갭 {len(status['gaps'])}건. 'gap-detect' 확인.")

    status["suggestions"] = suggestions
    output_result(status, ctx.obj["json"])


@agent_group.command("explain-error", help="에러 메시지 해석 + 추천 조치")
@click.option("--error", "-e", required=True, help="에러 메시지 텍스트")
@click.pass_context
def agent_explain(ctx, error):
    suggestions: list[str] = []
    error_lower = error.lower()

    if "segmentoverlap" in error_lower or "overlap" in error_lower:
        suggestions.append("세그먼트가 겹침. 같은 트랙에 동시 표시 불가. 별도 트랙 추가.")
    if "不存在名为" in error or "track" in error_lower and "not found" in error_lower:
        suggestions.append("트랙이 없음. 'track add'로 먼저 추가하거나 자동생성 op 사용.")
    if "keyerror" in error_lower:
        suggestions.append("enum 이름이 잘못됨. 'alias search'로 정확한 이름 검색.")
    if "ffprobe" in error_lower:
        suggestions.append("ffprobe 미설치. PATH에 ffmpeg/ffprobe 추가하거나 --duration 명시.")
    if "tim" in error_lower or "0us" in error_lower:
        suggestions.append("시간 표현 문제. '3s', '500ms', '1m30s' 형식 사용.")

    output_result(
        {"error": error, "suggestions": suggestions or ["일반 에러. 로그 전체 확인 권장."]},
        ctx.obj["json"],
    )
