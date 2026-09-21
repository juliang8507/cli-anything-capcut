"""``text add --font`` 별칭 해석과 저장 배선 회귀 테스트."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pycapcut as cc
import pytest
from click.testing import CliRunner

from cli_anything.capcut.capcut_cli import cli
from cli_anything.capcut.core import alias_map
from cli_anything.capcut.core.postprocess import apply_text_style_patch


def _invoke_json(runner: CliRunner, args: list[str]) -> dict[str, Any]:
    result = runner.invoke(
        cli,
        ["--json", *args],
        env={"CAPCUT_NO_STAGING": "1"},
    )
    assert result.exit_code == 0, (
        f"CLI failed for {args!r} (exit={result.exit_code}):\n{result.output}"
    )
    return json.loads(result.output)


def _new_text_project(tmp_path: Path, name: str) -> tuple[CliRunner, Path, Path]:
    runner = CliRunner()
    drafts = (tmp_path / "drafts").resolve()
    session_path = (tmp_path / f"{name}.session.json").resolve()
    _invoke_json(
        runner,
        [
            "project",
            "new",
            "--name",
            name,
            "--preset",
            "9x16",
            "--draft-folder",
            str(drafts),
            "--output",
            str(session_path),
        ],
    )
    _invoke_json(
        runner,
        [
            "track",
            "add",
            "-p",
            str(session_path),
            "--type",
            "text",
            "--name",
            "T1",
        ],
    )
    return runner, session_path, drafts


def _add_text_with_font(
    runner: CliRunner, session_path: Path, font_alias: str
) -> None:
    _invoke_json(
        runner,
        [
            "text",
            "add",
            "-p",
            str(session_path),
            "--text",
            "한글 자막",
            "--start",
            "0s",
            "--duration",
            "1s",
            "--track",
            "T1",
            "--font",
            font_alias,
        ],
    )


def _save_and_load(
    runner: CliRunner, session_path: Path, drafts: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    saved = _invoke_json(runner, ["save", "-p", str(session_path)])
    draft_content_path = Path(saved["draft_content_json"]).resolve()
    assert drafts == draft_content_path or drafts in draft_content_path.parents
    return saved, json.loads(draft_content_path.read_text(encoding="utf-8"))


def _installed_local_font() -> tuple[str, Path]:
    windows_fonts = Path("C:/Windows/Fonts")
    candidates = [
        ("malgun_gothic", windows_fonts / "malgun.ttf"),
        ("malgun_gothic_bold", windows_fonts / "malgunbd.ttf"),
        ("malgun_gothic_semilight", windows_fonts / "malgunsl.ttf"),
        ("noto_sans_kr", windows_fonts / "NotoSansKR-VF.ttf"),
    ]
    for alias, font_path in candidates:
        if font_path.is_file():
            return alias, font_path.resolve()
    pytest.skip("테스트 환경에 알려진 로컬 한글 TTF가 없음")


def test_user_font_location_is_included_without_existing_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "missing-local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    locations = alias_map._font_scan_locations()

    assert local_app_data / "Microsoft" / "Windows" / "Fonts" in locations


def test_user_font_precedes_same_named_windows_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source_font = _installed_local_font()
    local_app_data = tmp_path / "z-local-app-data"
    windows_root = tmp_path / "a-windows"
    user_font = (
        local_app_data / "Microsoft" / "Windows" / "Fonts" / "NanumGothic.ttf"
    )
    windows_font = windows_root / "Fonts" / "NanumGothic.ttf"
    user_font.parent.mkdir(parents=True)
    windows_font.parent.mkdir(parents=True)
    shutil.copy2(source_font, user_font)
    shutil.copy2(source_font, windows_font)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("WINDIR", str(windows_root))
    alias_map._discover_available_fonts_at.cache_clear()

    runner, session_path, drafts = _new_text_project(tmp_path, "user-font")
    _add_text_with_font(runner, session_path, "nanum_gothic")
    _, draft = _save_and_load(runner, session_path, drafts)

    material = draft["materials"]["texts"][0]
    style = json.loads(material["content"])["styles"][0]
    font = style["font"]
    assert font == {"id": "", "path": user_font.resolve().as_posix()}
    assert "\\" not in font["path"]
    assert style["range"] == [0, 5]
    assert material["font_path"] == user_font.resolve().as_posix()
    assert material["font_resource_id"] == ""

    local_aliases = alias_map.discover_local_font_aliases(
        (user_font.parent, windows_font.parent)
    )
    assert local_aliases["nanum_gothic"] == user_font.resolve().as_posix()


def test_downloaded_capcut_font_writes_content_path_and_resource_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source_font = _installed_local_font()
    local_app_data = tmp_path / "local-app-data"
    resource_id = cc.FontType.ALEGREYA.value.resource_id
    cached_font = (
        local_app_data
        / "CapCut"
        / "User Data"
        / "Cache"
        / "effect"
        / resource_id
        / "font-hash"
        / "Alegreya.ttf"
    )
    cached_font.parent.mkdir(parents=True)
    shutil.copy2(source_font, cached_font)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    runner, session_path, drafts = _new_text_project(tmp_path, "downloaded-font")

    _add_text_with_font(runner, session_path, "alegreya")
    saved, draft = _save_and_load(runner, session_path, drafts)

    material = draft["materials"]["texts"][0]
    font = json.loads(material["content"])["styles"][0]["font"]

    assert font == {"id": resource_id, "path": cached_font.resolve().as_posix()}
    assert material["font_resource_id"] == resource_id
    assert material["font_path"] == cached_font.resolve().as_posix()
    assert saved["postprocess_applied"] == 1


def test_capcut_system_font_stem_resolves_with_empty_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source_font = _installed_local_font()
    local_app_data = tmp_path / "local-app-data"
    system_font = (
        local_app_data
        / "CapCut"
        / "User Data"
        / "Resources"
        / "Font"
        / "SystemFont"
        / "ko.ttf"
    )
    system_font.parent.mkdir(parents=True)
    shutil.copy2(source_font, system_font)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    runner, session_path, drafts = _new_text_project(tmp_path, "system-font")
    _add_text_with_font(runner, session_path, "ko")
    _, draft = _save_and_load(runner, session_path, drafts)

    font = json.loads(draft["materials"]["texts"][0]["content"])["styles"][0]["font"]
    assert font == {"id": "", "path": system_font.resolve().as_posix()}


def test_bundled_generic_alias_can_match_scanned_system_font_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source_font = _installed_local_font()
    local_app_data = tmp_path / "local-app-data"
    system_font = (
        local_app_data
        / "CapCut"
        / "User Data"
        / "Resources"
        / "Font"
        / "SystemFont"
        / "Source_Serif_4_18pt-BoldItalic.ttf"
    )
    system_font.parent.mkdir(parents=True)
    shutil.copy2(source_font, system_font)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    runner, session_path, drafts = _new_text_project(tmp_path, "generic-serif")
    _add_text_with_font(runner, session_path, "serif")
    _, draft = _save_and_load(runner, session_path, drafts)

    font = json.loads(draft["materials"]["texts"][0]["content"])["styles"][0]["font"]
    assert font == {"id": "", "path": system_font.resolve().as_posix()}


def test_local_font_alias_writes_existing_absolute_ttf_path(tmp_path: Path) -> None:
    font_alias, expected_path = _installed_local_font()
    runner, session_path, drafts = _new_text_project(tmp_path, "local-font")

    _add_text_with_font(runner, session_path, font_alias)
    saved, draft = _save_and_load(runner, session_path, drafts)

    material = draft["materials"]["texts"][0]
    style = json.loads(material["content"])["styles"][0]
    font = style["font"]
    actual_path = Path(font["path"])

    assert font["id"] == ""
    assert "id" in font
    assert font["path"] == expected_path.as_posix()
    assert actual_path == expected_path
    assert actual_path.is_absolute()
    assert actual_path.is_file()
    assert actual_path.suffix.lower() == ".ttf"
    assert "\\" not in font["path"]
    assert style["range"] == [0, 5]
    assert style["size"] == 8.0
    assert style["fill"]["content"]["render_type"] == "solid"
    assert material["font_path"] == expected_path.as_posix()
    assert material["font_resource_id"] == ""
    assert saved["postprocess_applied"] == 1


def test_unknown_font_stops_before_text_or_draft_is_created(tmp_path: Path) -> None:
    runner, session_path, drafts = _new_text_project(tmp_path, "unknown-font")

    result = runner.invoke(
        cli,
        [
            "--json",
            "text",
            "add",
            "-p",
            str(session_path),
            "--text",
            "한글 자막",
            "--track",
            "T1",
            "--font",
            "totally_bogus_font_xyz",
        ],
        env={"CAPCUT_NO_STAGING": "1"},
    )

    assert result.exit_code != 0
    assert "totally_bogus_font_xyz" in result.output
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert [op["op"] for op in session["operations"]] == ["add_track"]
    assert not list(drafts.rglob("draft_content.json"))


def test_undownloaded_bundled_font_stops_with_download_instruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "empty-local-app-data"
    windows_root = tmp_path / "empty-windows"
    local_app_data.mkdir()
    (windows_root / "Fonts").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("WINDIR", str(windows_root))
    runner, session_path, drafts = _new_text_project(tmp_path, "undownloaded-font")

    result = runner.invoke(
        cli,
        [
            "--json",
            "text",
            "add",
            "-p",
            str(session_path),
            "--text",
            "한글 자막",
            "--track",
            "T1",
            "--font",
            "alegreya",
        ],
        env={"CAPCUT_NO_STAGING": "1"},
    )

    assert result.exit_code != 0
    assert "CapCut에 아직 다운로드되지 않은 폰트" in result.output
    assert "CapCut에서 한 번 사용" in result.output
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert [op["op"] for op in session["operations"]] == ["add_track"]
    assert not list(drafts.rglob("draft_content.json"))


def test_postprocess_count_excludes_patch_that_changed_nothing(tmp_path: Path) -> None:
    runner, session_path, drafts = _new_text_project(tmp_path, "noop-font-patch")
    _invoke_json(
        runner,
        [
            "text",
            "add",
            "-p",
            str(session_path),
            "--text",
            "기본 폰트",
            "--start",
            "0s",
            "--duration",
            "1s",
            "--track",
            "T1",
        ],
    )
    _invoke_json(
        runner,
        [
            "text",
            "style-patch",
            "-p",
            str(session_path),
            "--track",
            "T1",
            "--segment-ref",
            "missing-segment",
            "--font-resource-id",
            cc.FontType.ALEGREYA.value.resource_id,
        ],
    )

    saved, draft = _save_and_load(runner, session_path, drafts)

    assert "font_resource_id" not in draft["materials"]["texts"][0]
    assert saved["postprocess_applied"] == 0
    assert saved["postprocess_warnings"]


def test_empty_content_styles_skips_font_injection_with_warning(tmp_path: Path) -> None:
    font_path = (tmp_path / "font.ttf").resolve()
    font_path.touch()
    content = {"styles": [], "text": "한글 자막"}
    draft = {
        "tracks": [
            {
                "type": "text",
                "name": "T1",
                "segments": [{"material_id": "material-1"}],
            }
        ],
        "materials": {
            "texts": [
                {
                    "id": "material-1",
                    "content": json.dumps(content, ensure_ascii=False),
                }
            ]
        },
    }
    session = {
        "operations": [
            {
                "id": "text-op",
                "op": "add_text",
                "args": {"track": "T1"},
            }
        ]
    }

    warnings = apply_text_style_patch(
        draft,
        {
            "track": "T1",
            "segment_ref": "text-op",
            "font_path": str(font_path),
        },
        session,
    )

    material = draft["materials"]["texts"][0]
    assert json.loads(material["content"]) == content
    assert material["font_path"] == font_path.as_posix()
    assert material["font_resource_id"] == ""
    assert any("content.styles가 비어" in warning for warning in warnings)
