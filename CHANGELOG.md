# Changelog

> **완료 판정 기준:** op 를 추가한 기능은 CLI 실행 -> save -> 산출 draft 필드 확인까지 통과해야 완료로 적는다.
> 그리고 **사용자가 눈으로 보는 결과(폰트·효과 등 렌더 결과)를 바꾸는 기능은 CapCut GUI 에서
> 실제로 반영되는지 확인해야** 완료로 적는다 — draft 에 필드가 있어도 CapCut 이 읽지 않으면
> 사용자에게는 아무 일도 일어나지 않는다 (2026-09-01 폰트 실측으로 확인, docs/capcut-gui-verification.md).

## 0.5.4 - 2026-09-21 (문서/메타데이터 정확성)

### 수정 - pyproject 가 OS 를 잘못 알리고 있었다

`Operating System :: OS Independent` 로 선언되어 있었다. 실제로는 Windows 전용이다.
폰트 해석이 CapCut 캐시 / CapCut SystemFont / 사용자 Fonts / Windows Fonts 네 경로를
스캔하고, 드래프트 폴더 감지와 GUI 렌더도 Windows 경로를 전제한다(그래서 CI 도 windows
러너로 옮겼다). macOS/Linux 사용자가 이 메타데이터를 보고 설치하면 폰트 해석부터
실패한다. `Microsoft :: Windows` 로 정정했다.

### 수정 - README 가 없는 경로를 안내하고 있었다

'옛 버전 스펙' 절이 `_recovered/capcut/` 와 `_recovered/live_sample_analysis.md` 를
가리켰으나 두 경로 모두 공개 저장소에 없다(개발 저장소 전용). 해당 절을 제거하고,
대신 실제로 있는 `scripts/` 설명을 넣었다.

프로젝트 구조 목록도 낡아 있었다. commands 11 개(style, mask, asset, preset, plan,
preview, render, render_headless, import_draft, review, session_utils)와
core 3 개(style_registry, media_staging, auto_fix)가 빠져 있었다. 테스트 수도
25 파일 / 396 tests 로 적혀 있던 것을 24 파일 / 398 tests 로 맞췄다.

### 추가 - 영어 README

공개 저장소의 문서가 전부 한국어였다. 스타를 누른 사용자 중 확인되는 위치가 독일과
이탈리아인데 영어 문서가 하나도 없었다. `README.md` 를 영어로 두고 기존 한국어 문서를
`README.ko.md` 로 옮겼다. 양쪽 상단에서 서로 링크한다.

첫 화면 메시지도 바꿨다. 기존 첫 문장은 "드래프트를 CLI 로 스크립팅하는 하네스"라는
구현 설명이었다. 이 도구가 실제로 파는 것은 "AI 에이전트가 CapCut 편집을 직접 조종한다"
쪽이므로 그것을 먼저 쓰고, 데모 영상을 링크했다. CLI 와 MCP 비교는 접이식 절로 넣되
인용한 벤치마크가 도구 방식 일반에 대한 외부 측정이며 이 프로젝트를 잰 수치가 아님을
명시했다.

## 0.5.3 - 2026-09-21 (폰트 해석 + 공개 게이트)

### 수정 - 일반명 폰트가 한글 미지원 파일에 매칭되던 문제

내장 스타일 `text/cinematic` 의 폰트는 `serif` 라는 일반명이다. CapCut 폰트
경로(캐시 / SystemFont)는 한글 cmap 을 검사하지 않고 별칭을 등록하므로
(`_discover_available_fonts_at` 의 2, 3번), 이 별칭이 SourceSerif4
(한글 cmap 없음)에 매칭되어 한글 자막이 조용히 깨졌다. 게다가 토큰 매칭은
"후보가 유일할 때"만 성립해서 PC 마다 결과가 달랐다.

- `GENERIC_FONT_FALLBACKS` 추가. 일반명(`serif` / `sans_serif` / `monospace`)을
  한글 지원이 확인된 구체 폰트 우선순위로 해석한다.
- 구체 후보가 없을 때만 토큰 매칭으로 내려가되, 파일 **이름**이 아니라 한글
  cmap 유무로 수락을 판단한다. 둘 다 실패하면 후보 목록을 담아 알린다.
- 실측: `serif` 해석이 SourceSerif4_18pt-BoldItalic.ttf(한글 미지원, 게다가
  BoldItalic)에서 NanumMyeongjo-Bold.ttf(한글 지원)로 바뀐다.

### 추가 - 공개 저장소 개인정보 게이트

`scripts/scan_private.py` — git 추적 파일에서 실명 / 개인 작업 경로 /
타 프로젝트 고유명 / 비밀키를 찾고 하나라도 있으면 종료 코드 1.
공개 저장소 CI 에 별도 job 으로 배선했다. 개인 개발본에서 동기화할 때마다
사람이 기억해서 익명화하는 방식은 언젠가 실패한다.

한글 경로 일반(`D:/촬영/`)은 일부러 잡지 않는다. 한글 경로 처리가 이 도구의
핵심 기능이라 문서 예제와 테스트 데이터에 정상적으로 등장하며, 오탐으로
게이트가 자주 깨지면 게이트를 믿지 않게 된다.

테스트 396 -> 398 passed.

## 0.5.2 - 2026-09-21 (공개 저장소 동기화)

이전 공개본(2026-04-27)과 개발 저장소의 격차를 해소한 릴리스다.

- **수정**: 이전 공개본은 `POSTPROCESS_OPS` 배선 누락으로
  `video reverse` / `freeze-frame` / `blend-mode` / `chroma-key` / `lut` / `speed-curve`,
  `color curves` / `hsl` 8종이 실행 즉시 예외를 냈다. 해당 경로를 복구했다.
- **신규**: `import-draft`(CapCut GUI draft 역변환), `text auto-srt`(whisper 자동 자막),
  `gap-detect` / `overlap-detect`, `merge-session`, 사용자 폰트 폴더 스캔.
- **테스트**: 309 -> 396 passed. CLI -> replay -> save 전 구간을 지나는
  E2E 매트릭스로 8종 각각의 draft delta를 검증한다.
- **문서**: Claude Code 스킬(`claude-skill/`)을 2026-09-01 기준으로 갱신했다.

## 0.5.1 — 2026-09-01 (검증 복구)

### R16 — CapCut GUI 프로젝트 import 실전 대응

- CapCut GUI가 만든 draft는 트랙 `name`이 전부 빈 문자열이라 `import-draft` 결과가 `_default_` 한 트랙으로 뭉쳤다. 트랙별 gap/overlap 검사가 통째로 무의미해지던 것을 타입별 자동 명명(`V1`/`T1`/`A1`/`E1`/`S1`/`F1`, 기존 이름은 보존·충돌 회피)으로 고쳤다.
- 미디어 경로가 `##_draftpath_placeholder_<UUID>_##/...` 플레이스홀더로 남아 `media` 검사가 전부 무용지물이던 것을 draft 폴더 기준 절대경로 치환으로 고쳤다. 절대경로는 그대로 두고, 치환 후 파일이 없고 실제 참조된 소재만 경고한다.
- 실물 검증: 실제 CapCut GUI 프로젝트(27트랙 78세그먼트 2:54)에서 27트랙 전부 명명·24개 경로 치환 확인. 396 passed.

### R0 — 독립 저장소와 기준선

- 독립 git 저장소와 baseline을 구성했다.
- 복구 시험에서 `core.autocrlf=true`가 LF -> CRLF 변환으로 롤백 해시를 바꾸는 것을 발견해 껐다.

### R1 — 실제 저장 경로 E2E

- CLI -> replay -> save를 타고 산출 draft 필드까지 확인하는 E2E 매트릭스 테스트를 신설했으며, 실패하는 red 상태를 먼저 커밋했다.

### R2 — postprocess replay 배선

- `POSTPROCESS_OPS`를 단일 소스로 순회해 8종 postprocess op를 replay에 배선했다. op 이름을 별도로 하드코딩하지 않았다.
- `setdefault(k, {})`가 무력화되는 3곳에 타입 가드를 추가했다. pycapcut이 `track_attribute`를 int, `curve_speed`를 None으로 만드는 경우를 처리한다.

### R3 — alias 감사

- 죽은 alias 매핑 107건을 remapped 49 / removed 27 / deferred 31로 결산했다.
- 재실행 가능한 감사 스크립트 `scripts/alias_audit.py`와 manifest를 남겼다.

### R4 — preset hook

- `preset hook` 기본 호출을 0/10에서 10/10으로 복구했다.
- `add_effect` 트랙 자동 배정을 `Session.append_operation()` 한 곳에 두고, 존재하지 않던 별칭 `pop` -> `bounce`, `flash` -> `glow`로 교체했다.

### R5 — `--font` 이중 경로

- `--font`를 번들 `resource_id` 348개와 로컬 TTF `font_path` 47개 두 경로로 연결했다.
- 번들 목록은 `FontType`에서 기계 생성하고, 로컬 목록은 폰트 폴더 스캔과 cmap 검사로 한글 지원 여부를 판별한다.
- 해석할 수 없는 이름은 오류로 중단하며, `postprocess_applied`는 실제 변경분만 집계한다.

### R6 — 트랙별 gap/overlap 검사

- `gap-detect`/`overlap-detect`가 track 미지정 시 전 트랙을 한 타임라인으로 뭉치던 동작을 트랙별 순회로 수정했다.
- 결과에 track 이름을 포함한다.

### R7 — `segment_ref` 경계 검증

- CLI 경계에서 `segment_ref`를 검증하고, pycapcut의 중국어 트랙 예외 4종을 한국어로 변환했다.
- `--segment-ref` help를 22개 명령에서 통일했다.
- **`Session.append_operation()`은 건드리지 않았다.** `core/auto_fix.py`의 quarantine이 "잘못된 segment_ref를 수용한 뒤 격리한다"를 전제로 한 의도된 복원력 설계이기 때문이다.

### R8 — 세션 병합

- `merge-session`에 동명 트랙 병합/리네임 정책을 적용했다.

### R11 — dangling material 참조

- 텍스트 기본 1건은 pycapcut 책임으로 확인해 수정하지 않았다.
- 8개 modifier op의 추가 1건은 cli_anything의 호출 순서 문제로 확인해 수정했다.
- `review`에 참조 무결성 검사를 추가했다.

### 테스트와 검증 범위

- 전체 테스트: **309 -> 374 passed**.
- CapCut GUI 검증은 수행하지 않았다.

## 0.5.1 — 2026-04-19 (최초 기록)

### 신규 — `text auto-srt` 서브커맨드 (whisper CLI 연동 자동 자막)

- **`text auto-srt`**: 오디오/영상 파일을 받아 `whisper` CLI를 subprocess로 호출 → SRT 자동 생성 → 기존 `srt import` 로직으로 세션에 연결. 한 줄 명령으로 자막 자동 생성.
  - `text auto-srt -p session.json --audio interview.mp4 --model small --language ko`
  - `--word-level/--segment-level`: 단어 단위 vs 세그먼트 단위 타임스탬프 (기본: word-level)
  - `--initial-prompt "호텔 디럭스 스위트 트윈"`: 한국어 도메인 힌트 전달
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
- 당시 기록: **306개 통과, 1개 건너뜀** (예상치이며 실행 검증 기록 아님)

### 버전

- 0.5.1

## 0.4.4 — 2026-04-19

> **정정 (2026-09-01):** 아래 4종과 0.4.3의 4종을 합친 8종은 `POSTPROCESS_OPS`에는 등록됐지만 `_OP_HANDLERS` 배선이 빠져 replay가 즉시 raise했으므로 당시에는 실제로 동작하지 않았다. CLI의 op 기록과 postprocess의 JSON 패치를 각각 직접 호출한 테스트만 있었고 CLI -> replay -> save 경로는 지나가지 않았다. 2026-09-01에 `POSTPROCESS_OPS`를 단일 소스로 순회하도록 배선하고 E2E 매트릭스로 수정 사실을 검증했다.

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
- 당시 기록: **300개 통과, 1개 건너뜀**. 위 정정과 같이 이 결과는 해당 4종의 실제 동작을 입증하지 못했다.

### 버전

- 0.4.4

## 0.4.3 — 2026-04-19

> **정정 (2026-09-01):** 아래 4종과 0.4.4의 4종을 합친 8종은 `POSTPROCESS_OPS`에는 등록됐지만 `_OP_HANDLERS` 배선이 빠져 replay가 즉시 raise했으므로 당시에는 실제로 동작하지 않았다. CLI의 op 기록과 postprocess의 JSON 패치를 각각 직접 호출한 테스트만 있었고 CLI -> replay -> save 경로는 지나가지 않았다. 2026-09-01에 `POSTPROCESS_OPS`를 단일 소스로 순회하도록 배선하고 E2E 매트릭스로 수정 사실을 검증했다.

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
- 당시 기록: **274개 통과, 1개 건너뜀**. 위 정정과 같이 이 결과는 해당 4종의 실제 동작을 입증하지 못했다.

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
- 당시 기록: **255개 통과, 1개 건너뜀**

### 버전
- 0.4.1

---

## 0.4.0 — 2026-04-19

### 추가 — 에이전트 UX 4대 개선
- **한글 경로 자동 스테이징** (`core/media_staging.py`): video/image/audio `add` 시 한글/공백 경로 감지 → `%TEMP%/capcut-stage/` 에 SHA-1 fingerprint 파일명으로 하드링크(동일 볼륨) 또는 copy. `CAPCUT_NO_STAGING=1` 로 비활성화. `CAPCUT_STAGE_DIR` 로 경로 오버라이드.
- **`staging` 커맨드 그룹**: `staging stats | clear | list` — 캐시 관리.
- **auto-fix save** (`core/auto_fix.py`): `save --auto-fix` 로 실패 op 를 격리(quarantine)하고 반복 replay. `--max-attempts N` 로 재시도 한도 조정.
- **스타일 프리셋 레지스트리** (`core/style_registry.py`, `commands/style.py`): `~/.capcut_cli/styles.json` 에 텍스트 스타일 저장/재사용. 5개 내장 프리셋 — `hotel-brand`, `youtube-subtitle`, `news-title`, `minimal-caption`, `cinematic`.
  - `style list | show | save | delete | export | import`
  - `text add --style <name>`, `srt import --style <name>` — 명시 옵션이 프리셋을 덮어씀.
- **자연어 plan** (`commands/plan.py`): `plan "30초 호텔 홍보 숏폼 …" -o recipe.json` — Claude API 로 레시피 JSON 생성. `ANTHROPIC_API_KEY` 필요. `[plan]` extras.
- **타임라인 HTML 미리보기** (`commands/preview.py`): `preview -p session.json -o preview.html [--open] [--thumbs]` — self-contained HTML + SVG 간트차트 + ffmpeg 썸네일(옵션) + 겹침/갭 시각화. 외부 CDN 의존성 0.
- **headless ffmpeg 렌더** (`commands/render_headless.py`): `render-headless -p session.json -o out.mp4 [--crf 20] [--preset medium] [--allow-unsupported] [--dry-run]`. video concat + audio amix + text SRT burn-in + fade/dissolve 지원. 복잡 이펙트(애니메이션/필터/마스크)는 미지원 — `--allow-unsupported` 로 무시 가능. GUI 의존 기존 `render` 는 유지.

### 테스트
- 신규: staging 16, auto-fix 9, style 25, plan 16, preview 17, render-headless 25 = **108 신규 테스트**
- 당시 기록: **156개 통과, 1개 건너뜀** (157 collected)

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
