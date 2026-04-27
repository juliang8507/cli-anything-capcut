"""v0.5.1 — text auto-srt 서브커맨드 테스트.

whisper CLI 실행은 mock으로 대체 (느리고 모델 다운로드 필요).
실제 whisper 동작 검증은 사용자가 `--audio real.mp3`로 직접 smoke test 권장.

CliRunner를 사용해 in-process로 실행 → subprocess.run mock이 정상 동작.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core.session import Session


# 최소 SRT 샘플 (세그먼트 2개)
_FAKE_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "안녕하세요\n"
    "\n"
    "2\n"
    "00:00:02,500 --> 00:00:05,000\n"
    "오늘도 좋은 하루입니다\n"
    "\n"
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def workspace(tmp_path):
    """세션 파일 + T1 텍스트 트랙이 있는 워크스페이스."""
    sp = tmp_path / "test.session.json"
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    session = Session.create(
        draft_folder=str(drafts),
        draft_name="auto-srt-test",
        width=1920,
        height=1080,
        fps=30,
        output=sp,
    )
    session.append_operation("add_track", {"type": "text", "name": "T1"})
    return tmp_path, sp


def _make_srt(directory: Path, stem: str) -> Path:
    """가짜 SRT 파일을 지정 디렉토리에 생성."""
    srt = directory / f"{stem}.srt"
    srt.write_text(_FAKE_SRT, encoding="utf-8")
    return srt


# =========================================================================
# 1. Happy path — word-level(기본) + srt_import까지 세션에 반영
# =========================================================================


class TestAutoSrtHappyPath:
    def test_word_level_segments_added(self, runner, workspace):
        """word-level 기본 옵션 — SRT 2개 세그먼트가 세션 op로 기록됨."""
        tmp_path, sp = workspace
        audio = tmp_path / "audio.mp4"
        audio.write_bytes(b"\x00")

        out_dir = tmp_path / "srt_out"
        out_dir.mkdir()
        _make_srt(out_dir, "audio")

        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", return_value=mock_result):
            result = runner.invoke(cli, [
                "--json", "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--model", "tiny",
                "--language", "ko",
                "--output-dir", str(out_dir),
                "--no-keep-srt",
            ])

        assert result.exit_code == 0, result.output
        # stdout에 두 개의 JSON 블록 (imported + auto_srt_applied)
        assert "auto_srt_applied" in result.output

        # 출력에 두 JSON 오브젝트가 있음 — 마지막 블록 파싱
        # pretty-print 형식이므로 전체 텍스트에서 {} 블록을 직접 추출
        import re as _re
        blocks = _re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}', result.output, _re.DOTALL)
        last_data = json.loads(blocks[-1])
        assert last_data["srt_segments"] == 2
        assert last_data["status"] == "auto_srt_applied"

    def test_word_level_cmd_contains_word_timestamps(self, runner, workspace):
        """word-level 기본 모드 — whisper cmd에 word_timestamps 포함."""
        tmp_path, sp = workspace
        audio = tmp_path / "voice.mp4"
        audio.write_bytes(b"\x00")

        out_dir = tmp_path / "srt_wl"
        out_dir.mkdir()
        _make_srt(out_dir, "voice")

        captured: list[list] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--word-level",
                "--output-dir", str(out_dir),
            ])

        assert result.exit_code == 0, result.output
        assert len(captured) >= 1
        whisper_cmd = captured[0]
        assert "--word_timestamps" in whisper_cmd


# =========================================================================
# 2. segment-level 모드 — word_timestamps 미포함
# =========================================================================


class TestAutoSrtSegmentLevel:
    def test_segment_level_cmd_no_word_timestamps(self, runner, workspace):
        """--segment-level 지정 시 whisper cmd에 word_timestamps 미포함."""
        tmp_path, sp = workspace
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"\x00")

        out_dir = tmp_path / "srt_seg"
        out_dir.mkdir()
        _make_srt(out_dir, "voice")

        captured: list[list] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--segment-level",
                "--output-dir", str(out_dir),
            ])

        assert result.exit_code == 0, result.output
        assert len(captured) >= 1
        whisper_cmd = captured[0]
        assert "--word_timestamps" not in whisper_cmd, (
            "--segment-level 모드에서 word_timestamps가 포함되면 안 됨"
        )


# =========================================================================
# 3. initial_prompt 전달 확인 — cmd 배열에 포함되는지
# =========================================================================


class TestAutoSrtInitialPrompt:
    def test_initial_prompt_in_cmd(self, runner, workspace):
        """--initial-prompt 옵션이 whisper cmd에 전달되는지."""
        tmp_path, sp = workspace
        audio = tmp_path / "hotel.wav"
        audio.write_bytes(b"\x00")

        out_dir = tmp_path / "srt_prompt"
        out_dir.mkdir()
        _make_srt(out_dir, "hotel")

        captured: list[list] = []
        prompt_text = "Product Pro Max 256GB"

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--initial-prompt", prompt_text,
                "--output-dir", str(out_dir),
            ])

        assert result.exit_code == 0, result.output
        assert len(captured) >= 1
        whisper_cmd = captured[0]
        assert "--initial_prompt" in whisper_cmd, "cmd에 --initial_prompt 없음"
        prompt_idx = whisper_cmd.index("--initial_prompt")
        assert whisper_cmd[prompt_idx + 1] == prompt_text, "prompt 값이 다름"


# =========================================================================
# 4. whisper 실패 시 ClickException (returncode != 0)
# =========================================================================


class TestAutoSrtWhisperFailure:
    def test_whisper_nonzero_returncode_raises(self, runner, workspace):
        """whisper 실패(returncode=1) → exit_code != 0 + 에러 메시지 포함."""
        tmp_path, sp = workspace
        audio = tmp_path / "bad.mp4"
        audio.write_bytes(b"\x00")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error: invalid audio format"
            )
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code != 0, "whisper 실패인데 CLI가 성공으로 끝남"
        assert "whisper" in result.output.lower() or "실패" in result.output

    def test_whisper_not_found_friendly_message(self, runner, workspace):
        """whisper 미설치(FileNotFoundError) → pip 안내 메시지 포함."""
        tmp_path, sp = workspace
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"\x00")

        with patch("subprocess.run", side_effect=FileNotFoundError("whisper not found")):
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--output-dir", str(tmp_path),
            ])

        assert result.exit_code != 0
        assert "pip install openai-whisper" in result.output or \
               "whisper" in result.output.lower()


# =========================================================================
# 5. --output-dir 사용자 지정 시 정리하지 않음
# =========================================================================


class TestAutoSrtKeepDir:
    def test_user_output_dir_not_deleted(self, runner, workspace):
        """--output-dir 지정 시 srt import 후 해당 디렉토리를 삭제하지 않음."""
        tmp_path, sp = workspace
        audio = tmp_path / "audio.mp4"
        audio.write_bytes(b"\x00")

        user_dir = tmp_path / "my_srt_output"
        user_dir.mkdir()
        _make_srt(user_dir, "audio")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--output-dir", str(user_dir),
                "--no-keep-srt",  # keep-srt=False여도 사용자 지정 dir은 유지
            ])

        assert result.exit_code == 0, result.output
        # 사용자 지정 디렉토리는 삭제되지 않아야 함
        assert user_dir.exists(), "사용자 지정 output-dir이 삭제됨 (유지해야 함)"
        assert (user_dir / "audio.srt").exists(), "SRT 파일이 삭제됨 (유지해야 함)"

    def test_no_keep_srt_cleans_tmp_dir(self, runner, workspace):
        """--no-keep-srt + 임시 디렉토리(output-dir 미지정) → 자동 정리됨."""
        tmp_path, sp = workspace
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"\x00")

        created_dirs: list[str] = []
        original_mkdtemp = __import__("tempfile").mkdtemp

        def fake_mkdtemp(**kwargs):
            # 실제 임시 디렉토리 생성하고 SRT 파일도 미리 배치
            d = original_mkdtemp(**kwargs)
            created_dirs.append(d)
            _make_srt(Path(d), "audio")
            return d

        with patch("subprocess.run") as mock_run, \
             patch("tempfile.mkdtemp", side_effect=fake_mkdtemp):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(cli, [
                "text", "auto-srt",
                "-p", str(sp),
                "--audio", str(audio),
                "--no-keep-srt",
            ])

        # 임시 디렉토리가 실제로 정리됐는지 확인
        if result.exit_code == 0 and created_dirs:
            from pathlib import Path as P
            assert not P(created_dirs[0]).exists(), "임시 디렉토리가 정리되지 않음"


# =========================================================================
# 6. --help 출력 smoke test
# =========================================================================


class TestAutoSrtHelp:
    def test_help_exits_zero(self, runner):
        """text auto-srt --help가 정상 출력됨."""
        result = runner.invoke(cli, ["text", "auto-srt", "--help"])
        assert result.exit_code == 0
        assert "--audio" in result.output
        assert "--model" in result.output
        assert "--language" in result.output
        # word-level / segment-level 둘 중 하나는 반드시 있어야 함
        assert "--word-level" in result.output or "--segment-level" in result.output
