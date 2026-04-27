"""asset 그룹 — 미디어 자산 관리 (bulk-import/transcode/relocate/cover)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from cli_anything.capcut.commands.helpers import load_session, output_result


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
_AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac")


@click.group("asset", help="미디어 자산 관리")
def asset_group():
    pass


@asset_group.command("bulk-import", help="폴더의 모든 미디어를 자동 분류해 추가")
@click.option("-p", "--project", "project_path", required=True)
@click.option("--folder", "-f", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--video-track", default="V1")
@click.option("--audio-track", default="A1")
@click.option("--image-duration", default="3s", help="이미지 기본 duration")
@click.option("--sort/--no-sort", default=True)
@click.pass_context
def bulk_import(ctx, project_path, folder, video_track, audio_track, image_duration, sort):
    session = load_session(project_path)
    files: list[Path] = []
    for p in Path(folder).iterdir():
        if p.is_file():
            files.append(p)
    if sort:
        files.sort(key=lambda x: x.name)

    stats = {"image": 0, "video": 0, "audio": 0, "skipped": 0}
    added: list[str] = []

    with session.batch():
        # 트랙이 없으면 추가
        session.append_operation("add_track", {"type": "video", "name": video_track})
        session.append_operation("add_track", {"type": "audio", "name": audio_track})

        for f in files:
            ext = f.suffix.lower()
            if ext in _IMAGE_EXTS:
                result = session.append_operation("add_image", {
                    "file": str(f),
                    "start": "auto",
                    "duration": image_duration,
                    "track": video_track,
                })
                added.append(result["id"])
                stats["image"] += 1
            elif ext in _VIDEO_EXTS:
                result = session.append_operation("add_video", {
                    "file": str(f),
                    "start": "auto",
                    "track": video_track,
                })
                added.append(result["id"])
                stats["video"] += 1
            elif ext in _AUDIO_EXTS:
                result = session.append_operation("add_audio", {
                    "file": str(f),
                    "start": "auto",
                    "track": audio_track,
                })
                added.append(result["id"])
                stats["audio"] += 1
            else:
                stats["skipped"] += 1

    output_result({"status": "bulk_imported", **stats, "added_count": len(added)},
                  ctx.obj["json"])


@asset_group.command("transcode", help="ffmpeg로 파일 포맷 변환 (opinionated 기본값)")
@click.option("-i", "--input", "input_path", required=True, type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True)
@click.option("--video-codec", default="libx264", show_default=True,
              type=click.Choice(["libx264", "libx265", "libvpx-vp9", "copy"]))
@click.option("--audio-codec", default="aac", show_default=True,
              type=click.Choice(["aac", "libmp3lame", "libopus", "copy"]))
@click.option("--crf", type=click.IntRange(0, 51), default=23, show_default=True,
              help="x264/x265 품질 (18~28 권장, 낮을수록 고품질)")
@click.option("--preset", default="medium", show_default=True,
              type=click.Choice(["ultrafast", "veryfast", "fast", "medium", "slow", "slower"]))
@click.pass_context
def transcode(ctx, input_path, output_path, video_codec, audio_codec, crf, preset):
    if not shutil.which("ffmpeg"):
        raise click.ClickException("ffmpeg이 PATH에 없음. 설치 후 다시 시도.")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", video_codec, "-preset", preset, "-crf", str(crf),
        "-c:a", audio_codec, "-b:a", "192k",
        str(output_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        raise click.ClickException("ffmpeg timeout (1시간 초과)")
    if proc.returncode != 0:
        raise click.ClickException(f"ffmpeg 실패:\n{proc.stderr[-500:]}")
    output_result(
        {"status": "transcoded", "input": str(input_path), "output": str(output_path)},
        ctx.obj["json"],
    )


@asset_group.command("relocate", help="세션이 참조하는 모든 미디어를 한 폴더로 복사")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-o", "--output", "output_dir", required=True,
              help="복사 대상 폴더 (없으면 생성)")
@click.option("--update-session/--no-update", default=True,
              help="세션의 파일 경로를 새 위치로 갱신")
@click.pass_context
def relocate(ctx, project_path, output_dir, update_session):
    session = load_session(project_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    copied: list[dict] = []
    skipped: list[dict] = []
    path_map: dict[str, str] = {}

    for op in session.data["operations"]:
        a = op.get("args", {})
        f = a.get("file")
        if not f:
            continue
        src = Path(f)
        if not src.exists():
            skipped.append({"op_id": op["id"], "file": f, "reason": "missing"})
            continue
        if f in path_map:
            a["file"] = path_map[f]
            continue
        # 이름 충돌 시 suffix 추가
        dst = out_path / src.name
        if dst.exists() and not _same_file(src, dst):
            stem, ext = src.stem, src.suffix
            i = 1
            while True:
                dst = out_path / f"{stem}_{i}{ext}"
                if not dst.exists():
                    break
                i += 1
        shutil.copy2(src, dst)
        path_map[f] = str(dst)
        copied.append({"from": f, "to": str(dst)})
        if update_session:
            a["file"] = str(dst)

    if update_session:
        session.save()

    output_result(
        {"status": "relocated",
         "copied_count": len(copied), "skipped_count": len(skipped),
         "output_dir": str(out_path),
         "updated_session": update_session},
        ctx.obj["json"],
    )


@asset_group.command("cover-from-frame",
                     help="비디오 파일에서 특정 프레임을 드래프트 커버로 추출")
@click.option("-p", "--project", "project_path", required=True)
@click.option("-f", "--file", required=True, type=click.Path(exists=True))
@click.option("--time", "ts", default="0s", help="추출할 시각 (예: 2s, 1m30s)")
@click.pass_context
def cover_from_frame(ctx, project_path, file, ts):
    if not shutil.which("ffmpeg"):
        raise click.ClickException("ffmpeg 필요.")
    from cli_anything.capcut.core.time_utils import parse_time_value

    session = load_session(project_path)
    draft_path = Path(session.draft_folder) / session.draft_name
    draft_path.mkdir(parents=True, exist_ok=True)
    cover_out = draft_path / "draft_cover.jpg"

    seconds = parse_time_value(ts) / 1_000_000
    cmd = [
        "ffmpeg", "-y", "-ss", f"{seconds}", "-i", str(file),
        "-frames:v", "1", "-q:v", "2", str(cover_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise click.ClickException(f"ffmpeg 실패:\n{proc.stderr[-500:]}")
    output_result({"status": "cover_saved", "path": str(cover_out)}, ctx.obj["json"])


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_size == b.stat().st_size and a.read_bytes()[:256] == b.read_bytes()[:256]
    except OSError:
        return False
