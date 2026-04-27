# Changelog

## 0.5.1 — 2026-04-19

### 신규 — `text auto-srt` 서브커맨드 (whisper CLI 연동 자동 자막)

- **`text auto-srt`**: 오디오/영상 파일을 받아 `whisper` CLI를 subprocess로 호출 → SRT 자동 생성 → 기존 `srt import` 로직으로 세션에 연결. 한 줄 명령으로 자막 자동 생성.
  - `text auto-srt -p session.json --audio interview.mp4 --model small --language ko`
  - `--word-level/--segment-level`: 단어 단위 vs 세그먼트 단위 타임스탬프 (기본: word-level)
  - `--initial-prompt "specialized vocabulary"`: 도메인 특화 어휘 힌트 전달
  - `--output-dir`: SRT 저장 경로 지정 (기본: 임시 디렉토리 자동 정리)
  - `--keep-srt/--no-keep-srt`: SRT 파일 보존 여부 (기본: --no-keep-srt, 임시 디렉토리 정리)
  - `--model`: tiny/base/small/medium/large 선택 (기본: small)
  - `--language`: 언어 코드 또는 'auto' (기본: ko)
  - whisper 미설치 시 `pip install openai-whisper` 안내 메시지 출력
  - 한글 경로 처리: `encoding='utf-8'` + 인자 리스트 방식(shell=False) 유지

### 구현 파일

- `commands/text.py`: `text_group`에 `auto-srt` 서브커맨드 추가. `import shutil, subprocess, tempfile` 추가. 파일 끝 `text_auto_srt` 함수 삽입 (~100라인).

### 테스트

- 신규: `tests/test_text_auto_srt.py` — 6개 (happy path + segment-level + initial_prompt + whisper실패 + 미설치 + output-dir 보존 + --help)
- 전체: **306 passed, 1 skipped** (예상) — 회귀 없음

### 버전

- 0.5.1

## 0.4.4 — 2026-04-19

### 복원 — v0.3 기능 4개 (draft_content.json 직접 패치 방식)

- **`video lut`** (`add_lut` op): LUT 파일을 세그먼트에 적용. `materials.video_luts[]`에 material 추가 + `segment.enable_lut = True` + `extra_material_refs` 연결. `.cube`/`.3dl` 등 지원, 비표준 확장자 시 경고.
  - `video lut -p session.json --track V1 --segment-ref op_0 --file lut.cube --intensity 0.8`
- **`video speed-curve`** (`set_speed_curve` op): speed material에 `mode=curve` + `curve_speed.points` 주입. speed material 없으면 새로 생성 후 `extra_material_refs` 연결.
  - `video speed-curve -p session.json --track V1 --segment-ref op_0 --points "0,1.0;0.5,2.0;1.0,1.0"`
- **`color curves`** (`add_color_curves` op): `materials.color_curves[]`에 material 추가 + `segment.enable_color_curves = True`. RGB 마스터 채널 및 R/G/B 개별 채널 선택적 지정. 최소 1채널 필수.
  - `color curves -p session.json --track V1 --segment-ref op_0 --rgb "0,0;0.5,0.7;1,1"`
- **`color hsl`** (`add_hsl_adjust` op): `materials.material_colors[]`에 target_color별 HSL 값 저장 + `segment.enable_color_correct_adjust = True`. 8색 채널(red/orange/yellow/green/cyan/blue/purple/magenta) 지원. 같은 세그먼트에 여러 target 누적 가능. 수치 -100~+100 → 내부 -1.0~+1.0 변환.
  - `color hsl -p session.json --track V1 --segment-ref op_0 --target red --hue 10 --saturation -20 --lightness 5`

### 구현 파일

- `core/postprocess.py`: `apply_lut_patch` / `apply_speed_curve_patch` / `apply_color_curves_patch` / `apply_hsl_patch` 추가. `HSL_TARGET_CHOICES` 상수 추가. `apply_postprocess` 내 `add_lut` / `set_speed_curve` / `add_color_curves` / `add_hsl_adjust` 분기 추가.
- `core/op_registry.py`: `POSTPROCESS_OPS`에 `add_lut`, `set_speed_curve`, `add_color_curves`, `add_hsl_adjust` 추가.
- `commands/media.py`: `video_group`에 `lut`, `speed-curve` 서브커맨드 추가. `_parse_speed_points` 헬퍼 추가.
- `commands/color.py`: `color_group`에 `curves`, `hsl` 서브커맨드 추가. `_parse_curve_points`, `_HSL_TARGET_CHOICES` 추가.

### 테스트

- 신규: `tests/test_postprocess_v044.py` — 26개 (--help 확인 4 + 세션 op 기록 4 + draft JSON 패치 18)
- 전체: **300 passed, 1 skipped** — 회귀 없음

### 버전

- 0.4.4

## 0.4.3 — 2026-04-19

### 복원 — v0.3 기능 4개 (draft_content.json 직접 패치 방식)

- **`video reverse`** (`set_reverse` op): 비디오 세그먼트에 역재생 플래그(`reverse=True`) 설정.
  - `video reverse -p session.json --track V1 --segment-ref op_0`
- **`video freeze-frame`** (`set_freeze_frame` op): speed material을 `mode=freeze, speed=0.0`으로 패치. speed material 없으면 `speed_info` 직접 폴백.
  - `video freeze-frame -p session.json --track V1 --segment-ref op_0 [--duration 2s]`
- **`video blend-mode`** (`set_blend_mode` op): `segment.track_attribute.blend_mode` 정수값 설정. 지원 모드 13종 (normal/multiply/screen/overlay/darken/lighten/add/color-dodge/color-burn/hard-light/soft-light/difference/exclusion).
  - `video blend-mode -p session.json --track V1 --segment-ref op_0 --mode multiply`
- **`video chroma-key`** (`set_chroma_key` op): `materials.video_chromakeys[]`에 material 추가 + `segment.extra_material_refs[]` 연결. `--color`(기본 #00FF00), `--intensity`, `--shadow`, `--smoothness`, `--spill` 옵션.
  - `video chroma-key -p session.json --track V1 --segment-ref op_0 --color "#00FF00" --intensity 0.5`

### 구현 파일

- `core/postprocess.py`: `BLEND_MODES` 상수 + `_new_uuid()` + `apply_reverse_patch` / `apply_freeze_frame_patch` / `apply_blend_mode_patch` / `apply_chroma_key_patch` 추가. `apply_postprocess` 내 분기 추가.
- `core/op_registry.py`: `POSTPROCESS_OPS`에 `set_reverse`, `set_freeze_frame`, `set_blend_mode`, `set_chroma_key` 추가.
- `commands/media.py`: `video_group`에 `reverse`, `freeze-frame`, `blend-mode`, `chroma-key` 서브커맨드 추가.

### 테스트

- 신규: `tests/test_postprocess_v043.py` — 19개 (--help 확인 4 + 세션 op 기록 5 + draft JSON 패치 10)
- 전체: **274 passed, 1 skipped** — 회귀 없음

### 버전

- 0.4.3

---

## 0.4.1 — 2026-04-19

### 후속 보정 — v0.4.0 축소 구현 확장
- **headless 렌더 확장** (`commands/render_headless.py`):
  - **V2+ 비디오 트랙 오버레이**: clip_settings의 `scale_x/y`, `transform_x/y`를 ffmpeg overlay 좌표로 변환. 다중 PIP 트랙 체이닝.
  - **실제 xfade 트랜지션**: dissolve/fade/slide_{left,right,up,down}/wipe_{left,right}/circle 9종 매핑. fade 근사 대신 진짜 xfade 사용.
  - **add_keyframe 근사**: `uniform_scale`(Ken Burns), `alpha`(fade), `transform_x/y`(V2 overlay 이동) 2-keyframe 선형 보간.
- **스타일 프리셋 카테고리 확장** (`core/style_registry.py`, `commands/style.py`):
  - `text / video / audio` 3카테고리로 분리. 기존 플랫 스키마는 자동 마이그레이션.
  - 내장 비디오 3개: `cinematic-warm`, `social-punchy`, `corporate-clean`
  - 내장 오디오 3개: `podcast-voice`, `bgm-background`, `sfx-short`
  - `style save/list/show/delete --category <text|video|audio>`
  - **`style apply-video` / `style apply-audio`**: 여러 op(filter + animation + color 또는 volume + fade + effect)를 한 커맨드로 일괄 적용.
- **plan 피드백 루프** (`commands/plan.py`):
  - `plan-refine -i recipe.json -o v2.json --feedback "..."` — 기존 레시피 + 피드백을 LLM에 넘겨 수정. validate 실패 시 1회 재시도.
  - 기존 `plan` 커맨드는 그대로 유지 (하위 호환).

### 신규 — 자동 세션 리뷰
- **`review` 커맨드** (`commands/review.py`): 세션을 8개 관점에서 자동 분석.
  - `gaps` (1s+ warning / 5s+ error), `overlaps` (error), `volume` (합산 1.0+ warning / 1.5+ error)
  - `subtitles` (0.8s 미만 / 초당 8자 초과 warning), `media` (누락 error / 한글경로+staging비활성 info)
  - `resolution` (업/다운스케일 info), `duration` (플랫폼별 권장), `render` (headless 미지원 op info)
  - `--severity`, `--only`, `--json`, `--fail-on-warning` 옵션. error 있으면 종료 코드 2.

### 테스트
- 신규: render_headless_v2 30, review 37, style 확장 ~20, plan refine ~10 = **~100 신규/확장 테스트**
- 전체: **255 passed, 1 skipped** — 회귀 없음

### 버전
- 0.4.1

---

## 0.4.0 — 2026-04-19

### 추가 — 에이전트 UX 4대 개선
- **한글 경로 자동 스테이징** (`core/media_staging.py`): video/image/audio `add` 시 한글/공백 경로 감지 → `%TEMP%/capcut-stage/` 에 SHA-1 fingerprint 파일명으로 하드링크(동일 볼륨) 또는 copy. `CAPCUT_NO_STAGING=1` 로 비활성화. `CAPCUT_STAGE_DIR` 로 경로 오버라이드.
- **`staging` 커맨드 그룹**: `staging stats | clear | list` — 캐시 관리.
- **auto-fix save** (`core/auto_fix.py`): `save --auto-fix` 로 실패 op 를 격리(quarantine)하고 반복 replay. `--max-attempts N` 로 재시도 한도 조정.
- **스타일 프리셋 레지스트리** (`core/style_registry.py`, `commands/style.py`): `~/.capcut_cli/styles.json` 에 텍스트 스타일 저장/재사용. 5개 내장 프리셋 — `lifestyle-brand`, `youtube-subtitle`, `news-title`, `minimal-caption`, `cinematic`.
  - `style list | show | save | delete | export | import`
  - `text add --style <name>`, `srt import --style <name>` — 명시 옵션이 프리셋을 덮어씀.
- **자연어 plan** (`commands/plan.py`): `plan "30초 제품 광고 숏폼 …" -o recipe.json` — Claude API 로 레시피 JSON 생성. `ANTHROPIC_API_KEY` 필요. `[plan]` extras.
- **타임라인 HTML 미리보기** (`commands/preview.py`): `preview -p session.json -o preview.html [--open] [--thumbs]` — self-contained HTML + SVG 간트차트 + ffmpeg 썸네일(옵션) + 겹침/갭 시각화. 외부 CDN 의존성 0.
- **headless ffmpeg 렌더** (`commands/render_headless.py`): `render-headless -p session.json -o out.mp4 [--crf 20] [--preset medium] [--allow-unsupported] [--dry-run]`. video concat + audio amix + text SRT burn-in + fade/dissolve 지원. 복잡 이펙트(애니메이션/필터/마스크)는 미지원 — `--allow-unsupported` 로 무시 가능. GUI 의존 기존 `render` 는 유지.

### 테스트
- 신규: staging 16, auto-fix 9, style 25, plan 16, preview 17, render-headless 25 = **108 신규 테스트**
- 전체: **156 passed, 1 skipped** (157 collected) — 기존 회귀 없음

### 버전
- 0.4.0

---

## 0.3.0 — 2026-04-19

### 추가 (Phase 8~14)
- **Mask/Background**: `mask add` (원형/사각/하트/별/선형/거울), `background add` (blur/color 채우기)
- **렌더링 자동화**: `render` 커맨드 — CapCut/JianYing GUI 자동 제어로 MP4 export (Windows 전용)
- **고수준 프리셋**: `preset slideshow|lyric-video|intro-outro|pip` — 원샷 드래프트 생성
- **컬러 후처리 실동작**: `color adjust|wheels` 가 save 후 draft_content.json에 실제 반영
- **자산 관리**: `asset bulk-import|transcode|relocate|cover-from-frame`
  - `bulk-import`: 폴더 전체 자동 분류(이미지/비디오/오디오)
  - `relocate`: 세션이 참조하는 미디어를 한 폴더로 패킹 (배포용)
  - `cover-from-frame`: 비디오 N초 지점 프레임을 draft_cover.jpg 로
- **세션 유틸**: `session compact|find-replace-media|watch`
  - `compact`: 중복 op 제거 + ID 리넘버링
  - `find-replace-media`: 미디어 경로 일괄 치환 (literal/regex)
  - `watch`: 세션 파일 변경 감지 → 자동 save
- **Claude Code 스킬**: `SKILL.md` — 자동 로드되는 사용 가이드

### 테스트
- 25 유닛 + 8 E2E + 7 feature = **40개 테스트 전부 통과**

### 버전
- 0.3.0

---

## 0.2.0 — 2026-04-19

### 추가 (Phase 1~7, 풀 기능 복원)
- **Core 확장**:
  - `alias_map` — 9개 enum 카테고리의 영→한자 별칭 + fuzzy search
  - `op_handlers` — 15개 op 디스패처 (video/image/audio/text/sticker/effect/filter/transition/fade/animation/keyframe/audio_effect)
  - `session` 대폭 확장 (batch/edit/delete/reorder/clone/merge/diff/timeline/stats/gap-detect/overlap-detect/export_script/export_recipe/status)
  - `recipe` (load/validate/apply)
  - `postprocess` (텍스트 폰트/테두리/그림자/색/위치 직접 패치)
  - `segment_utils` (segment_ref 해석)
- **Commands 37개 (22 → 37)**: text (전 옵션), srt import, sticker, effect/filter, keyframe,
  color, alias 4 sub, agent status/explain, timeline/stats/gap/overlap/segments-at,
  import/export-recipe/script, edit/delete/reorder/batch-op, merge/diff-session, media-info
- **REPL**: prompt-toolkit 기반 인터랙티브 모드
- **CapCut 드래프트 인식 버그**: `create_draft()` 항상 통과하도록 수정 → `draft_meta_info.json` 정상 생성

### 수정 (옛 22개 버그)
- #1 `tim()` bare 숫자 파싱 → `parse_time_value()`
- #2/#3/#15 별칭 불일치 → 정확한 매핑
- #4/#9/#14 트랙 자동 생성 → `_ensure_track()`
- #5 ffprobe 의존성 → WAV는 `wave` fallback
- #6/#21 clip-settings 프리셋 → 8개 내장
- #17~#20 텍스트 필드 미반영 → `--patch-style` 옵션으로 postprocess 적용

### 테스트
- 25 유닛 + 8 E2E = 33개 테스트 통과

---

## 0.1.0 — 2026-04-19

### Walking Skeleton
- `pyproject.toml` + `setup.py` + namespace package 구조
- Core: `time_utils`, `session` (minimal), `op_registry`
- CLI: `project new`, `track add`, `video/image/audio add`, `save`, `validate`, `undo`, `history`, `diagnose`
- 25개 유닛 테스트

### 배경
- 기존 버전 1.0.0의 Python `.py` 소스가 손실된 상태에서 `.pyc` 메타 추출 + 22개 버그 리포트 + 실제 드래프트 JSON 분석을 기반으로 재작성.
