# Operations Reference (v0.4.x)

CLI 명령은 *훨씬* 단순한 셋입니다. 옛 v0.3 combo (`add-with-*`)와 일부 video sub-op은 사라졌고, 일부는 별도 최상위 명령으로 분리되었습니다.

## 1. Creation Ops (timeline 세그먼트 생성)

| Op (recipe) | CLI | Required Args | 비고 |
|-------------|-----|---------------|------|
| `add_video` | `video add` | `file`, `start`, `duration` | `--track`, `--clip-settings`, `--volume`, `--speed` |
| `add_image` | `image add` | `file`, `start`, `duration` | duration `auto` 불가 — 명시 필수 |
| `add_audio` | `audio add` | `file`, `start`, `duration` | `--volume`, `--speed` |
| `add_text` | `text add` | `text`, `start`, `duration` | font/border/shadow/clip-settings/style/position-x/-y |
| `add_sticker` | `sticker add` | `file`, `start`, `duration` | 이미지를 스티커로 |
| `add_effect` | `effect add` | `name`, `start`, `duration` | 트랙 자동 |
| `add_filter` | `effect add-filter` | `name`, `start`, `duration` | `--intensity` 0.0~1.0 |
| `add_track` | `track add` | `type`, `name` | 보통 자동 생성, 거의 안 씀 |

**Creation 옵션 공통**: `--track`(없으면 기본 트랙), `--clip-settings`(프리셋 또는 JSON), `--volume`/`--speed`(미디어).

## 2. Sub-Ops (기존 세그먼트 수정)

모두 `--track` + `--segment-ref op_N` 필수. (`--segment` 위치기반은 비추천)

| Op (recipe) | CLI | 추가 인자 | 비고 |
|-------------|-----|----------|------|
| `add_video_animation` | `video add-animation` | `role`(intro/outro/group), `name`, `duration` | **`--role`** (옛 `--category` 아님) |
| `add_text_animation` | `text add-animation` | `role`(intro/outro/loop), `name`, `duration` | |
| `add_video_transition` | `video add-transition` | `name`, `duration` | **`--name`** (옛 `--type` 아님) |
| `add_video_fade` | `video add-fade` | `fade_in` and/or `fade_out` | |
| `add_audio_fade` | `audio add-fade` | `fade_in` and/or `fade_out` | |
| `add_audio_effect` | `audio add-effect` | `name` | echo/reverb/noise-reduction... |
| `add_keyframe` | `keyframe add` | `property`, `time`, `value` | property: alpha, position_x/y, rotation, scale_x/y, uniform_scale, volume |
| `add_color_adjust` | `color adjust` | `brightness`/`contrast`/`saturation`/... | **모두 -1.0~+1.0** |
| `add_color_wheels` | `color wheels` | shadow/midtone/highlight hue/sat | |
| `add_mask` | `mask add` | `type`(circle/rect/heart/star/line), `size`, `feather` | |
| `add_background` | `background add` | `mode`(blur/color), `--blur` 또는 `--color` | |
| `text style-patch` | `text style-patch` | font/border/shadow/clip-settings | save 후 draft_content.json 직접 패치 (텍스트 스타일 버그 우회) |
| `set_reverse` | `video reverse` | (없음) | segment에 `reverse=True` 주입 (v0.4.3 복원) |
| `set_freeze_frame` | `video freeze-frame` | `--duration`(선택) | speed material을 `mode=freeze, speed=0` 로 (v0.4.3 복원) |
| `set_blend_mode` | `video blend-mode` | `--mode`(13종) | `track_attribute.blend_mode` 정수 매핑 (v0.4.3 복원). 정수 매핑은 휴리스틱 — GUI 확인 권장 |
| `set_chroma_key` | `video chroma-key` | `--color`, `--intensity`, `--shadow`, `--smoothness`, `--spill` | materials.video_chromakeys 추가 + extra_material_refs 연결 (v0.4.3 복원). 실제 CapCut draft 키 이름 GUI 확인 권장 |
| `add_lut` | `video lut` | `--file`, `--intensity`, `--name`(선택) | LUT 파일(.cube/.3dl) 등록 + segment.enable_lut=true (v0.4.4 복원). materials 배열 키 이름 GUI 확인 권장 |
| `set_speed_curve` | `video speed-curve` | `--points "t,s;t,s;..."`, `--curve-range`(선택) | speed material의 mode=curve, curve_speed.points 주입 (v0.4.4 복원) |
| `add_color_curves` | `color curves` | `--rgb`, `--red`, `--green`, `--blue` (최소 1개) | color_curves material 추가 + seg.enable_color_curves=true (v0.4.4 복원). 각 채널당 최소 2점 |
| `add_hsl_adjust` | `color hsl` | `--target` (8색), `--hue`, `--saturation`, `--lightness` (-100~+100) | target_color 채널별 HSL 주입. 같은 segment에 다른 target 누적 가능 (v0.4.4 복원) |

## 3. Content / Replacement / Session Ops

| Op | CLI | 비고 |
|----|-----|------|
| `import_srt` | `srt import` | `--style` 프리셋 또는 `--style-json` |
| (매크로) | `text auto-srt` | whisper CLI subprocess → SRT → srt import 재호출 (v0.5.1). 옵션: `--audio`, `--model {tiny\|base\|small\|medium\|large}`, `--language ko`, `--word-level/--segment-level`, `--initial-prompt`, `--output-dir`, `--keep-srt`. 한국어 도메인 전문 용어는 initial-prompt에 `"제품명 전문용어 예시"` 같은 힌트 권장 |
| (없음) | `session find-replace-media` | regex/literal로 미디어 경로 일괄 치환 |
| (없음) | `merge-session --other X --offset auto` | 다른 세션 합치기 |
| (없음) | `diff-session --other X` | op 비교 |
| (없음) | `session compact` | undo 자취 정리 (파괴적) |
| (없음) | `session watch` | 세션 변경 감시 + 자동 save |

## 4. Project / Export

| 명령 | 용도 |
|------|------|
| `project new -n NAME --preset landscape` | 새 세션 |
| `project info -p p.session.json` | 요약 |
| `project status -p p.session.json` | 검증 + 갭 + 겹침 통합 (AI 친화) |
| `project clone -p p.session.json -o copy.session.json` | 복제 |
| `export-recipe -p p.session.json -o r.json` | 세션→레시피 |
| `export-script -p p.session.json -o repro.sh` | 세션→재현 가능 CLI 스크립트 |
| `import-recipe -p p.session.json -f r.json` | 레시피→세션 |
| `validate-recipe -f r.json` | 레시피 구조만 검증 (replay 없이) |

## 5. Validate / Review / Render Pipeline

| 명령 | 용도 |
|------|------|
| `validate -p p.session.json` | replay dry-run (op 시퀀스 정합성) |
| `review -p p.session.json [--severity warning] [--only volume,gaps] [--fail-on-warning]` | 자동 QA |
| `preview -p p.session.json --open [--thumbs]` | HTML 간트차트 미리보기 |
| `save -p p.session.json [--auto-fix --max-attempts 3] [--skip-errors]` | CapCut 드래프트 디스크 저장 |
| `render -p p.session.json -o out.mp4 --resolution 1080P --save-first` | CapCut GUI로 export |
| `render-headless -p p.session.json -o out.mp4 --crf 20 --preset medium` | ffmpeg로 직접 (GUI 없음) |

## 6. Analysis / Debug / Agent

| 명령 | 용도 |
|------|------|
| `agent status -p p.session.json` | 세션 상태 + 다음 추천 작업 |
| `agent explain-error -e "MSG"` | 에러 메시지 해석 |
| `diagnose` | 환경 점검 (예전 `doctor`) |
| `media-info FILE` | ffprobe로 코덱/duration/해상도 |
| `history -p p [--filter add_video]` | op 로그 |
| `timeline -p p [--width 80]` | ASCII 타임라인 |
| `stats -p p` | 길이/트랙/미디어 통계 |
| `segments-at -p p --time 5s` | 특정 시각 활성 세그먼트 |
| `gap-detect -p p [--track V1]` | 갭 |
| `overlap-detect -p p [--track V1]` | 겹침 |
| `undo -p p [-n N] [--type add_filter]` | 마지막 N개 또는 타입별 |
| `alias classes` / `alias list --class TransitionType` / `alias search -k "fade"` / `alias resolve "fade_in"` | enum 도구 |

## 7. Style Preset System

| 명령 | 용도 |
|------|------|
| `style list [--category text\|video\|audio]` | 내장+사용자 스타일 |
| `style show NAME --category text` | JSON 상세 |
| `style save NAME --category text --font ...` | 저장 |
| `style apply-video --track V1 --segment-ref op_0 --style cinematic-warm` | 적용 |
| `style apply-audio --track A1 --segment-ref op_1 --style bgm-background` | 적용 |
| `style export -o backup.json` / `style import -i backup.json` | 백업/복원 |
| `style delete NAME --category text` | 사용자 스타일 삭제 (내장 불가) |

## 8. High-Level Presets (한방 명령)

| 명령 | 용도 |
|------|------|
| `preset slideshow -n N -f IMG_DIR --duration 3s --transition dissolve --audio bgm.mp3 --preset-size 9x16` | 이미지 폴더→슬라이드쇼 |
| `preset lyric-video -n N -a song.mp3 -s lyrics.srt -b bg.jpg --position subtitle-bottom` | 가사 영상 |
| `preset intro-outro -p p --intro intro.png --outro outro.png --transition dissolve` | 인트로/아웃트로 |
| `preset pip -p p -f overlay.mp4 --corner top-right --scale 0.35` | PIP 오버레이 |
| `preset hook -p p -t "훅 텍스트" --category pattern-interrupt --duration 3s` | 쇼츠 첫 3초 훅 (shake+zoom+flash+bold text) |
| `preset kenburns -p p --folder D:/imgs --duration-each 4s --pattern alternating --intensity 0.2` | 이미지 폴더→켄번스 (줌/팬 키프레임 자동) |

### 8-A. `preset hook` 옵션 상세 (v0.4.1~)

- **필수**: `-p/--project`, `-t/--text`
- **선택**: `--duration 3s`, `--category {curiosity|shock|pattern-interrupt|number|promise|contrarian|fear|question|authority|pov}` (기본 `pattern-interrupt`)
- **트랙**: `--video-track V1`, `--text-track T_HOOK` (자동 생성)
- **텍스트**: `--font "Black Han Sans"`, `--size 8.0`, `--color "255,255,255"`
- **효과**: `--zoom 1.08`, `--shake/--no-shake`, `--flash/--no-flash`

카테고리가 shake intensity, flash duration, zoom 값, 텍스트 애니메이션(pop vs fade_in)을 자동 튜닝. 기존 세션의 `--video-track` 첫 세그먼트에 zoom 키프레임 자동 연결. 감지 실패 시 warning.

내부 op 시퀀스: `add_track(text)` → `add_text` → `add_text_animation(intro)` → `add_keyframe × 2(uniform_scale)` → `add_effect(shake)` → `add_effect(flash)`.

### 8-B. `preset kenburns` 옵션 상세 (v0.4.2~)

- **필수**: `-p/--project`, 그리고 `--folder DIR` 또는 `--images "GLOB"` 중 하나 (둘 다 지정 시 에러)
- **시간**: `--duration-each 4s` (각 이미지 표시 시간, `auto` 금지), `--start 0s` (타임라인 시작 오프셋)
- **패턴**: `--pattern {alternating|random|zoom-in|zoom-out|pan-lr|pan-tb}` (기본 `alternating`)
- **강도**: `--intensity 0.2` (`scale_end = 1 + intensity`. 0.1~0.3 권장)
- **트랙**: `--track V1`
- **기타**: `--sort/--no-sort`, `--seed INT` (random 재현)

내부 op 시퀀스: 각 이미지마다 `add_image` + `add_keyframe × 2~4` (시작/끝 `uniform_scale`, pan 패턴은 `transform_x` 또는 `transform_y` 추가).
`render-headless`가 이 키프레임들을 선형 보간으로 줌/팬 적용하므로 GUI 없이도 결과물 동일.

**매크로 CLI 주의**: `preset hook`/`preset kenburns`는 기존 `add_*` op를 반복 호출하는 매크로이므로 recipe 스펙에는 **직접 대응 op 없음**. recipe로 재현하려면 `export-recipe`로 뽑아 그대로 저장.

## 9. Asset / Staging

| 명령 | 용도 |
|------|------|
| `asset bulk-import -p p -f /folder` | 폴더의 모든 미디어를 자동 분류해 추가 |
| `asset relocate -p p -o /collected --update-session` | 미디어를 한 폴더로 묶기 |
| `asset transcode -i in.mov -o out.mp4 --crf 22` | 포맷 변환 |
| `asset cover-from-frame -i clip.mp4 -t 3s -o cover.png` | 드래프트 커버 |
| `staging list` / `staging stats` / `staging clear` | 한글 경로 캐시 관리 |

## 10. Plan (자연어 → 레시피)

| 명령 | 용도 |
|------|------|
| `plan "지시문" --width 1920 --height 1080 --duration 30s --assets-dir /assets -o r.json` | 자연어→레시피 (Claude API) |
| `plan-refine -i r.json -o r.v2.json --feedback "..."` | 레시피 수정 |

## 11. Batch / REPL

| 명령 | 용도 |
|------|------|
| `batch -p p -f ops.json [--skip-errors]` | JSON 파일에서 여러 op |
| `repl` | 인터랙티브 모드 (`use sess.json` → 명령 입력) |

---

## v0.4에서 사라진 것 (참고용)

- `add-with-transition` / `add-with-animation` (combo) — 분리해 호출
- `video add-filter` → `effect add-filter`
- `video add-mask` → `mask add`
- `video add-background` → `background add`
- `video chroma-key` / `video reverse` / `video freeze-frame` / `video blend-mode` — **v0.4.3에서 복원됨** (위 §2 sub-ops 표 참조)
- `video lut` / `video speed-curve` / `color curves` / `color hsl` — **v0.4.4에서 복원됨** (위 §2 sub-ops 표 참조)
- `video speed` (단일 속도값) — 아직 미복원. `video add --speed` 옵션으로 대체 가능
- `clone` (top-level) → `project clone`
- `save-version` / `list-versions` / `restore-version` — 명시적 백업 폴더 + clone로 대체
- `replace material/text/material-by-seg` — 일부는 `session find-replace-media`로 대체
- `add_text_bubble` / `add_text_effect` / `add_tone_effect` / `add_speech_to_song` — recipe만 가능, CLI 직접 명령 없음

세션의 모든 명령 인자는 항상 `--help` 로 확인하세요. CLI는 `--json` 글로벌 플래그로 기계 파싱 가능 출력을 지원합니다.
