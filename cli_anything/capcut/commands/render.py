"""render 커맨드 — CapCut/JianYing GUI 자동화로 드래프트를 MP4로 export.

**제약**:
    - Windows 전용 (uiautomation 의존)
    - JianYing 6 및 이하 버전에서 안정적. 최신 CapCut international은 UI 구조가
      달라서 동작 안 할 수 있음
    - CapCut/JianYing이 이미 실행 중이어야 함 (해당 드래프트는 닫혀있어야 함)
    - VIP 기능이 포함된 드래프트는 export 시 무한 루프에 빠질 수 있음 (pyCapCut 경고)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


@click.command("render",
               help="드래프트를 MP4로 export (CapCut GUI 자동 제어)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-o", "--output", "output_path", default=None,
              help="출력 파일 또는 폴더 경로 (생략 시 CapCut 기본)")
@click.option("--resolution",
              type=click.Choice(["720P", "1080P", "2K", "4K", "8K"]), default=None)
@click.option("--framerate", type=click.Choice(["24", "25", "30", "50", "60"]), default=None)
@click.option("--timeout", type=float, default=1200, help="export 타임아웃(초). 기본 20분")
@click.option("--save-first", is_flag=True, default=False,
              help="render 전에 세션을 먼저 save (드래프트 갱신)")
@click.pass_context
def render_cmd(ctx, project_path, output_path, resolution, framerate, timeout, save_first):
    if sys.platform != "win32":
        raise click.ClickException(
            "render는 Windows 전용입니다 (uiautomation 필요). "
            "다른 플랫폼에서는 save로 드래프트만 생성하고 CapCut에서 수동 export하세요."
        )

    try:
        import pycapcut as cc
    except ImportError:
        raise click.ClickException("pycapcut이 설치되지 않음")

    # JianyingController는 Windows에서만 import 가능 (uiautomation 때문)
    try:
        from pycapcut.jianying_controller import (
            ExportFramerate,
            ExportResolution,
            JianyingController,
        )
    except ImportError as e:
        raise click.ClickException(
            f"JianyingController를 로드할 수 없음: {e}\n"
            "pip install uiautomation 으로 의존성 확인."
        )

    session = load_session(project_path)

    if save_first:
        # save_cmd 로직 인라인 (import cycle 방지용)
        try:
            script = session.replay()
        except Exception as e:
            raise click.ClickException(f"replay 실패: {e}")
        Path(session.draft_folder).mkdir(parents=True, exist_ok=True)
        draft_folder_obj = cc.DraftFolder(session.draft_folder)
        fresh = draft_folder_obj.create_draft(
            session.draft_name,
            session.data["width"],
            session.data["height"],
            session.data["fps"],
            allow_replace=True,
        )
        script.dump(str(Path(fresh.save_path)))
        session.save()

    # 해상도/프레임레이트 enum 매핑
    res_enum = None
    if resolution:
        res_enum = getattr(ExportResolution, f"RES_{resolution}", None)
        if res_enum is None:
            raise click.ClickException(f"지원하지 않는 해상도: {resolution}")
    fr_enum = None
    if framerate:
        fr_enum = getattr(ExportFramerate, f"FR_{framerate}", None)
        if fr_enum is None:
            raise click.ClickException(f"지원하지 않는 프레임레이트: {framerate}")

    # 실행
    try:
        controller = JianyingController()
        controller.export_draft(
            session.draft_name,
            output_path=output_path,
            resolution=res_enum,
            framerate=fr_enum,
            timeout=timeout,
        )
    except Exception as e:
        raise click.ClickException(
            f"export 실패: {type(e).__name__}: {e}\n"
            "CapCut이 실행 중이고 드래프트가 닫혀있는지, VIP 기능을 쓰지 않았는지 확인."
        )

    output_result(
        {
            "status": "rendered",
            "draft_name": session.draft_name,
            "output_path": output_path,
            "resolution": resolution,
            "framerate": framerate,
        },
        ctx.obj["json"],
    )
