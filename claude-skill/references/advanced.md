# Advanced Reference (v0.4.x)

## 1. Agent Decision Tree

```
영상 후처리 요청
├─ CLI 설치 확인: cli-anything-capcut diagnose
│   ├─ 정상 → CLI 사용
│   └─ 문제 → pip install -e <pyCapCut>/agent-harness
│
├─ 작업 유형 판단:
│   ├─ 정형 (슬라이드쇼/가사영상/인트로/PIP) → preset 명령 1줄
│   ├─ 자연어로만 표현 → plan → import-recipe
│   ├─ 단일 클립 + 표준 효과 → import-recipe (recipe JSON)
│   ├─ 멀티 클립 + 색보정/이펙트 다수 → 개별 명령 시퀀스
│   ├─ 동일 스타일 반복 → style save → style apply-* / --style
│   └─ 폴더 통째로 → asset bulk-import
│
├─ 검증 단계 (반드시): validate → review → preview --open
│
└─ 출력:
    ├─ 최종 납품 → render --save-first  (CapCut GUI ground truth)
    └─ 빠른 미리보기 / CI → render-headless --crf 23 --preset fast
```

| 상황 | 접근법 |
|------|--------|
| 정형 패턴 (슬라이드/가사/인트로) | `preset *` |
| 사용자가 명령 짜기 싫어함 | `plan "..."` → `import-recipe` |
| 정해진 패턴 반복 | recipe JSON + `import-recipe` |
| 탐색적 작업 | 개별 CLI + `undo` |
| 다수 클립 일괄 | `asset bulk-import` 또는 `batch -f ops.json` |
| 프로덕션 | recipe + `validate-recipe` + `import-recipe` + `review --fail-on-warning` |
| 텍스트 스타일 중복 | `style save` 1번 → 매번 `--style NAME` |

## 2. Agent Efficiency Tips

1. **`agent status` 자주**: 다음 추천 작업까지 알려줌. 디버깅 시작점.
2. **`--json`**: 모든 명령에 글로벌 플래그. 파싱 가능한 출력.
3. **`history --filter add_video`**: op 검색.
4. **`save --auto-fix --max-attempts 3`**: 자동 격리 + 재시도. 인터랙티브 아닌 곳엔 디폴트.
5. **`review --fail-on-warning`**: CI에서 warning도 실패 처리.
6. **`alias search -k "fade"`**: 한자/영어 모두 매치.
7. **`asset bulk-import`**: 폴더에서 자동 분류 import. 손으로 add 반복 X.

## 3. v0.3 → v0.4 마이그레이션

| 옛 명령 | 새 명령 |
|---------|---------|
| `doctor` | `diagnose` |
| `validate-full` | `validate` (+ `review` 별도) |
| `recipe-validate` | `validate-recipe` |
| `recipe-apply` | `import-recipe` |
| `save --register` | `save` |
| `save-skip-errors` | `save --skip-errors` 또는 `save --auto-fix` |
| `alias search-all` | `alias search -k <kw>` |
| `video add-filter` | `effect add-filter` |
| `video add-mask` | `mask add` |
| `video add-background` | `background add` |
| `clone` | `project clone` |
| `add-with-transition` | `video add` + `video add-transition` (분리) |
| `add-with-animation` | `video add` + `video add-animation` (분리) |
| `--category intro` | `--role intro` |
| `--type dissolve` | `--name dissolve` |
| `--brightness 10` (0~100 가정) | `--brightness 0.1` (-1~+1) |
| `--intensity 40` (0~100 가정) | `--intensity 0.4` (0~1) |

**완전히 제거된 명령** (v0.4에선 없음, draft_content.json 직접 패치 필요):
- `video chroma-key`
- `video lut`
- `video blend-mode`
- `video reverse`
- `video freeze-frame`
- `video speed` / `video speed-curve`
- `color curves`
- `color hsl`
- `replace material/text/material-by-seg` (일부는 `session find-replace-media`로 대체)
- `save-version` / `list-versions` / `restore-version`

## 4. Error Recovery

```
save 실패
├─ 1. diagnose                                      # 환경
├─ 2. validate                                       # op 시퀀스
├─ 3. agent explain-error -e "MSG"                   # AI 해석
├─ 4. history --filter <op_type>                     # 어디서 깨졌나
├─ 5. undo --type X 또는 edit-op -i N --args '...'   # 수정
└─ 6. save --auto-fix --max-attempts 3              # 자동 복구
```

| 에러 | 해결 |
|------|------|
| `Track 'V1' not found` | creation op의 `--track` 확인. 자동 생성됨 |
| `segment_ref 'op_5' not found` | `history` 또는 `agent status`로 ID 확인 |
| `File not found` | staging 정상 동작 확인 (`staging list`) |
| `Fade not supported on TextSegment` | `keyframe add --property alpha` |
| `Duration 'auto' not supported for image` | `-d 3s` 명시 |
| `Invalid enum 'fade_in_xxx'` | `alias search -k "fade"` |
| `--category not recognized` | `--role` 사용 (v0.4) |
| `--type not recognized` | `--name` 사용 (v0.4) |

**방어 패턴**:
```bash
cli-anything-capcut project clone -p p.session.json -o backup.session.json
cli-anything-capcut validate -p p.session.json
cli-anything-capcut review   -p p.session.json --severity warning --fail-on-warning
cli-anything-capcut preview  -p p.session.json --open
cli-anything-capcut save     -p p.session.json --auto-fix
```

## 5. Session Management

```bash
# Undo
cli-anything-capcut undo -p sess.json                        # 마지막 1개
cli-anything-capcut undo -p sess.json -n 3                   # 3개
cli-anything-capcut undo -p sess.json --type add_filter      # 타입별

# Project clone
cli-anything-capcut project clone -p sess.json -o copy.session.json

# Session merge / diff
cli-anything-capcut merge-session -p main.session.json --other other.session.json --offset auto
cli-anything-capcut diff-session -p A.session.json --other B.session.json

# 미디어 경로 일괄 치환 (예: D:/old → E:/new)
cli-anything-capcut session find-replace-media -p sess.json --pattern "D:/old" --replacement "E:/new" --dry-run
cli-anything-capcut session find-replace-media -p sess.json --pattern "D:/old" --replacement "E:/new" -y

# 미디어 한 폴더로 묶기 (이사용)
cli-anything-capcut asset relocate -p sess.json -o "/collected" --update-session

# undo 자취 정리
cli-anything-capcut session compact -p sess.json --dry-run
cli-anything-capcut session compact -p sess.json -y

# 자동 save (개발 중)
cli-anything-capcut session watch -p sess.json --interval 2
```

## 6. REPL Mode

```bash
cli-anything-capcut repl
# > project new -n MyVideo --preset landscape
# > use MyVideo.session.json
# > video add -f clip.mp4 -s 0s -d 5s     (no -p needed once `use`d)
# > status
# > save
# > help / quit
```

## 7. Color Grading 패턴 (v0.4)

값 범위는 모두 **-1.0 ~ +1.0** (옛 0~100 아님).

### 시네마틱 (어둡고 대비 강하게)
```bash
cli-anything-capcut color adjust -p sess.json --track V1 --segment-ref op_0 \
  --brightness -0.05 --contrast 0.15 --saturation -0.1 --temperature -0.05
cli-anything-capcut effect add-filter -p sess.json --name film --intensity 0.4
cli-anything-capcut effect add -p sess.json --name vignette -s 0s -d auto
```

### SNS 밝은 톤
```bash
cli-anything-capcut color adjust -p sess.json --track V1 --segment-ref op_0 \
  --brightness 0.1 --contrast 0.05 --saturation 0.15 --temperature 0.1
cli-anything-capcut effect add-filter -p sess.json --name vivid --intensity 0.35
```

### Color Wheels (음영/하이라이트 색감)
```bash
cli-anything-capcut color wheels -p sess.json --track V1 --segment-ref op_0 \
  --shadow-hue 220 --shadow-sat 0.15 --highlight-hue 40 --highlight-sat 0.1
```

> **주의**: v0.4엔 `color curves`/`color hsl`이 없음. 더 정밀한 그레이딩이 필요하면 LUT 파일을
> CapCut GUI에서 직접 적용하거나, draft_content.json 패치.

## 8. 그린스크린 / 합성 — 한계

v0.4 CLI엔 `chroma-key` / `blend-mode` 명령이 없음. 두 가지 우회:

1. **CapCut GUI에서 마스크 처리**: CLI로 두 클립만 V1/V2에 배치 → save → CapCut에서 크로마키.
2. **render-headless에서 ffmpeg 옵션 직접 추가**: 미지원이지만 ffmpeg 명령을 `--dry-run` 으로 추출해 수동 보강.

마스크는 됨:
```bash
cli-anything-capcut mask add -p sess.json --track V2 --segment-ref op_1 \
  --type circle --size 0.5 --feather 20
```

## 9. Text Styling 패턴

```bash
cli-anything-capcut text add -p sess.json -t "Premium" -s 0s -d 3s \
  --font arial --size 6.0 --bold \
  --color 255,255,255 --letter-spacing 3 \
  --border '{"alpha":1.0,"color":[0,0,0],"width":0.08}' \
  --shadow '{"alpha":0.9,"color":[0,0,0],"distance":5,"angle":315}' \
  --clip-settings title-center
```

**Border**: `{"alpha": float, "color": [R,G,B], "width": float}` (width는 0~1 normalized)
**Shadow**: `{"alpha": float, "color": [R,G,B], "distance": float, "angle": int}`
**Background**: 텍스트엔 background 옵션 없음. `clip-settings` 또는 별도 sticker로 처리.

**스타일이 적용 안 되는 버그가 의심되면 `text style-patch`** — save 후 draft_content.json 직접 패치:
```bash
cli-anything-capcut text style-patch -p sess.json --track T1 --segment-ref op_5 \
  --font arial --border '{"alpha":1,"color":[0,0,0],"width":0.08}'
```

## 10. SRT + 스타일 프리셋

```bash
# 내장 프리셋 사용 (가장 단순)
cli-anything-capcut srt import -p sess.json -f subs.srt --track T1 --style youtube-subtitle

# 커스텀 프리셋 만들고 적용
cli-anything-capcut style save my-yellow-cap --category text \
  --font arial --size 5.5 --bold --color 255,235,0 \
  --border '{"alpha":1,"color":[0,0,0],"width":0.1}' \
  --clip-settings subtitle-bottom \
  --description "노란 굵은 캡션"
cli-anything-capcut srt import -p sess.json -f subs.srt --track T1 --style my-yellow-cap

# 더 세밀하게: --style-json 으로 추가 오버라이드
cli-anything-capcut srt import -p sess.json -f subs.srt --track T1 \
  --style youtube-subtitle --style-json '{"size":6.0}'
```

## 11. 폴더 통째로 → 영상

`asset bulk-import`는 폴더의 모든 미디어를 자동 분류해 추가합니다 (확장자로 video/audio/image 판단).

```bash
cli-anything-capcut project new -n quick --preset landscape
cli-anything-capcut asset bulk-import -p quick.session.json -f "D:/촬영/" \
  --image-duration 3s --sort
cli-anything-capcut review -p quick.session.json
cli-anything-capcut save -p quick.session.json
```

## 12. 빠른 슬라이드쇼 한 줄

```bash
cli-anything-capcut preset slideshow -n quick \
  -f "D:/사진들/" \
  --duration 4s --transition dissolve --transition-duration 600ms \
  --audio "D:/bgm.mp3" --preset-size 9x16
cli-anything-capcut review -p quick.session.json
cli-anything-capcut render-headless -p quick.session.json -o "D:/quick.mp4" --crf 22
```
