"""preset 그룹 — 고수준 반복 패턴을 한 줄로.

각 프리셋은 내부에서 track add + image/audio/text add + transition/fade 등을
조합해서 세션에 순차 추가. 사용자는 "slideshow", "lyric-video" 같은 큰 단위로
생각하고 디테일은 옵션만 넘기면 됨.
"""

from __future__ import annotations

import glob
import random
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import (
    load_session,
    output_result,
    parse_color,
    parse_json_option,
    resolve_clip_settings,
)
from cli_anything.capcut.core.session import Session
from cli_anything.capcut.core.time_utils import parse_time_value
from cli_anything.capcut.utils.capcut_backend import require_draft_folder

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


@click.group("preset", help="고수준 조합 프리셋")
def preset_group():
    pass


# =========================================================================
# slideshow
# =========================================================================


@preset_group.command("slideshow", help="이미지 폴더 → 슬라이드쇼 드래프트")
@click.option("--name", "-n", required=True)
@click.option("--folder", "-f", required=True, type=click.Path(exists=True, file_okay=False),
              help="이미지들이 있는 폴더")
@click.option("--duration", default="3s", help="각 이미지당 표시 시간", show_default=True)
@click.option("--transition", default=None,
              help='이미지 사이 전환 (예: "dissolve"). 생략 시 컷')
@click.option("--transition-duration", default="500ms", show_default=True)
@click.option("--audio", default=None,
              help="배경 오디오 파일 (있으면 전체 타임라인에 깔림)")
@click.option("--preset-size", type=click.Choice(["landscape", "portrait", "square", "16x9", "9x16", "1x1"]),
              default="landscape")
@click.option("--fps", type=int, default=30, show_default=True)
@click.option("--draft-folder", default=None)
@click.option("--output", "-o", default=None, help="세션 JSON 저장 위치")
@click.option("--sort/--no-sort", default=True, help="파일명 정렬 (기본 정렬)")
@click.pass_context
def slideshow(ctx, name, folder, duration, transition, transition_duration, audio,
              preset_size, fps, draft_folder, output, sort):
    # 이미지 수집
    pattern_dir = Path(folder)
    images: list[Path] = []
    for ext in _IMAGE_EXTS:
        images.extend(pattern_dir.glob(f"*{ext}"))
    if sort:
        images.sort()
    if not images:
        raise click.ClickException(f"이미지 없음: {folder} ({', '.join(_IMAGE_EXTS)})")

    # 프로젝트 생성
    presets = {"landscape": (1920, 1080), "portrait": (1080, 1920), "square": (1080, 1080),
               "16x9": (1920, 1080), "9x16": (1080, 1920), "1x1": (1080, 1080)}
    width, height = presets[preset_size]
    folder_root = require_draft_folder(draft_folder)
    session = Session.create(folder_root, name, width=width, height=height, fps=fps,
                             output=output)

    dur_us = parse_time_value(duration)
    added_segment_ids: list[str] = []

    with session.batch():
        # 트랙
        session.append_operation("add_track", {"type": "video", "name": "V1"})
        if audio:
            session.append_operation("add_track", {"type": "audio", "name": "A1"})

        # 이미지 순차 추가
        cursor_us = 0
        for img in images:
            result = session.append_operation("add_image", {
                "file": str(img),
                "start": f"{cursor_us}us",
                "duration": f"{dur_us}us",
                "track": "V1",
            })
            added_segment_ids.append(result["id"])
            cursor_us += dur_us

        # 전환 (첫 세그먼트부터 마지막-1까지)
        if transition:
            td = parse_time_value(transition_duration)
            for sid in added_segment_ids[:-1]:
                session.append_operation("add_video_transition", {
                    "track": "V1",
                    "segment_ref": sid,
                    "name": transition,
                    "duration": f"{td}us",
                })

        # 오디오
        if audio:
            session.append_operation("add_audio", {
                "file": audio,
                "start": "0s",
                "duration": f"{cursor_us}us",
                "track": "A1",
            })

    output_result(
        {
            "status": "slideshow_created",
            "session_path": str(session.path),
            "image_count": len(images),
            "total_duration_us": cursor_us,
            "with_audio": bool(audio),
            "with_transition": bool(transition),
        },
        ctx.obj["json"],
    )


# =========================================================================
# lyric-video
# =========================================================================


@preset_group.command("lyric-video", help="오디오 + SRT 가사 → 가사 자막 영상")
@click.option("--name", "-n", required=True)
@click.option("--audio", "-a", required=True, type=click.Path(exists=True))
@click.option("--srt", "-s", required=True, type=click.Path(exists=True))
@click.option("--background", "-b", default=None,
              help="배경 이미지 또는 비디오 (오디오 전체 길이로 늘림)")
@click.option("--font", default=None)
@click.option("--text-size", type=float, default=8.0, show_default=True)
@click.option("--text-color", default="1.0,1.0,1.0", show_default=True)
@click.option("--text-border/--no-text-border", default=True,
              help="검정 테두리 자동 추가")
@click.option("--position", default="subtitle-bottom",
              help="가사 위치 프리셋 (subtitle-bottom/title-top 등)", show_default=True)
@click.option("--preset-size", type=click.Choice(["landscape", "portrait", "square"]),
              default="portrait")
@click.option("--fps", type=int, default=30, show_default=True)
@click.option("--draft-folder", default=None)
@click.option("--output", "-o", default=None)
@click.pass_context
def lyric_video(ctx, name, audio, srt, background, font, text_size, text_color,
                text_border, position, preset_size, fps, draft_folder, output):
    from cli_anything.capcut.commands.text import _parse_srt

    # 프로젝트
    presets = {"landscape": (1920, 1080), "portrait": (1080, 1920), "square": (1080, 1080)}
    width, height = presets[preset_size]
    folder_root = require_draft_folder(draft_folder)
    session = Session.create(folder_root, name, width=width, height=height, fps=fps,
                             output=output)

    srt_content = Path(srt).read_text(encoding="utf-8-sig")
    entries = _parse_srt(srt_content)
    if not entries:
        raise click.ClickException("SRT 파싱 실패 또는 엔트리 없음")

    total_us = max(e["end_us"] for e in entries)
    color_arr = parse_color(text_color)
    clip_dict = resolve_clip_settings(position) or {}
    border_dict = {"alpha": 1.0, "color": [0, 0, 0], "width": 0.08} if text_border else None

    with session.batch():
        # 트랙
        session.append_operation("add_track", {"type": "video", "name": "V1"})
        session.append_operation("add_track", {"type": "audio", "name": "A1"})
        session.append_operation("add_track", {"type": "text", "name": "lyrics"})

        # 배경
        if background:
            session.append_operation("add_image", {
                "file": background,
                "start": "0s",
                "duration": f"{total_us}us",
                "track": "V1",
            })
        # 오디오
        session.append_operation("add_audio", {
            "file": audio,
            "start": "0s",
            "duration": f"{total_us}us",
            "track": "A1",
        })
        # 가사
        for e in entries:
            dur_us = e["end_us"] - e["start_us"]
            session.append_operation("add_text", {
                "text": e["text"],
                "start": f"{e['start_us']}us",
                "duration": f"{dur_us}us",
                "track": "lyrics",
                "font": font,
                "size": text_size,
                "color": color_arr,
                "border": border_dict,
                "clip_settings": dict(clip_dict) if clip_dict else None,
            })

    output_result(
        {
            "status": "lyric_video_created",
            "session_path": str(session.path),
            "lyric_count": len(entries),
            "total_duration_us": total_us,
        },
        ctx.obj["json"],
    )


# =========================================================================
# intro-outro wrap
# =========================================================================


@preset_group.command("intro-outro", help="기존 세션에 인트로/아웃트로 이미지 붙이기")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--intro", default=None, type=click.Path(exists=True))
@click.option("--intro-duration", default="3s", show_default=True)
@click.option("--outro", default=None, type=click.Path(exists=True))
@click.option("--outro-duration", default="3s", show_default=True)
@click.option("--transition", default="dissolve", show_default=True)
@click.option("--transition-duration", default="500ms", show_default=True)
@click.option("--video-track", default="V1", show_default=True)
@click.pass_context
def intro_outro(ctx, project_path, intro, intro_duration, outro, outro_duration,
                transition, transition_duration, video_track):
    if not intro and not outro:
        raise click.ClickException("--intro 또는 --outro 중 하나는 필요")

    session = load_session(project_path)

    # 기존 세그먼트들의 시간을 뒤로 미룸 (intro 길이만큼)
    if intro:
        intro_us = parse_time_value(intro_duration)
        # 기존 비디오/오디오 op의 start를 +intro_us 만큼
        for op in session.data["operations"]:
            if op["op"] in ("add_video", "add_image", "add_audio", "add_text",
                            "add_sticker", "add_effect", "add_filter"):
                a = op.get("args", {})
                if a.get("track") == video_track or True:
                    # 모든 미디어 op에 대해 (텍스트/오디오 포함)
                    cur_start = parse_time_value(a.get("start", 0))
                    a["start"] = f"{cur_start + intro_us}us"

    # 각 추가를 배치 밖에서 session.append_operation으로 (start 계산 순서 보존)
    added: list[str] = []
    td = parse_time_value(transition_duration)

    if intro:
        intro_us = parse_time_value(intro_duration)
        result = session.append_operation("add_image", {
            "file": intro,
            "start": "0s",
            "duration": f"{intro_us}us",
            "track": video_track,
        })
        if transition:
            session.append_operation("add_video_transition", {
                "track": video_track,
                "segment_ref": result["id"],
                "name": transition,
                "duration": f"{td}us",
            })
        added.append("intro")

    if outro:
        # 기존 마지막 시점 계산
        from cli_anything.capcut.core.time_utils import calc_auto_start
        last_us = calc_auto_start(session.data, video_track)
        outro_us = parse_time_value(outro_duration)
        result = session.append_operation("add_image", {
            "file": outro,
            "start": f"{last_us}us",
            "duration": f"{outro_us}us",
            "track": video_track,
        })
        # 바로 직전 세그먼트에 전환 걸기 (찾아서)
        added.append("outro")

    # 파일 갱신
    session.save()
    output_result({"status": "wrapped", "added": added}, ctx.obj["json"])


# =========================================================================
# reaction-pip (PIP = Picture-in-Picture)
# =========================================================================


@preset_group.command("pip", help="기존 세그먼트 위에 PIP 오버레이 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True))
@click.option("--start", default="0s", show_default=True)
@click.option("--duration", default=None)
@click.option("--corner", type=click.Choice(["top-left", "top-right", "bottom-left", "bottom-right"]),
              default="top-right")
@click.option("--scale", type=float, default=0.35, show_default=True)
@click.option("--track", default="PIP", help="PIP 트랙 이름 (자동 생성)", show_default=True)
@click.pass_context
def pip(ctx, project_path, file, start, duration, corner, scale, track):
    session = load_session(project_path)
    preset_map = {
        "top-right": {"transform_x": 0.55, "transform_y": 0.65},
        "top-left": {"transform_x": -0.55, "transform_y": 0.65},
        "bottom-right": {"transform_x": 0.55, "transform_y": -0.65},
        "bottom-left": {"transform_x": -0.55, "transform_y": -0.65},
    }
    clip = {"scale_x": scale, "scale_y": scale, **preset_map[corner]}

    with session.batch():
        session.append_operation("add_track", {"type": "video", "name": track})
        op_name = "add_video" if str(file).lower().endswith((".mp4", ".mov", ".mkv", ".webm")) else "add_image"
        result = session.append_operation(op_name, {
            "file": file,
            "start": start,
            "duration": duration,
            "track": track,
            "clip_settings": clip,
        })
    output_result({"status": "pip_added", "op": result}, ctx.obj["json"])


# =========================================================================
# hook — 첫 3초 훅 자동 생성 (shake + zoom + flash + bold text)
# =========================================================================
# references/content-formulas.md 섹션 1.3 "3-Layer Stack" 공식 구현:
#   텍스트(5~8단어 bold) + 비주얼(zoom_in + shake) + SFX(flash 이펙트)
#   → 3-second hold 3배 상승 (음소거 환경 대응)
#
# 이 프리셋은 기존 세션(Phase 1~2 구성 완료)의 맨 앞(0~target duration)에
# 훅 레이어를 자동으로 끼워넣음. 영상 본체는 그대로 유지.
# =========================================================================


@preset_group.command("hook", help="첫 3초 훅 자동 생성 — shake + zoom + flash + bold text (3-Layer Stack)")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-t", "--text", required=True, help='훅 텍스트 (5~8 단어 권장). 예: "이거 모르면 30% 더 낸다"')
@click.option("--duration", default="3s", show_default=True, help="훅 지속 시간. 쇼츠/릴스는 2~3초 권장")
@click.option("--category", type=click.Choice([
    "curiosity", "number", "pattern-interrupt", "promise",
    "contrarian", "fear", "question", "authority", "pov", "shock"
]), default="pattern-interrupt", show_default=True,
    help="훅 10 카테고리 중 — 시각 연출 자동 매핑 (content-formulas.md 섹션 1.2)")
@click.option("--video-track", default="V1", show_default=True,
    help="훅 효과를 적용할 영상 트랙")
@click.option("--text-track", default="T_HOOK", show_default=True,
    help="훅 텍스트 전용 트랙 (자동 생성)")
@click.option("--font", default="Black Han Sans", show_default=True,
    help="훅 폰트 (anti-slop: Inter/Arial 금지)")
@click.option("--size", type=float, default=8.0, show_default=True,
    help="쇼츠=8~10, 본편=6~7 권장")
@click.option("--color", default="255,255,255", show_default=True,
    help='"R,G,B" (0~255) 또는 "R,G,B"(0~1)')
@click.option("--zoom", type=float, default=1.08, show_default=True,
    help="zoom_in 최종 배율 (1.05~1.15 권장)")
@click.option("--shake/--no-shake", default=True, show_default=True,
    help="shake 효과 동시 적용 여부")
@click.option("--flash/--no-flash", default=True, show_default=True,
    help="flash 이펙트 (0.1초) 동시 적용")
@click.pass_context
def hook(ctx, project_path, text, duration, category, video_track, text_track,
         font, size, color, zoom, shake, flash):
    """Phase 2-7 훅 레이어 자동 생성.

    카테고리별 연출 차이:
      - curiosity / shock     → flash 강함 + zoom 1.10
      - pattern-interrupt     → shake 강함 + color invert flash
      - number                → 숫자 카운트다운 권장 (현재는 기본 훅만)
      - contrarian / fear     → 느린 zoom + 진지한 톤 (shake 약)
      - question              → 큰 텍스트 중앙
      - authority / pov       → 부드러운 zoom, shake X
    """
    session = load_session(project_path)
    dur_us = parse_time_value(duration)

    # 카테고리별 연출 오버라이드
    category_tweaks = {
        "curiosity":        {"shake_intensity": 0.6, "flash_dur": "0.15s"},
        "shock":            {"shake_intensity": 0.7, "flash_dur": "0.15s"},
        "pattern-interrupt": {"shake_intensity": 0.9, "flash_dur": "0.1s"},
        "number":           {"shake_intensity": 0.3, "flash_dur": "0.1s"},
        "promise":          {"shake_intensity": 0.4, "flash_dur": "0.1s"},
        "contrarian":       {"shake_intensity": 0.2, "flash_dur": "0.08s"},
        "fear":             {"shake_intensity": 0.3, "flash_dur": "0.12s"},
        "question":         {"shake_intensity": 0.3, "flash_dur": "0.1s"},
        "authority":        {"shake_intensity": 0.1, "flash_dur": "0s"},
        "pov":              {"shake_intensity": 0.2, "flash_dur": "0.08s"},
    }
    tweak = category_tweaks[category]

    rgb = parse_color(color)
    ops_summary = {"category": category, "text": text, "duration": duration, "ops": []}

    with session.batch():
        # 1) 텍스트 트랙 생성 (emphasis 계층)
        session.append_operation("add_track", {"type": "text", "name": text_track})

        # 2) 훅 텍스트 세그먼트 (0s ~ duration)
        text_result = session.append_operation("add_text", {
            "text": text,
            "start": "0s",
            "duration": duration,
            "track": text_track,
            "font": font,
            "size": size,
            "bold": True,
            "color": rgb,
            "clip_settings": "title-center",
        })
        ops_summary["ops"].append({"op": "add_text", "id": text_result.get("id")})

        # 3) 텍스트 intro 애니메이션 (pop/scale) — 단어별 강조
        text_anim_name = "pop" if category in ("shock", "pattern-interrupt", "promise") else "fade_in"
        session.append_operation("add_text_animation", {
            "track": text_track,
            "segment_ref": text_result.get("id"),
            "role": "intro",
            "name": text_anim_name,
            "duration": "0.4s",
        })
        ops_summary["ops"].append({"op": "add_text_animation", "role": "intro", "name": text_anim_name})

        # 4) 영상 zoom_in 키프레임 (duration 동안 1.0 → zoom)
        #    기존 V1 첫 세그먼트에 적용 — session이 V1 첫 op_0 참조 가능하다고 가정
        #    (실패 시 사용자가 --video-track 으로 지정)
        try:
            first_v = session.first_segment_on_track(video_track)
            if first_v:
                session.append_operation("add_keyframe", {
                    "track": video_track,
                    "segment_ref": first_v,
                    "property": "uniform_scale",
                    "time": "0s",
                    "value": 1.0,
                })
                session.append_operation("add_keyframe", {
                    "track": video_track,
                    "segment_ref": first_v,
                    "property": "uniform_scale",
                    "time": duration,
                    "value": zoom,
                })
                ops_summary["ops"].append({"op": "keyframe", "property": "uniform_scale",
                                            "range": f"1.0 → {zoom}"})
        except AttributeError:
            # Session 객체가 first_segment_on_track 미지원이면 스킵
            ops_summary["warnings"] = ops_summary.get("warnings", [])
            ops_summary["warnings"].append(
                f"video_track {video_track}에 첫 세그먼트 자동 감지 실패. zoom 키프레임은 수동 추가 필요."
            )

        # 5) shake 효과 (category에 따라 강도 조정)
        if shake and tweak["shake_intensity"] > 0:
            session.append_operation("add_effect", {
                "name": "shake",
                "start": "0s",
                "duration": duration,
                "intensity": tweak["shake_intensity"],
            })
            ops_summary["ops"].append({"op": "effect", "name": "shake",
                                        "intensity": tweak["shake_intensity"]})

        # 6) flash 이펙트 (카테고리별 짧은 깜빡임)
        if flash and tweak["flash_dur"] != "0s":
            session.append_operation("add_effect", {
                "name": "flash",
                "start": "0s",
                "duration": tweak["flash_dur"],
            })
            ops_summary["ops"].append({"op": "effect", "name": "flash",
                                        "duration": tweak["flash_dur"]})

    ops_summary["status"] = "hook_added"
    ops_summary["layer_count"] = len(ops_summary["ops"])
    output_result(ops_summary, ctx.obj["json"])


# =========================================================================
# kenburns — 이미지 폴더에 Ken Burns (줌/패닝) 키프레임 자동 생성
# =========================================================================
# 원리: 각 이미지를 add_image로 추가하고, uniform_scale / transform_x /
# transform_y 에 키프레임 2개씩 걸어서 부드러운 줌·패닝 효과를 만든다.
# render_headless.py가 uniform_scale 키프레임 선형 보간을 내부 지원하므로
# 이 프리셋은 "키프레임 자동 생성 매크로" 역할만 담당.
# =========================================================================


@preset_group.command("kenburns", help="이미지 폴더 → Ken Burns 줌/패닝 키프레임 자동 생성")
@click.option("-p", "--project", "project_path", required=True, help="세션 JSON 파일 경로")
@click.option("--folder", default=None, type=click.Path(file_okay=False),
              help="이미지 폴더 경로 (--images와 택1)")
@click.option("--images", default=None,
              help="glob 패턴으로 이미지 지정 (--folder와 택1). 예: 'D:/imgs/*.jpg'")
@click.option("--duration-each", default="4s", show_default=True,
              help="각 이미지 표시 시간. 'auto' 금지, 반드시 초 단위 명시")
@click.option("--pattern", type=click.Choice(["alternating", "random", "zoom-in", "zoom-out", "pan-lr", "pan-tb"]),
              default="alternating", show_default=True,
              help="Ken Burns 패턴. alternating=줌인/아웃 교대, random=무작위, zoom-in/out=전부 동일 방향, pan-lr/tb=패닝")
@click.option("--intensity", type=float, default=0.2, show_default=True,
              help="줌 강도 (0.1~0.3 권장). scale_end = 1 + intensity")
@click.option("--track", default="V1", show_default=True,
              help="이미지를 배치할 영상 트랙")
@click.option("--start", default="0s", show_default=True,
              help="타임라인 시작 오프셋")
@click.option("--sort/--no-sort", default=True, show_default=True,
              help="파일명 정렬 (기본 정렬)")
@click.option("--seed", type=int, default=None,
              help="random 패턴 재현성용 시드 (생략 시 매번 무작위)")
@click.pass_context
def kenburns(ctx, project_path, folder, images, duration_each, pattern,
             intensity, track, start, sort, seed):
    """Ken Burns 효과 매크로.

    패턴별 동작:
      - alternating  → 짝수 이미지: 줌인(1.0→1+intensity), 홀수: 줌아웃(1+intensity→1.0)
      - zoom-in      → 전부 줌인
      - zoom-out     → 전부 줌아웃
      - random       → zoom-in/out/pan-lr/pan-tb 중 무작위 선택 (--seed로 재현 가능)
      - pan-lr       → 왼→오른 패닝 (scale=1.1 고정)
      - pan-tb       → 위→아래 패닝 (scale=1.1 고정)
    """
    # 이미지 소스 검증: folder / images 중 정확히 하나만
    if folder and images:
        raise click.ClickException("--folder 와 --images 는 동시에 사용 불가. 하나만 지정할 것.")
    if not folder and not images:
        raise click.ClickException("--folder 또는 --images 중 하나는 반드시 지정해야 함.")

    # 이미지 수집
    img_paths: list[Path] = []
    if folder:
        folder_path = Path(folder)
        if not folder_path.exists():
            raise click.ClickException(f"폴더 없음: {folder}")
        for ext in _IMAGE_EXTS:
            img_paths.extend(folder_path.glob(f"*{ext}"))
    else:
        # glob 패턴
        matched = glob.glob(images)
        img_paths = [Path(p) for p in matched
                     if Path(p).suffix.lower() in _IMAGE_EXTS]

    if sort:
        img_paths.sort()
    if not img_paths:
        raise click.ClickException(
            f"이미지 없음 (확장자: {', '.join(_IMAGE_EXTS)}). "
            f"경로/패턴을 다시 확인할 것."
        )

    # duration 검증 (auto 금지)
    if duration_each.strip().lower() == "auto":
        raise click.ClickException("--duration-each 에 'auto' 사용 불가. 초 단위 명시 필수. 예: '4s'")

    dur_us = parse_time_value(duration_each)
    start_us = parse_time_value(start)

    # random 패턴용 RNG
    rng = random.Random(seed)
    _random_pool = ["zoom-in", "zoom-out", "pan-lr", "pan-tb"]

    session = load_session(project_path)

    ops_summary = {
        "pattern": pattern,
        "intensity": intensity,
        "image_count": len(img_paths),
        "duration_each": duration_each,
        "track": track,
        "seed": seed,
        "images": [],
        "ops": [],
    }

    with session.batch():
        cursor_us = start_us

        for idx, img in enumerate(img_paths):
            # 실제 적용할 패턴 결정
            if pattern == "alternating":
                effective = "zoom-in" if idx % 2 == 0 else "zoom-out"
            elif pattern == "random":
                effective = rng.choice(_random_pool)
            else:
                effective = pattern  # zoom-in / zoom-out / pan-lr / pan-tb

            # add_image
            img_result = session.append_operation("add_image", {
                "file": str(img),
                "start": f"{cursor_us}us",
                "duration": f"{dur_us}us",
                "track": track,
            })
            seg_id = img_result["id"]
            img_entry = {
                "index": idx,
                "file": img.name,
                "seg_id": seg_id,
                "effective_pattern": effective,
                "keyframes": [],
            }

            # 패턴별 키프레임 추가
            if effective in ("zoom-in", "zoom-out"):
                scale_start = 1.0 if effective == "zoom-in" else (1.0 + intensity)
                scale_end   = (1.0 + intensity) if effective == "zoom-in" else 1.0

                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us}us",
                    "value": scale_start,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us + dur_us}us",
                    "value": scale_end,
                })
                img_entry["keyframes"].extend([
                    {"property": "uniform_scale", "from": scale_start, "to": scale_end},
                ])

            elif effective == "pan-lr":
                # 좌→우 패닝: scale 1.1 고정, transform_x -0.05 → +0.05
                pan_scale = 1.0 + max(0.1, intensity)
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us}us",
                    "value": pan_scale,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us + dur_us}us",
                    "value": pan_scale,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "transform_x",
                    "time": f"{cursor_us}us",
                    "value": -0.05,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "transform_x",
                    "time": f"{cursor_us + dur_us}us",
                    "value": 0.05,
                })
                img_entry["keyframes"].extend([
                    {"property": "uniform_scale", "fixed": pan_scale},
                    {"property": "transform_x", "from": -0.05, "to": 0.05},
                ])

            elif effective == "pan-tb":
                # 위→아래 패닝: scale 1.1 고정, transform_y -0.05 → +0.05
                pan_scale = 1.0 + max(0.1, intensity)
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us}us",
                    "value": pan_scale,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "uniform_scale",
                    "time": f"{cursor_us + dur_us}us",
                    "value": pan_scale,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "transform_y",
                    "time": f"{cursor_us}us",
                    "value": -0.05,
                })
                session.append_operation("add_keyframe", {
                    "track": track,
                    "segment_ref": seg_id,
                    "property": "transform_y",
                    "time": f"{cursor_us + dur_us}us",
                    "value": 0.05,
                })
                img_entry["keyframes"].extend([
                    {"property": "uniform_scale", "fixed": pan_scale},
                    {"property": "transform_y", "from": -0.05, "to": 0.05},
                ])

            ops_summary["images"].append(img_entry)
            ops_summary["ops"].append({
                "op": "add_image",
                "id": seg_id,
                "file": img.name,
            })
            ops_summary["ops"].append({
                "op": "add_keyframe",
                "seg_id": seg_id,
                "effective_pattern": effective,
            })

            cursor_us += dur_us

    ops_summary["status"] = "kenburns_added"
    ops_summary["total_duration_us"] = cursor_us - start_us
    ops_summary["op_count"] = len(ops_summary["ops"])
    output_result(ops_summary, ctx.obj["json"])
