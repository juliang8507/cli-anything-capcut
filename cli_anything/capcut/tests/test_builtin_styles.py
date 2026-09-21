"""내장 스타일 프리셋의 실제 CLI 배선 회귀 테스트."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli_anything.capcut.core.style_registry import _BUILTIN


CLI = "cli-anything-capcut"
REPO_ROOT = Path(__file__).resolve().parents[3]
BUILTIN_CASES = [
    pytest.param(category, name, id=f"{category}-{name}")
    for category, styles in _BUILTIN.items()
    for name in styles
]

BUILTIN_REFERENCE_FIELDS = {
    "text": (("font", "FontType"),),
    "video": (
        ("filter", "FilterType"),
        ("animation_intro", "IntroType"),
        ("animation_outro", "OutroType"),
        ("effect", "VideoSceneEffectType"),
    ),
    "audio": (("effect", "AudioSceneEffectType"),),
}


def _run_json(args: list[str]) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["CAPCUT_NO_STAGING"] = "1"
    result = subprocess.run(
        [CLI, "--json", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert result.returncode == 0, (
        f"CLI failed ({result.returncode}): {' '.join(args)}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def _make_test_image(tmp_path: Path) -> Path:
    image = tmp_path / "segment.png"
    image.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "8900000010504c5445000000000000ffffffffffffffa56cdf3d0000000174524e"
        "53400e6cf2c80000000a4944415478da630000000200012b1d2c5b00000000"
        "49454e44ae426082"
    ))
    return image


def _make_test_audio(tmp_path: Path) -> Path:
    import wave

    audio = tmp_path / "segment.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\x00\x00" * 8_000)
    return audio


@pytest.mark.parametrize("category,style_name", BUILTIN_CASES)
def test_every_builtin_style_applies_through_cli_and_validates(
    tmp_path: Path,
    category: str,
    style_name: str,
) -> None:
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    session = tmp_path / f"{category}-{style_name}.session.json"

    _run_json([
        "project", "new", "--name", f"builtin-{category}-{style_name}",
        "--preset", "square", "--draft-folder", str(drafts),
        "--output", str(session),
    ])

    if category == "text":
        _run_json(["track", "add", "-p", str(session),
                   "--type", "text", "--name", "T1"])
        _run_json([
            "text", "add", "-p", str(session), "--text", "한글 자막 테스트",
            "--start", "0s", "--duration", "3s", "--track", "T1",
            "--style", style_name,
        ])
    elif category == "video":
        _run_json(["track", "add", "-p", str(session),
                   "--type", "video", "--name", "V1"])
        segment = _run_json([
            "image", "add", "-p", str(session), "--file", str(_make_test_image(tmp_path)),
            "--start", "0s", "--duration", "3s", "--track", "V1",
        ])
        _run_json([
            "style", "apply-video", "-p", str(session), "--track", "V1",
            "--segment-ref", segment["id"], "--style", style_name,
        ])
    elif category == "audio":
        _run_json(["track", "add", "-p", str(session),
                   "--type", "audio", "--name", "A1"])
        segment = _run_json([
            "audio", "add", "-p", str(session), "--file", str(_make_test_audio(tmp_path)),
            "--start", "0s", "--duration", "1s", "--track", "A1",
        ])
        _run_json([
            "style", "apply-audio", "-p", str(session), "--track", "A1",
            "--segment-ref", segment["id"], "--style", style_name,
        ])
    else:  # pragma: no cover - _BUILTIN 카테고리 추가 시 명시적 배선 요구
        pytest.fail(f"지원하지 않는 내장 스타일 카테고리: {category}")

    validation = _run_json(["validate", "-p", str(session)])
    assert validation["valid"] is True, validation


def test_alias_audit_checks_every_builtin_style_reference() -> None:
    expected: list[str] = []
    for category, styles in _BUILTIN.items():
        for style_name, spec in styles.items():
            for field, enum_class in BUILTIN_REFERENCE_FIELDS[category]:
                value = spec.get(field)
                if isinstance(value, dict):
                    value = value.get("name")
                if isinstance(value, str) and value:
                    expected.append(
                        f"style={category}/{style_name} field={field} "
                        f"value={value!r} class={enum_class}"
                    )

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "alias_audit.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for reference in expected:
        assert reference in result.stdout
    assert (
        f"BUILTIN_STYLES: total={len(expected)} alive={len(expected)} dead=0"
        in result.stdout
    )
