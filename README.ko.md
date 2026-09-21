# cli-anything-capcut

[![tests](https://github.com/juliang8507/cli-anything-capcut/actions/workflows/test.yml/badge.svg)](https://github.com/juliang8507/cli-anything-capcut/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**[English](README.md)** · 한국어

**AI 에이전트가 CapCut 영상 편집을 직접 조종하게 만드는 CLI.**
Claude Code, Cursor 같은 에이전트가 50개 이상의 명령어와 `--json` 출력을 통해
GUI 없이 드래프트를 만들고, 검증하고, MP4까지 렌더합니다.
`pyCapCut` 위에서 이벤트 소스 세션을 관리하며 원샷 커맨드와 REPL을 제공합니다.

▶ **[데모 영상 — AI가 CapCut을 조종한다 (2분 38초)](https://www.youtube.com/watch?v=pgx5QqAt8Is)**

<details>
<summary><b>왜 MCP 서버가 아니라 CLI인가</b></summary>

에이전트 도구를 MCP 서버로 붙이면 도구 스키마가 컨텍스트를 상시 점유합니다.
CLI는 필요할 때만 호출되고 출력이 그대로 텍스트라 에이전트가 파싱해 쓰기 쉽습니다.
그래서 이 프로젝트는 모든 명령에 `--json`을 두고, `agent status` 같은
에이전트 전용 명령으로 "다음에 뭘 해야 하는지"까지 돌려줍니다.

에이전트 도구를 CLI로 제공할 때 MCP 대비 토큰 효율이 크게 유리하다는 외부 벤치마크가
있습니다 (ScaleKit 2026, Jannik Reinhard 2026). 다만 이는 **도구 방식 일반에 대한 비교이며
이 프로젝트를 직접 측정한 수치가 아닙니다.**

</details>

> **현재 버전: 0.5.4** · Windows 전용
> 변경 이력은 [CHANGELOG.md](CHANGELOG.md) 참조.

## 설치

```bash
# 1) upstream library (pycapcut)
#
# PyPI 의 pycapcut 0.0.3 에는 TextSegment(shadow=...) 가 없다. 내장 텍스트
# 스타일이 shadow 를 쓰므로 PyPI 버전만으로는 `text add --style ...` 이 실패한다.
# upstream git 에는 들어가 있으나(2025-08-15, b846b95) 그 뒤로 PyPI 배포가 없다.
#
# 그리고 upstream setup.py 는 git 에 커밋되지 않은 pypi_readme.md 를 읽기 때문에
# `pip install git+https://...` 가 FileNotFoundError 로 실패한다. clone 후 보완해서 설치한다.
git clone https://github.com/GuanYixuan/pyCapCut.git
cd pyCapCut
git checkout 00c223aa246f955d741b17b703e10270b22ec75e
cp README.md pypi_readme.md          # PowerShell: Copy-Item README.md pypi_readme.md
pip install .
cd ..

# 2) this CLI
pip install -e .
```

> shadow 없이도 쓰겠다면 `pip install pycapcut` 로 충분하다. 단 내장 텍스트
> 스타일(`text add --style`)은 동작하지 않는다.

### 실행 환경

Windows 전용이다. 폰트 해석은 CapCut 캐시 / CapCut SystemFont / 사용자 Fonts /
Windows Fonts 네 위치를 스캔하고, 드래프트 폴더 감지와 GUI 렌더도 Windows 경로를
전제한다. CI 도 같은 이유로 windows 러너에서 돈다.

`ffmpeg/ffprobe`가 PATH에 있으면 미디어 길이 자동 감지 가능합니다.

## 빠른 사용

```bash
# 환경 점검
cli-anything-capcut diagnose

# 새 프로젝트
cli-anything-capcut project new --name my-mv --preset portrait

# 트랙
cli-anything-capcut track add -p my-mv.session.json --type video --name V1
cli-anything-capcut track add -p my-mv.session.json --type audio --name A1
cli-anything-capcut track add -p my-mv.session.json --type text --name title

# 미디어
cli-anything-capcut image add -p my-mv.session.json -f intro.png --start 0s --duration 3s --track V1
cli-anything-capcut image add -p my-mv.session.json -f main.png --start auto --duration 5s --track V1
cli-anything-capcut audio add -p my-mv.session.json -f song.wav --start 0s --duration 8s --track A1

# 텍스트 (모든 스타일 옵션)
cli-anything-capcut text add -p my-mv.session.json -t "타이틀" \
    --track title --start 0.5s --duration 3s \
    --font roboto --size 12 --bold \
    --color "1.0,1.0,1.0" \
    --border '{"alpha": 1.0, "color": [0,0,0], "width": 0.08}' \
    --shadow '{"alpha": 0.9, "color": [0,0,0], "distance": 5, "angle": 315}' \
    --clip-settings title-top \
    --patch-style

# 효과 / 필터
cli-anything-capcut effect add -p my-mv.session.json --name vignette --start 0s --duration 8s
cli-anything-capcut effect add-filter -p my-mv.session.json --name warm --start 0s --duration 8s

# 트랜지션 / 페이드 / 애니메이션
cli-anything-capcut video add-transition -p my-mv.session.json \
    --track V1 --segment-ref op_3 --name dissolve --duration 500ms
cli-anything-capcut video add-fade -p my-mv.session.json \
    --track V1 --segment-ref op_3 --fade-in 1s --fade-out 1s
cli-anything-capcut video add-animation -p my-mv.session.json \
    --track V1 --segment-ref op_3 --role intro --name zoom_in --duration 800ms

# 키프레임 (Ken Burns 효과 등)
cli-anything-capcut keyframe add -p my-mv.session.json \
    --track V1 --segment-ref op_3 --property uniform_scale --time 0s --value 1.0
cli-anything-capcut keyframe add -p my-mv.session.json \
    --track V1 --segment-ref op_3 --property uniform_scale --time 5s --value 1.2

# 분석
cli-anything-capcut timeline -p my-mv.session.json
cli-anything-capcut stats -p my-mv.session.json
cli-anything-capcut gap-detect -p my-mv.session.json --track V1
cli-anything-capcut overlap-detect -p my-mv.session.json

# 저장
cli-anything-capcut save -p my-mv.session.json
```

## 고수준 프리셋 (원샷)

```bash
# 이미지 폴더 → 슬라이드쇼
cli-anything-capcut preset slideshow --name ss --folder ./imgs \
    --duration 3s --transition dissolve --audio bgm.wav

# 오디오 + SRT → 가사 뮤비
cli-anything-capcut preset lyric-video --name mv \
    --audio song.wav --srt lyrics.srt --background cover.png

# 기존 세션 앞뒤에 인트로/아웃트로
cli-anything-capcut preset intro-outro -p session.json \
    --intro in.png --outro out.png --transition dissolve

# PIP 오버레이
cli-anything-capcut preset pip -p session.json -f overlay.mp4 \
    --corner top-right --scale 0.35
```

## 자산 관리

```bash
# 폴더 전체 자동 분류 import
cli-anything-capcut asset bulk-import -p session.json --folder ./media

# 드래프트 참조 미디어를 한 폴더로 패킹 (배포용)
cli-anything-capcut asset relocate -p session.json -o ./packaged

# ffmpeg 변환
cli-anything-capcut asset transcode -i src.mov -o out.mp4 --crf 20

# 드래프트 커버 생성
cli-anything-capcut asset cover-from-frame -p session.json -f video.mp4 --time 2s
```

## 세션 유틸

```bash
cli-anything-capcut session compact -p session.json           # 중복 op 정리 + ID 리넘버
cli-anything-capcut session find-replace-media -p session.json \
    --pattern "D:/old" --replacement "D:/new"                  # 경로 일괄 치환
cli-anything-capcut session watch -p session.json             # 변경 감지 → 자동 save
cli-anything-capcut import-draft --from <드래프트폴더> -o out.session.json  # CapCut draft → 세션 역변환
```

## 렌더링

```bash
# CapCut GUI 자동 제어
cli-anything-capcut render -p session.json \
    --resolution 1080P --framerate 30 -o output.mp4 --save-first

# CapCut 안 켜고 ffmpeg 로 직접
cli-anything-capcut render-headless -p session.json -o output.mp4
```

## 인터랙티브 REPL

```bash
cli-anything-capcut repl
```
탭 자동완성, 히스토리(`~/.capcut_cli/repl_history`) 지원.

## 레시피 (배치 자동화)

레시피는 세션을 한 번에 구성하는 선언형 JSON:

```json
{
  "name": "music-video",
  "width": 1080, "height": 1920, "fps": 30,
  "operations": [
    {"op": "add_track", "args": {"type": "video", "name": "V1"}},
    {"op": "add_track", "args": {"type": "audio", "name": "A1"}},
    {"op": "add_image", "args": {"file": "scene1.png", "track": "V1",
                                  "start": "0s", "duration": "5s"}},
    {"op": "add_audio", "args": {"file": "song.wav", "track": "A1",
                                  "start": "0s", "duration": "30s"}}
  ]
}
```

```bash
cli-anything-capcut import-recipe -p out.session.json -f recipe.json
cli-anything-capcut export-recipe -p out.session.json -o backup.json
cli-anything-capcut validate-recipe -f recipe.json
```

## 별칭

CapCut/pyCapCut의 효과·전환·필터 enum은 한자(`暗角`, `叠化` 등). 영어 별칭으로 쓸 수 있습니다.

```bash
cli-anything-capcut alias resolve --class VideoSceneEffectType --name vignette
# → {"resolved": "暗角"}

cli-anything-capcut alias search --class FilterType -k warm
# → [{"name": "暖黄", "alias": "warm"}, ...]

cli-anything-capcut alias classes
# → ["AudioSceneEffectType", "FilterType", ..., "VideoSceneEffectType"]
```

## AI 에이전트 친화

```bash
cli-anything-capcut --json agent status -p my-mv.session.json
# → 검증 + 갭/겹침 + 다음 추천 작업
```

## 옛 버전 버그 회피 (재구현 시 고친 것들)

- **#1** `tim()`이 `"3000000"`을 0으로 반환 → `parse_time_value()` 가 흡수
- **#2/#3/#15** 별칭이 실제 enum과 어긋남 → 정확한 매핑 (`dissolve → 叠化` 등)
- **#4/#9/#14** replay 시 트랙 자동 생성 안 됨 → 모든 op_handler가 `_ensure_track()` 호출
- **#5** ffprobe 의존성 → WAV는 `wave` 모듈 fallback
- **#6/#21** clip-settings 프리셋 → `subtitle-bottom`, `pip-top-right` 등 8개 내장
- **#10/#22** 파이핑 시 SIGPIPE 손실 → 세션은 stderr 출력에 의존하지 않음
- **#17~#20** `text add --font/--border/--shadow/--color` 미반영 → `--patch-style` 또는 `text style-patch` 로 save 후 draft_content.json 직접 패치
- **draft_meta_info.json 누락** → CapCut 목록에 안 뜨던 문제 → `DraftFolder.create_draft` 항상 통과

## 프로젝트 구조

```
cli_anything/capcut/
├── capcut_cli.py            # Click 진입점, 그룹 등록
├── commands/                # 서브커맨드 그룹
│   ├── helpers.py           # 출력/세션로드/JSON옵션/색/clip 프리셋
│   ├── project.py           # project new/info/status/clone
│   ├── track.py             # track add
│   ├── media.py             # video/image/audio add + add-fade/transition/animation
│   ├── text.py              # text add (스타일/위치) + animation + style-patch + srt import
│   ├── style.py             # 내장 텍스트/비디오/오디오 스타일 프리셋
│   ├── sticker.py           # sticker add
│   ├── effect.py            # effect add / add-filter
│   ├── mask.py              # 마스크 (원형/사각/하트 등)
│   ├── keyframe.py          # keyframe add (alpha/scale/transform/...)
│   ├── color.py             # color adjust / curves / hsl
│   ├── asset.py             # bulk-import / relocate / transcode / cover
│   ├── preset.py            # slideshow / lyric-video / intro-outro / pip / hook / kenburns
│   ├── plan.py              # 자연어 → 레시피 (Claude API)
│   ├── preview.py           # 트랙 구조를 HTML 간트차트로
│   ├── render.py            # CapCut GUI 자동 제어 렌더
│   ├── render_headless.py   # ffmpeg 직접 렌더 (CapCut 없이)
│   ├── import_draft.py      # CapCut draft → 분석용 세션 역변환
│   ├── review.py            # 참조 무결성 검사
│   ├── session_utils.py     # compact / find-replace-media / watch / merge
│   ├── alias_cmds.py        # alias resolve/list/search/classes
│   ├── analysis.py          # timeline/stats/gap/overlap/segments-at/undo/validate/history
│   ├── recipe_cmds.py       # import/export/validate-recipe + edit/delete/reorder/batch + merge/diff
│   └── agent_cmds.py        # agent status/explain-error
├── core/
│   ├── session.py           # 이벤트 소스 Session 클래스 (30+ 메서드)
│   ├── op_handlers.py       # op → ScriptFile 변환 디스패처
│   ├── op_registry.py       # op 분류 (CREATION/MODIFIER/STRUCTURE/POSTPROCESS)
│   ├── alias_map.py         # 영→한자 별칭 + 폰트 해석 + fuzzy search
│   ├── style_registry.py    # 내장 스타일 정의
│   ├── media_staging.py     # 한글/비ASCII 경로 스테이징
│   ├── auto_fix.py          # 실패 op 격리 후 재replay
│   ├── time_utils.py        # parse_time_value (버그 #1 수정), 미디어 duration
│   ├── segment_utils.py     # segment_ref 해석
│   ├── recipe.py            # 레시피 로드/검증/적용
│   └── postprocess.py       # save 후 draft_content.json 패치 (버그 #17~#21)
├── utils/
│   ├── capcut_backend.py    # 드래프트 폴더 자동 감지
│   └── repl_skin.py         # prompt-toolkit REPL
└── tests/                   # 24개 파일 / 398 tests
    ├── test_core.py          # 유닛 테스트
    ├── test_e2e_op_matrix.py # CLI -> replay -> save 전 구간 검증
    ├── test_import_draft.py  # CapCut draft 역변환
    ├── test_font_resolution.py # 폰트 별칭 해석
    └── ...                   # 기능별 테스트
```

`scripts/alias_audit.py` 는 별칭이 설치된 pycapcut enum 과 어긋나지 않는지 감사하고,
`scripts/scan_private.py` 는 공개 전 개인정보 스캔 게이트입니다(CI 에 배선됨).

## Claude Code 스킬 (선택)

이 repo의 `claude-skill/` 폴더를 `~/.claude/skills/capcut-cli/`로 복사하면 Claude Code 안에서 자연어로 이 CLI를 사용할 수 있습니다.

```bash
cp -r claude-skill ~/.claude/skills/capcut-cli
```

## 라이선스

MIT. `pyCapCut` (업스트림)은 별도 라이선스를 따릅니다.
