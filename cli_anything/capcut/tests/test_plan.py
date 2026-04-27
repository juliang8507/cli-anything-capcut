"""plan 커맨드 (자연어 → 레시피) 유닛 테스트.

실제 Claude API 호출은 유료라 기본은 스킵. 프롬프트 빌더/JSON 추출기 같은
순수 함수만 빠르게 검증.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

from cli_anything.capcut.commands import plan as plan_mod


# =========================================================================
# 프롬프트 빌더
# =========================================================================


class TestSystemPrompt:
    def test_contains_known_ops(self):
        p = plan_mod.build_system_prompt()
        for op in ("add_track", "add_video", "add_image",
                    "add_audio", "add_text", "add_video_animation",
                    "add_video_transition"):
            assert op in p, f"시스템 프롬프트에 {op} 없음"

    def test_contains_canvas_defaults(self):
        p = plan_mod.build_system_prompt(width=1080, height=1920, fps=30)
        assert "1080" in p
        assert "1920" in p
        assert "fps=30" in p

    def test_example_recipes_included(self):
        p = plan_mod.build_system_prompt()
        # 예시에 등장하는 문자열 중 일부가 실제 들어있어야
        assert "hotel-promo-30s" in p
        assert "lyric-short" in p

    def test_known_ops_matches_registry(self):
        """LLM 프롬프트 op 리스트가 실제 핸들러 등록 op 와 일치해야."""
        from cli_anything.capcut.core.op_handlers import list_ops as real_list_ops
        assert set(plan_mod.known_ops()) == set(real_list_ops())


# =========================================================================
# JSON 추출
# =========================================================================


class TestJSONExtraction:
    def test_extract_plain_json(self):
        txt = '{"a": 1, "b": 2}'
        assert plan_mod.extract_json_block(txt).startswith("{")
        assert json.loads(plan_mod.extract_json_block(txt)) == {"a": 1, "b": 2}

    def test_extract_from_fenced_json(self):
        txt = "여기 결과:\n```json\n{\"op\":\"add_track\"}\n```\n끝!"
        out = plan_mod.extract_json_block(txt)
        assert json.loads(out) == {"op": "add_track"}

    def test_extract_from_generic_fence(self):
        txt = "```\n{\"k\": 42}\n```"
        out = plan_mod.extract_json_block(txt)
        assert json.loads(out) == {"k": 42}

    def test_extract_from_mixed_prose(self):
        """코드펜스 없이 앞뒤 설명이 있는 경우 — 첫 ``{`` ~ 마지막 ``}``."""
        txt = 'Here is the JSON: {"name": "hi", "x": 1} — good luck!'
        out = plan_mod.extract_json_block(txt)
        assert json.loads(out) == {"name": "hi", "x": 1}

    def test_extract_nested_object(self):
        txt = '```json\n{"a": {"b": {"c": [1, 2, 3]}}}\n```'
        assert json.loads(plan_mod.extract_json_block(txt))["a"]["b"]["c"] == [1, 2, 3]

    def test_extract_non_string_returns_empty(self):
        assert plan_mod.extract_json_block(None) == ""  # type: ignore


# =========================================================================
# 에셋 리스팅
# =========================================================================


class TestAssetListing:
    def test_none_returns_empty_string(self):
        assert plan_mod.build_asset_listing(None) == ""

    def test_missing_folder_warns_in_string(self, tmp_path):
        out = plan_mod.build_asset_listing(str(tmp_path / "nope"))
        assert "없음" in out or "not" in out.lower() or "폴더" in out

    def test_classifies_by_extension(self, tmp_path):
        (tmp_path / "v.mp4").write_bytes(b"x")
        (tmp_path / "i.png").write_bytes(b"x")
        (tmp_path / "a.mp3").write_bytes(b"x")
        out = plan_mod.build_asset_listing(str(tmp_path))
        assert "Videos" in out and "v.mp4" in out
        assert "Images" in out and "i.png" in out
        assert "Audios" in out and "a.mp3" in out

    def test_limit_truncates(self, tmp_path):
        for i in range(50):
            (tmp_path / f"img{i:02d}.png").write_bytes(b"x")
        out = plan_mod.build_asset_listing(str(tmp_path), limit=5)
        assert "더)" in out  # 생략 표시


# =========================================================================
# Claude API 호출 에러 경로
# =========================================================================


class TestClaudeCallGuards:
    def test_missing_api_key(self, monkeypatch):
        """키 없으면 ClickException."""
        import click
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # anthropic 모듈은 있다고 가정 — 없으면 이전 단계에서 걸림
        # SDK 없는 환경 대비해 더미 모듈 주입
        dummy = types.ModuleType("anthropic")
        dummy.Anthropic = lambda **kw: None  # type: ignore
        monkeypatch.setitem(sys.modules, "anthropic", dummy)
        with pytest.raises(click.ClickException) as exc:
            plan_mod._call_claude("sys", "user", model="claude-sonnet-4-5")
        assert "ANTHROPIC_API_KEY" in str(exc.value.message)

    def test_missing_sdk(self, monkeypatch):
        """SDK import 실패 시 친절한 안내."""
        import click
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        # sys.modules 에서 anthropic 을 삭제하고, import 시 ImportError 나도록
        monkeypatch.setitem(sys.modules, "anthropic", None)
        with pytest.raises(click.ClickException) as exc:
            plan_mod._call_claude("sys", "user", model="claude-sonnet-4-5")
        assert "anthropic" in str(exc.value.message).lower()


# =========================================================================
# plan-refine — 피드백 루프 프롬프트 빌더
# =========================================================================


class TestRefinePrompt:
    def _example_recipe(self) -> dict:
        return {
            "name": "hotel-promo",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "operations": [
                {"op": "add_track", "args": {"type": "video", "name": "V1"}},
                {"op": "add_image", "args": {
                    "file": "a.jpg", "start": "0s", "duration": "5s",
                    "track": "V1"}},
                {"op": "add_image", "args": {
                    "file": "b.jpg", "start": "5s", "duration": "5s",
                    "track": "V1"}},
                {"op": "add_image", "args": {
                    "file": "c.jpg", "start": "10s", "duration": "5s",
                    "track": "V1"}},
            ],
        }

    def test_contains_existing_recipe(self):
        recipe = self._example_recipe()
        p = plan_mod.build_refine_system_prompt(recipe, "피드백")
        # 기존 레시피의 파일명들이 프롬프트에 포함되어야
        assert "a.jpg" in p
        assert "b.jpg" in p
        assert "hotel-promo" in p

    def test_contains_feedback(self):
        recipe = self._example_recipe()
        p = plan_mod.build_refine_system_prompt(
            recipe, "3번째 이미지는 2초만. BGM 볼륨 0.3.",
        )
        assert "2초만" in p
        assert "BGM 볼륨" in p

    def test_contains_known_ops(self):
        """refine 프롬프트도 op 목록을 포함 — 재사용 확인."""
        recipe = self._example_recipe()
        p = plan_mod.build_refine_system_prompt(recipe, "fb")
        for op in ("add_track", "add_video", "add_image",
                    "add_video_animation"):
            assert op in p

    def test_preserves_canvas_from_existing(self):
        recipe = self._example_recipe()
        recipe["width"] = 1440
        recipe["height"] = 2560
        recipe["fps"] = 60
        p = plan_mod.build_refine_system_prompt(recipe, "fb")
        assert "1440" in p
        assert "2560" in p
        # fps=60 선언 포함
        assert "fps=60" in p


# =========================================================================
# plan-refine 커맨드 — 입력 검증 & API 키 없을 때 에러
# =========================================================================


class TestRefineCommandGuards:
    def test_missing_api_key_errors(self, tmp_path, monkeypatch):
        """ANTHROPIC_API_KEY 없을 때 친절한 ClickException."""
        from click.testing import CliRunner
        # 입력 레시피 준비
        recipe_path = tmp_path / "in.json"
        recipe_path.write_text(json.dumps({
            "name": "x", "width": 1080, "height": 1920, "fps": 30,
            "operations": [
                {"op": "add_track", "args": {"type": "video", "name": "V1"}},
            ],
        }), encoding="utf-8")

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # 가짜 anthropic SDK 주입
        dummy = types.ModuleType("anthropic")
        dummy.Anthropic = lambda **kw: None  # type: ignore
        monkeypatch.setitem(sys.modules, "anthropic", dummy)

        runner = CliRunner()
        out_path = tmp_path / "out.json"
        result = runner.invoke(
            plan_mod.plan_refine_cmd,
            ["-i", str(recipe_path), "-o", str(out_path),
             "--feedback", "세번째 줄을 더 짧게"],
            obj={"json": True},
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in (result.output + str(result.exception or ""))

    def test_invalid_input_file_errors(self, tmp_path, monkeypatch):
        """입력 레시피가 operations 없는 JSON이면 에러."""
        from click.testing import CliRunner
        bad = tmp_path / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

        runner = CliRunner()
        out_path = tmp_path / "out.json"
        result = runner.invoke(
            plan_mod.plan_refine_cmd,
            ["-i", str(bad), "-o", str(out_path), "--feedback", "x"],
            obj={"json": True},
        )
        assert result.exit_code != 0
        assert "operations" in (result.output + str(result.exception or ""))


class TestRefineEndToEndFaked:
    """anthropic 호출을 가짜로 치환해 파이프라인 통과 검증."""

    def test_refine_pipeline_with_stub(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        # 기존 레시피
        recipe = {
            "name": "r1", "width": 1080, "height": 1920, "fps": 30,
            "operations": [
                {"op": "add_track", "args": {"type": "video", "name": "V1"}},
                {"op": "add_image", "args": {
                    "file": "a.jpg", "start": "0s", "duration": "5s",
                    "track": "V1"}},
            ],
        }
        recipe_path = tmp_path / "in.json"
        recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

        # LLM 응답: 기존 레시피 + 이미지 duration 변경 시뮬레이션
        refined = {
            "name": "r1", "width": 1080, "height": 1920, "fps": 30,
            "operations": [
                {"op": "add_track", "args": {"type": "video", "name": "V1"}},
                {"op": "add_image", "args": {
                    "file": "a.jpg", "start": "0s", "duration": "2s",
                    "track": "V1"}},
            ],
        }

        def fake_call(system, user, *, model, max_tokens=4096, extra_user=""):
            return "```json\n" + json.dumps(refined) + "\n```"

        monkeypatch.setattr(plan_mod, "_call_claude", fake_call)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

        runner = CliRunner()
        out_path = tmp_path / "out.json"
        result = runner.invoke(
            plan_mod.plan_refine_cmd,
            ["-i", str(recipe_path), "-o", str(out_path),
             "--feedback", "첫 이미지 2초로"],
            obj={"json": True},
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["operations"][1]["args"]["duration"] == "2s"


# =========================================================================
# 실제 API 호출 — 수동 확인용 (기본 스킵)
# =========================================================================


@pytest.mark.skipif(
    os.environ.get("ANTHROPIC_API_KEY") is None,
    reason="ANTHROPIC_API_KEY 없음 — 실제 API 호출 스킵",
)
class TestRealAPICall:
    def test_plan_roundtrip(self, tmp_path):
        """실제 API 로 레시피 생성 → 유효성 검증까지 통과하는지."""
        from click.testing import CliRunner
        runner = CliRunner()
        out_path = tmp_path / "recipe.json"
        result = runner.invoke(
            plan_mod.plan_cmd,
            ["30초 짧은 브랜드 홍보 숏폼. 하단 자막.", "-o", str(out_path)],
            obj={"json": True},
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert "operations" in data
