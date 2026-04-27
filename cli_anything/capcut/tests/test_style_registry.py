"""스타일 프리셋 레지스트리 유닛 테스트 (v0.4.1 — 카테고리 스키마)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_anything.capcut.core import style_registry


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """각 테스트가 실제 ~/.capcut_cli/styles.json 을 건드리지 않게 격리."""
    fake = tmp_path / "styles.json"
    monkeypatch.setattr(style_registry, "STYLE_FILE", fake)
    yield fake


# =========================================================================
# 내장 프리셋
# =========================================================================


class TestBuiltins:
    def test_builtin_text_has_five_presets(self):
        b = style_registry.builtin_styles("text")
        assert set(b.keys()) >= {
            "lifestyle-brand", "youtube-subtitle", "news-title",
            "minimal-caption", "cinematic",
        }

    def test_builtin_video_has_three_presets(self):
        b = style_registry.builtin_styles("video")
        assert set(b.keys()) >= {"cinematic-warm", "social-punchy", "corporate-clean"}
        # 카테고리 특화 필드가 실제로 들어있어야
        warm = b["cinematic-warm"]
        assert isinstance(warm.get("filter"), dict)
        assert warm["filter"].get("name") == "cinematic"
        assert isinstance(warm.get("animation_intro"), dict)
        assert isinstance(warm.get("animation_outro"), dict)

    def test_builtin_audio_has_three_presets(self):
        b = style_registry.builtin_styles("audio")
        assert set(b.keys()) >= {"podcast-voice", "bgm-background", "sfx-short"}
        voice = b["podcast-voice"]
        assert voice["volume"] == 0.9
        assert voice.get("effect", {}).get("name") == "noise-reduction"

    def test_builtin_all_returns_categorized(self):
        """카테고리 없이 호출하면 {category: {name: spec}} 형태."""
        b = style_registry.builtin_styles()
        assert "text" in b and "video" in b and "audio" in b
        assert "lifestyle-brand" in b["text"]
        assert "cinematic-warm" in b["video"]

    def test_builtin_is_deep_copy(self):
        """반환값 mutate 가 원본을 오염시키지 않아야."""
        b = style_registry.builtin_styles("text")
        b["lifestyle-brand"]["size"] = 999.0
        b2 = style_registry.builtin_styles("text")
        assert b2["lifestyle-brand"]["size"] != 999.0

    def test_get_builtin_style_text(self):
        spec = style_registry.get_style("lifestyle-brand")  # 기본 category=text
        assert spec["font"]
        assert spec["size"] > 0

    def test_get_builtin_style_video(self):
        spec = style_registry.get_style("cinematic-warm", category="video")
        assert spec["filter"]["name"] == "cinematic"

    def test_get_builtin_style_audio(self):
        spec = style_registry.get_style("podcast-voice", category="audio")
        assert spec["volume"] == 0.9


# =========================================================================
# 플랫 스키마 마이그레이션
# =========================================================================


class TestFlatSchemaMigration:
    def test_flat_schema_loads_under_text(self, _isolated_store):
        """v0.4.0 플랫 스키마 파일을 읽으면 text 카테고리로 이동."""
        _isolated_store.parent.mkdir(parents=True, exist_ok=True)
        legacy = {
            "legacy-sub": {"font": "arial", "size": 5.0},
            "legacy-cap": {"font": "serif", "size": 4.0},
        }
        _isolated_store.write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8",
        )

        # 카테고리별 조회 — text 에 들어있어야
        text_user = style_registry.load_styles("text")
        assert "legacy-sub" in text_user
        assert "legacy-cap" in text_user

        # get_style 도 텍스트에서 잘 찾음
        spec = style_registry.get_style("legacy-sub")
        assert spec["font"] == "arial"

    def test_flat_schema_migrated_on_save(self, _isolated_store):
        """플랫 스키마 파일에 save 하면 새 스키마로 재기록되어야."""
        _isolated_store.parent.mkdir(parents=True, exist_ok=True)
        _isolated_store.write_text(
            json.dumps({"legacy": {"font": "arial"}}), encoding="utf-8",
        )
        style_registry.save_style("new", {"font": "serif"})
        # 디스크 확인
        written = json.loads(_isolated_store.read_text(encoding="utf-8"))
        assert "text" in written
        assert "legacy" in written["text"]
        assert "new" in written["text"]

    def test_new_schema_roundtrip(self, _isolated_store):
        _isolated_store.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": {"t1": {"font": "arial"}},
            "video": {"v1": {"filter": {"name": "warm"}}},
            "audio": {"a1": {"volume": 0.5}},
        }
        _isolated_store.write_text(json.dumps(payload), encoding="utf-8")
        assert "t1" in style_registry.load_styles("text")
        assert "v1" in style_registry.load_styles("video")
        assert "a1" in style_registry.load_styles("audio")


# =========================================================================
# 저장/조회/삭제 라운드트립 (카테고리별)
# =========================================================================


class TestCRUDRoundtrip:
    def test_save_text_then_get(self):
        style_registry.save_style(
            "my-sub",
            {"font": "arial", "size": 5.5, "color": [1, 1, 1]},
        )
        got = style_registry.get_style("my-sub")
        assert got["font"] == "arial"
        assert got["size"] == 5.5

    def test_save_video_then_get(self):
        style_registry.save_style(
            "my-cine",
            {"filter": {"name": "cinematic", "intensity": 40}},
            category="video",
        )
        got = style_registry.get_style("my-cine", category="video")
        assert got["filter"]["name"] == "cinematic"

    def test_save_audio_then_get(self):
        style_registry.save_style(
            "my-voice",
            {"volume": 0.8, "fade_in": "0.2s"},
            category="audio",
        )
        got = style_registry.get_style("my-voice", category="audio")
        assert got["volume"] == 0.8

    def test_same_name_different_categories_ok(self):
        """같은 이름이라도 카테고리가 다르면 공존."""
        style_registry.save_style("x", {"font": "arial"}, category="text")
        style_registry.save_style("x", {"volume": 0.5}, category="audio")
        assert style_registry.get_style("x", category="text")["font"] == "arial"
        assert style_registry.get_style("x", category="audio")["volume"] == 0.5

    def test_save_then_list_includes(self):
        style_registry.save_style("s1", {"font": "arial", "size": 5.0})
        names = [(r["category"], r["name"]) for r in style_registry.list_styles()]
        assert ("text", "s1") in names
        assert ("text", "lifestyle-brand") in names
        assert ("video", "cinematic-warm") in names
        assert ("audio", "podcast-voice") in names

    def test_list_category_filter(self):
        style_registry.save_style(
            "v-test", {"filter": {"name": "bw"}}, category="video",
        )
        rows = style_registry.list_styles(category="video")
        # text/audio 는 나오면 안 됨
        assert all(r["category"] == "video" for r in rows)
        names = [r["name"] for r in rows]
        assert "v-test" in names
        assert "cinematic-warm" in names

    def test_list_marks_builtin_flag(self):
        rows = style_registry.list_styles("text")
        by_name = {r["name"]: r for r in rows}
        assert by_name["lifestyle-brand"]["builtin"] is True

    def test_builtin_collision_rejected_per_category(self):
        with pytest.raises(ValueError):
            style_registry.save_style("lifestyle-brand", {"font": "x"})
        # 다른 카테고리에서는 OK (video 에는 lifestyle-brand 가 없음)
        style_registry.save_style("lifestyle-brand", {"filter": {"name": "warm"}},
                                  category="video")

    def test_delete_text(self):
        style_registry.save_style("tmp", {"font": "arial"})
        assert style_registry.delete_style("tmp") is True
        with pytest.raises(KeyError):
            style_registry.get_style("tmp")

    def test_delete_video(self):
        style_registry.save_style("tmp-v", {"filter": {"name": "x"}},
                                  category="video")
        assert style_registry.delete_style("tmp-v", category="video") is True

    def test_delete_nonexistent_returns_false(self):
        assert style_registry.delete_style("not-there") is False

    def test_delete_builtin_returns_false(self):
        assert style_registry.delete_style("lifestyle-brand") is False
        assert style_registry.delete_style("cinematic-warm", category="video") is False
        # 여전히 get 가능
        style_registry.get_style("lifestyle-brand")
        style_registry.get_style("cinematic-warm", category="video")

    def test_duplicate_save_raises_without_overwrite(self):
        style_registry.save_style("dup", {"font": "arial"})
        with pytest.raises(ValueError):
            style_registry.save_style("dup", {"font": "serif"})

    def test_duplicate_save_ok_with_overwrite(self):
        style_registry.save_style("dup", {"font": "arial"})
        style_registry.save_style("dup", {"font": "serif"}, overwrite=True)
        assert style_registry.get_style("dup")["font"] == "serif"

    def test_invalid_name_rejected(self):
        with pytest.raises(ValueError):
            style_registry.save_style("has space", {"font": "arial"})

    def test_invalid_category_rejected(self):
        with pytest.raises(ValueError):
            style_registry.save_style("x", {"font": "arial"}, category="bogus")


# =========================================================================
# 파일 I/O 견고성
# =========================================================================


class TestFileIO:
    def test_load_empty_when_no_file(self, _isolated_store):
        assert not _isolated_store.exists()
        out = style_registry.load_styles()
        # 새 스키마 — 모든 카테고리 빈 dict
        assert out == {"text": {}, "video": {}, "audio": {}}

    def test_load_handles_corrupt_json(self, _isolated_store):
        _isolated_store.parent.mkdir(parents=True, exist_ok=True)
        _isolated_store.write_text("not-json!!{", encoding="utf-8")
        assert style_registry.load_styles() == {"text": {}, "video": {}, "audio": {}}

    def test_load_handles_non_object_json(self, _isolated_store):
        _isolated_store.parent.mkdir(parents=True, exist_ok=True)
        _isolated_store.write_text("[1,2,3]", encoding="utf-8")
        assert style_registry.load_styles() == {"text": {}, "video": {}, "audio": {}}

    def test_saved_file_is_category_schema(self, _isolated_store):
        style_registry.save_style("x", {"font": "arial", "size": 5.0})
        raw = _isolated_store.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert "text" in data and "x" in data["text"]


# =========================================================================
# merge_style_with_overrides (카테고리 인지)
# =========================================================================


class TestMergeOverrides:
    def test_no_style_returns_overrides(self):
        out = style_registry.merge_style_with_overrides(
            None, {"font": "arial", "size": 5.0}
        )
        assert out == {"font": "arial", "size": 5.0}

    def test_text_merge_default_category(self):
        style_registry.save_style("base", {"font": "arial", "size": 5.0})
        out = style_registry.merge_style_with_overrides(
            "base", {"font": "serif"}
        )
        assert out["font"] == "serif"
        assert out["size"] == 5.0

    def test_video_merge(self):
        style_registry.save_style(
            "vbase", {"filter": {"name": "warm", "intensity": 30}},
            category="video",
        )
        out = style_registry.merge_style_with_overrides(
            "vbase", {"filter": {"name": "bw", "intensity": 80}},
            category="video",
        )
        assert out["filter"]["name"] == "bw"
        assert out["filter"]["intensity"] == 80

    def test_audio_merge(self):
        style_registry.save_style(
            "abase", {"volume": 0.8, "fade_in": "0.2s"}, category="audio",
        )
        out = style_registry.merge_style_with_overrides(
            "abase", {"volume": 0.3}, category="audio",
        )
        assert out["volume"] == 0.3
        assert out["fade_in"] == "0.2s"

    def test_none_values_do_not_override(self):
        style_registry.save_style("base", {"font": "arial", "size": 5.0})
        out = style_registry.merge_style_with_overrides(
            "base", {"font": None, "size": None}
        )
        assert out["font"] == "arial"
        assert out["size"] == 5.0

    def test_unknown_style_raises(self):
        with pytest.raises(KeyError):
            style_registry.merge_style_with_overrides("no-such", {"font": "x"})

    def test_builtin_is_usable_as_base_text(self):
        out = style_registry.merge_style_with_overrides(
            "youtube-subtitle", {"size": 9.9}
        )
        assert out["size"] == 9.9
        assert out.get("font")

    def test_builtin_is_usable_as_base_video(self):
        out = style_registry.merge_style_with_overrides(
            "cinematic-warm", {"filter": {"name": "vivid", "intensity": 70}},
            category="video",
        )
        assert out["filter"]["name"] == "vivid"
        # 원본 animation 은 남아 있어야
        assert out.get("animation_intro")

    def test_internal_markers_stripped(self):
        out = style_registry.merge_style_with_overrides(
            "lifestyle-brand", {"size": 7.0}
        )
        assert "_description" not in out
        assert "_builtin" not in out


# =========================================================================
# apply_video_style / apply_audio_style — 세션에 op 추가
# =========================================================================


class _FakeSession:
    """테스트용 세션 더블 — Session 인터페이스의 필요 최소치만."""

    def __init__(self, ops=None):
        self.data = {"operations": list(ops or [])}
        self._counter = len(self.data["operations"])

    def _auto_save(self):
        pass

    def batch(self):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield
        return _cm()

    def append_operation(self, op: str, args: dict, *, _status: str = "added") -> dict:
        self._counter += 1
        op_id = f"op_{self._counter}"
        clean_args = {k: v for k, v in (args or {}).items() if v is not None}
        record = {"id": op_id, "op": op, "args": clean_args}
        self.data["operations"].append(record)
        return {"status": _status, "id": op_id, "type": op, **clean_args}


class TestApplyVideoStyle:
    def test_applies_filter_and_animations_and_color(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_video",
             "args": {"track": "V1", "start": "0s", "duration": "5s", "file": "a.mp4"}},
        ])
        appended = style_registry.apply_video_style(
            sess, track="V1", segment_ref="op_0", style_name="cinematic-warm",
        )
        op_types = [o["op"] for o in sess.data["operations"][1:]]
        # 최소한: add_filter, add_video_animation (intro), add_video_animation (outro), color_adjust
        assert "add_filter" in op_types
        assert op_types.count("add_video_animation") >= 2
        assert "color_adjust" in op_types
        assert len(appended) >= 3  # filter + 2 anims + color

    def test_filter_uses_segment_times(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_video",
             "args": {"track": "V1", "start": "1s", "duration": "4s", "file": "x.mp4"}},
        ])
        style_registry.apply_video_style(
            sess, track="V1", segment_ref="op_0", style_name="cinematic-warm",
        )
        filt = next(o for o in sess.data["operations"] if o["op"] == "add_filter")
        assert filt["args"].get("start") == "1s"
        assert filt["args"].get("duration") == "4s"

    def test_social_punchy_has_only_intro(self):
        """social-punchy 는 outro 없음 — intro 1개만."""
        sess = _FakeSession([
            {"id": "op_0", "op": "add_video",
             "args": {"track": "V1", "start": "0s", "duration": "5s", "file": "x.mp4"}},
        ])
        style_registry.apply_video_style(
            sess, track="V1", segment_ref="op_0", style_name="social-punchy",
        )
        anims = [o for o in sess.data["operations"] if o["op"] == "add_video_animation"]
        assert len(anims) == 1
        assert anims[0]["args"]["role"] == "intro"

    def test_corporate_clean_only_color(self):
        """corporate-clean 은 color 만."""
        sess = _FakeSession([
            {"id": "op_0", "op": "add_video",
             "args": {"track": "V1", "start": "0s", "duration": "5s"}},
        ])
        style_registry.apply_video_style(
            sess, track="V1", segment_ref="op_0", style_name="corporate-clean",
        )
        op_types = [o["op"] for o in sess.data["operations"][1:]]
        assert op_types == ["color_adjust"]

    def test_unknown_style_raises(self):
        sess = _FakeSession()
        with pytest.raises(KeyError):
            style_registry.apply_video_style(
                sess, track="V1", segment_ref="op_0", style_name="nope",
            )

    def test_user_override_merges(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_video",
             "args": {"track": "V1", "start": "0s", "duration": "5s"}},
        ])
        style_registry.apply_video_style(
            sess, track="V1", segment_ref="op_0", style_name="cinematic-warm",
            user_overrides={"filter": {"name": "bw", "intensity": 100}},
        )
        filt = next(o for o in sess.data["operations"] if o["op"] == "add_filter")
        assert filt["args"]["name"] == "bw"


class TestApplyAudioStyle:
    def test_applies_volume_fade_effect(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_audio",
             "args": {"track": "A1", "start": "0s", "duration": "10s",
                      "file": "voice.mp3"}},
        ])
        appended = style_registry.apply_audio_style(
            sess, track="A1", segment_ref="op_0", style_name="podcast-voice",
        )
        # volume 은 원본 op args 에 패치됨
        orig = sess.data["operations"][0]
        assert orig["args"]["volume"] == 0.9

        op_types = [o["op"] for o in sess.data["operations"][1:]]
        assert "add_audio_fade" in op_types
        assert "add_audio_effect" in op_types
        # appended 는 fade + effect (volume 은 edit 이라 append 에 없음)
        assert len(appended) == 2

    def test_bgm_background_no_effect(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_audio",
             "args": {"track": "A1", "start": "0s", "duration": "30s"}},
        ])
        style_registry.apply_audio_style(
            sess, track="A1", segment_ref="op_0", style_name="bgm-background",
        )
        op_types = [o["op"] for o in sess.data["operations"][1:]]
        # effect 는 bgm-background 에 없음 → add_audio_effect 없어야
        assert "add_audio_effect" not in op_types
        assert "add_audio_fade" in op_types
        assert sess.data["operations"][0]["args"]["volume"] == 0.3

    def test_missing_segment_ref_raises_and_rollback(self):
        sess = _FakeSession()  # op_0 없음
        with pytest.raises(KeyError):
            style_registry.apply_audio_style(
                sess, track="A1", segment_ref="op_0",
                style_name="podcast-voice",
            )
        # 롤백 — 새로 추가된 op 없어야 (원래도 없었지만 fade 가 먼저 append
        # 되지 않도록 volume 먼저 시도해 KeyError 나는 순서이어야)
        assert sess.data["operations"] == []

    def test_user_override(self):
        sess = _FakeSession([
            {"id": "op_0", "op": "add_audio",
             "args": {"track": "A1", "start": "0s", "duration": "10s"}},
        ])
        style_registry.apply_audio_style(
            sess, track="A1", segment_ref="op_0", style_name="podcast-voice",
            user_overrides={"volume": 0.5},
        )
        assert sess.data["operations"][0]["args"]["volume"] == 0.5
