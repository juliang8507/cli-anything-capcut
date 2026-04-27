"""미디어 파일 경로 자동 스테이징 테스트."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cli_anything.capcut.core.media_staging import (
    needs_staging,
    stage_media,
    staging_list,
    staging_stats,
    unstage_all,
)


# =========================================================================
# needs_staging
# =========================================================================


class TestNeedsStaging:
    def test_ascii_only_no_staging(self):
        assert needs_staging("D:/media/video.mp4") is False
        assert needs_staging("/tmp/clip.mov") is False
        assert needs_staging("C:\\videos\\file-01_v2.mp4") is False

    def test_hangul_needs_staging(self):
        assert needs_staging("D:/한글폴더/영상.mp4") is True
        assert needs_staging("/tmp/한국어/영상.mp4") is True

    def test_space_needs_staging(self):
        assert needs_staging("D:/My Videos/clip.mp4") is True

    def test_other_non_ascii_needs_staging(self):
        assert needs_staging("D:/médias/clip.mp4") is True
        assert needs_staging("/home/ユーザ/movie.mov") is True

    def test_special_chars_needs_staging(self):
        # 괄호 등 특수문자도 CapCut에서 문제를 일으키는 사례가 있어 보수적으로 True
        assert needs_staging("D:/a (copy)/b.mp4") is True

    def test_empty(self):
        assert needs_staging("") is False


# =========================================================================
# stage_media
# =========================================================================


def _ascii_root() -> Path:
    """테스트용 ASCII 루트. 한글 사용자명 (C:\\Users\\<korean-name>\\...) 환경 대응.

    ``tmp_path`` 가 한글 경로 하위라면 ``needs_staging`` 가 항상 True 가 되어
    ASCII-only / staging 동작을 구분 검증할 수 없다. 그래서 OS 루트의 ASCII
    임시 디렉토리를 직접 만들어 사용한다.
    """
    for candidate in (Path("C:/capcut_test_tmp"), Path("/tmp/capcut_test_tmp")):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if not needs_staging(str(candidate)):
                return candidate
        except OSError:
            continue
    pytest.skip("ASCII-only 테스트 루트를 만들 수 없음 (한글 사용자명 환경)")


@pytest.fixture
def ascii_root(request):
    """ASCII 루트 + 테스트별 서브폴더 + 자동 정리."""
    root = _ascii_root()
    name = request.node.name.replace("[", "_").replace("]", "_")
    sub = root / name
    if sub.exists():
        import shutil
        shutil.rmtree(sub, ignore_errors=True)
    sub.mkdir(parents=True, exist_ok=True)
    yield sub
    import shutil
    shutil.rmtree(sub, ignore_errors=True)


@pytest.fixture
def isolated_cache(ascii_root, monkeypatch):
    """CAPCUT_STAGE_DIR 을 ASCII 루트로 가리키고 CAPCUT_NO_STAGING 제거."""
    cache = ascii_root / "stage"
    monkeypatch.setenv("CAPCUT_STAGE_DIR", str(cache))
    monkeypatch.delenv("CAPCUT_NO_STAGING", raising=False)
    return cache


def _make_hangul_file(root: Path, name: str = "한글_영상.mp4",
                      content: bytes = b"\x00\x01\x02 fake mp4") -> Path:
    d = root / "한글폴더"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(content)
    return p


class TestStageMedia:
    def test_ascii_path_noop(self, ascii_root, isolated_cache):
        src = ascii_root / "video.mp4"
        src.write_bytes(b"abc")
        assert not needs_staging(str(src)), "test precondition: ASCII root"
        staged, info = stage_media(str(src))
        assert info["method"] == "noop"
        assert staged == str(src)

    def test_hangul_path_gets_staged(self, ascii_root, isolated_cache):
        src = _make_hangul_file(ascii_root)
        staged, info = stage_media(str(src))
        assert info["method"] in {"hardlink", "copy"}
        assert staged != str(src)
        assert needs_staging(staged) is False, "스테이징 결과 경로는 ASCII여야 함"
        assert Path(staged).exists()
        assert Path(staged).read_bytes() == src.read_bytes()

    def test_staging_info_fields(self, ascii_root, isolated_cache):
        src = _make_hangul_file(ascii_root)
        _, info = stage_media(str(src))
        assert info["original"] == str(src)
        assert info["staged"]
        assert info["hash"]
        assert len(info["hash"]) == 12

    def test_restaging_uses_cache(self, ascii_root, isolated_cache):
        src = _make_hangul_file(ascii_root)
        staged1, info1 = stage_media(str(src))
        staged2, info2 = stage_media(str(src))
        assert staged1 == staged2
        assert info2["method"] == "cached"

    def test_env_disables_staging(self, ascii_root, isolated_cache, monkeypatch):
        monkeypatch.setenv("CAPCUT_NO_STAGING", "1")
        src = _make_hangul_file(ascii_root)
        staged, info = stage_media(str(src))
        assert info["method"] == "noop"
        assert staged == str(src)

    def test_missing_source(self, ascii_root, isolated_cache):
        src = ascii_root / "한글" / "없는파일.mp4"
        staged, info = stage_media(str(src))
        assert info["method"] == "missing"

    def test_space_path_staged(self, ascii_root, isolated_cache):
        d = ascii_root / "My Videos"
        d.mkdir()
        src = d / "clip.mp4"
        src.write_bytes(b"xyz")
        staged, info = stage_media(str(src))
        assert info["method"] in {"hardlink", "copy"}
        assert " " not in Path(staged).name  # 스테이징 파일명은 깨끗


# =========================================================================
# unstage_all / staging_stats / staging_list
# =========================================================================


class TestCacheManagement:
    def test_stats_on_empty_cache(self, ascii_root, isolated_cache):
        s = staging_stats()
        assert s["file_count"] == 0
        assert s["total_bytes"] == 0
        assert s["cache_dir"]

    def test_unstage_all_removes_files(self, ascii_root, isolated_cache):
        src = _make_hangul_file(ascii_root)
        stage_media(str(src))
        assert staging_stats()["file_count"] >= 1
        removed = unstage_all()
        assert removed >= 1
        assert staging_stats()["file_count"] == 0

    def test_list_returns_files(self, ascii_root, isolated_cache):
        src1 = _make_hangul_file(ascii_root, "영상1.mp4", b"aaa")
        src2 = _make_hangul_file(ascii_root, "영상2.mp4", b"bbbbb")
        stage_media(str(src1))
        stage_media(str(src2))
        files = staging_list()
        assert len(files) == 2
        for f in files:
            assert "name" in f and "size" in f and "path" in f
