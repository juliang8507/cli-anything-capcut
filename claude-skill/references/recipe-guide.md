# Recipe Template Guide (v0.4.x)

## What is a Recipe?

레시피는 한 번의 명령으로 여러 op를 일괄 적용하기 위한 포터블 JSON입니다.
프로젝트 메타(name/width/height/fps) + operations 배열로 구성.

## Using Recipe Templates

`references/recipes/`의 5개 템플릿은 placeholder가 들어있어, 실제 파일 경로로 치환 후 사용.

### Placeholder Substitution

| Placeholder | Replace With | Example |
|------------|-------------|---------|
| `{{VIDEO_FILE}}` | 비디오 파일 (한글 경로 OK — staging이 처리) | `D:/촬영/main.mp4` |
| `{{AUDIO_FILE}}` | BGM/음악 | `D:/temp/bgm.mp3` |
| `{{SRT_FILE}}` | SRT 자막 | `D:/temp/subs.srt` |
| `{{IMAGE_FILE}}` | 이미지/로고 | `D:/temp/logo.png` |
| `{{NARRATION_FILE}}` | TTS/나레이션 | `D:/temp/narration.wav` |
| `{{LUT_FILE}}` | LUT 컬러 그레이딩 (v0.4 CLI 미지원, draft 패치 필요) | `D:/luts/film.cube` |

### Apply Workflow (v0.4)

```bash
# 1. 템플릿 읽고 placeholder 치환 (에이전트가 JSON 편집해 임시 파일에 저장)

# 2. 구조만 검증 (replay 없이, 빠름)
cli-anything-capcut validate-recipe -f my_recipe.json

# 3. 새 세션에 적용 (project 메타 포함)
cli-anything-capcut import-recipe -p my.session.json -f my_recipe.json

# 4. 검증 + 사람 확인
cli-anything-capcut validate -p my.session.json
cli-anything-capcut review   -p my.session.json --severity warning
cli-anything-capcut preview  -p my.session.json --open

# 5. 저장
cli-anything-capcut save -p my.session.json --auto-fix
```

### Agent Workflow

1. **Read**: `references/recipes/`에서 적합한 템플릿
2. **Replace**: 모든 `{{PLACEHOLDER}}` 치환
3. **Adjust**: 필요시 duration 변경 (`"auto"` → `"5s"` 등)
4. **Update to v0.4 spec**: 옛 템플릿이라면 다음 점검:
   - `"category": "intro"` → `"role": "intro"`
   - `"type": "dissolve"` → `"name": "dissolve"`
   - `"intensity": 40` → `"intensity": 0.4`
   - `"brightness": 5` → `"brightness": 0.05`
   - `add_video_filter`/`add_video_mask`/`add_video_background` → `add_filter`/`add_mask`/`add_background`
5. **Validate-recipe**: 구조 빠른 체크
6. **Import-recipe**: 적용
7. **Customize**: 추가 미세조정은 개별 명령으로
8. **Save**: `save --auto-fix`

### Available Templates

| Template | Description | Best For |
|----------|-------------|----------|
| `luxury-b2b.json` | Premium corporate + cinematic + slow zoom | B2B 프로모 |
| `social-short.json` | 1080x1920 + vivid + 텍스트 오버레이 | TikTok/Shorts |
| `cinematic.json` | film + S-curve + ramping | 시네마틱 |
| `tutorial.json` | multi-clip + dissolve + typewriter | 튜토리얼 |
| `music-video.json` | cyberpunk + glitch + 램핑 + chromakey* | 뮤직비디오 |

> **\*** music-video.json의 chroma-key는 v0.4 CLI에서 지원 안 됨. recipe 적용 후 CapCut GUI에서
> 직접 처리하거나 draft_content.json 패치.

### Recipe → 추가 미세조정 예시

```bash
# 레시피 적용 후
cli-anything-capcut import-recipe -p sess.json -f recipe.json

# v0.4 색보정 (값 -1.0~+1.0)
cli-anything-capcut color adjust -p sess.json --track V1 --segment-ref op_0 \
  --brightness 0.05 --contrast 0.1

# 추가 텍스트 (combo 명령 없으니 분리 호출)
cli-anything-capcut text add -p sess.json -t "Extra Title" -s 10s -d 3s \
  --style cinematic   # 또는 --font arial --size 6 ...
cli-anything-capcut text add-animation -p sess.json --track T1 --segment-ref op_N \
  --role intro --name typewriter --duration 0.5s
cli-anything-capcut text add-animation -p sess.json --track T1 --segment-ref op_N \
  --role outro --name fade_out --duration 0.5s

# 검증 + 저장
cli-anything-capcut review -p sess.json
cli-anything-capcut save -p sess.json --auto-fix
```

### Recipe vs Batch vs Plan

| 방법 | 입력 | 사용 시점 |
|------|------|----------|
| `import-recipe` | recipe JSON (+project meta) | 새 프로젝트 처음부터 |
| `batch` | ops JSON (project 미포함) | 기존 세션에 일괄 추가 |
| `plan` | 자연어 + assets-dir | 사용자가 명령 짜기 싫을 때 |

플로우: `plan` → `validate-recipe` → `import-recipe`. 자연어로 시작해도 결국 검증 가능한
JSON으로 떨어지므로 안전.
