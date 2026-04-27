---
name: capcut-cli
description: |
  Guide for using the cli-anything-capcut CLI (v0.4.x) to programmatically build, validate, render,
  and refine CapCut/JianYing video drafts. Use this skill whenever the user wants to: scaffold a
  CapCut project via CLI, write or import a recipe JSON, troubleshoot CapCut CLI errors, run a
  preview/review/render pipeline, generate a draft from natural language, or automate any video
  editing workflow with cli-anything-capcut. Trigger when user mentions 'capcut cli',
  'cli-anything-capcut', 'capcut recipe', 'capcut draft', 'CapCut 프로젝트', 'CapCut 렌더',
  'draft_content.json', 'pyCapCut', 'pycapcut', 'capcut staging', 'capcut preview', 'capcut review',
  'capcut plan', 'capcut preset slideshow / lyric-video / intro-outro / pip', or 'capcut style preset'.
  Korean triggers: '후처리해줘', '캡컷에 넣어줘', '영상 편집해줘', '캡컷 드래프트', '캡컷 프로젝트',
  '필터 적용', '이펙트 추가', '자막 넣어줘', '색보정', '트랜지션', 'SRT 임포트', '슬라이드쇼',
  '가사 영상', 'BGM 깔아줘', 'CapCut 렌더', 'MP4 뽑아줘'.
  Even when the user says "make a CapCut project" or "edit this video", use this skill to ensure
  v0.4.x CLI patterns are followed (commands, role-based animations, normalized -1..+1 color, staging).
---

> **CLI version: 0.4.x** (`cli-anything-capcut --version`). v0.3 docs that mention `add-with-transition`,
> `add-with-animation`, `--category` for animations, `--type` for transitions, 0–100 color values,
> `recipe-validate`/`recipe-apply`/`save --register`/`doctor`/`alias search-all` are **outdated** —
> see the rename table below.

## 🎬 Brief 파악 — 3페이즈 16개 질문 (자동화 파이프라인 전용)

capcut-cli는 **자동화**가 목적입니다. 한 번 잘못된 브리프로 파이프라인이 돌면 15~30분짜리
렌더를 통째로 다시 해야 합니다. 그래서 브리프 단계에 시간을 투자해 **첫 시도에 맞게** 가는
것이 훨씬 빠릅니다.

### 운영 원칙

1. **페이즈 단위로 묶어 묻기** — 한 번에 3페이즈 모두 쏟아붓지 말고, 페이즈마다 답 받고
   확인한 뒤 다음으로. 각 페이즈 끝에 **요약+승인** 체크포인트 1회씩 (총 3회).
2. **이미 알려준 정보는 다시 안 묻기** — "확인: X로 이해했어요" 로 대체. 중복 질문은 짜증 유발.
3. **"알아서 해줘" 선언 시** → 해당 페이즈 이후는 디폴트로 자동 진행 + 디폴트 값 **명시**.
4. **질문 건너뛰기 기준**: Phase 1의 6가지가 모두 요청에 담겨 있으면 Phase 1 스킵. 각 페이즈
   마찬가지.
5. **BOLD 방향성** (frontend-design 차용): 톤·스타일 질문은 **2~3지선다 뚜렷한 콘셉트**로
   제시. "그냥 예쁘게" 답 대신 CINEMATIC/VIVID/MINIMAL 중 하나를 고르게 해 밋밋한 평균 회피.

### Phase 1 — 기획 (필수 6개, 한 메시지로)

의사결정 뼈대. 답 없으면 진행 불가.

```
영상 자동화 돌리기 전에 기획 6개만 확인할게요 (한 번에 답주시면 페이즈 2로 넘어갑니다):

1) **한 줄 요약**: 어떤 영상인가요? 용도+내용을 한 문장으로.
   예) "신규 출시한 제품을 소개하는 인스타 릴스 30초"

2) **시청자·목적**: 누가 보고, 보고 난 뒤 뭘 하길 원해요?
   예) "20~30대 여성, 예약 페이지 방문 유도"

3) **플랫폼·비율·길이**: 어디 올릴지 + 대략 길이
   (쇼츠=9:16/15~60s, 유튜브 본편=16:9, 릴스=9:16, 강의=16:9, 인스타 피드=1:1)

4) **소재 파일**: 가진 것들의 경로·종류·대략 개수
   예) "D:/촬영/room1.mp4, room2.mp4 + D:/bgm.mp3 + D:/logo.png"
   (없으면 "없음" — 이 경우 pexels-media 스킬로 전환 or 사용자 준비 대기)

5) **참고·레퍼런스**: 비슷한 영상 URL 1개 또는 무드 키워드 자유 서술
   예) "이 릴스처럼 https://... / '노을 감성'"

6) **전체 톤** (BOLD 3지선다 — 평균값 금지):
   A. **CINEMATIC** — film 필터, 어둡고 대비 강함, 느린 줌, subtitle-bottom 자막
   B. **VIVID / SNS POP** — vivid 필터, 밝고 채도 높음, 빠른 컷, title-center 큰 글씨
   C. **MINIMAL / CLEAN** — 필터 없음, 자연 색감, 차분한 페이드, 미니멀 자막
```

**Phase 1 체크포인트**: 답 받으면 한 문단으로 요약해서 "이렇게 이해했어요, 맞죠?" 확인 →
승인 후 Phase 2로. 톤(6번)이 답 안 왔으면 **반드시** 재질문 (디폴트 금지).

### Phase 2 — 구조·상세 (타입별 6개, 한 메시지로)

Phase 1에서 **영상 타입**을 감지(쇼츠·릴스/슬라이드쇼/가사/강의/홍보/브이로그/인터뷰) →
해당 타입 전용 6개 질문 세트를 `references/brief-questions.md`에서 불러와 한 번에 물으세요.

**공통 6축** (타입별로 구체 문구만 달라짐):

| # | 축 | 예시 (쇼츠) | CLI 결정 |
|---|----|-----------|---------|
| 7 | **훅·오프닝** | 첫 3초 훅 텍스트/이미지? | `text add` + `add-animation --role intro` |
| 8 | **스토리 흐름** | 컷 순서 + 각 구간 역할 | `video add` × N + `start` 배치 |
| 9 | **자막·텍스트** | SRT 있음? 강조 문구만? | `srt import --style youtube-subtitle` 또는 `text add` |
| 10 | **오디오** | 나레이션? BGM 분위기·볼륨? | `audio add --track A1/A2 --volume` + `audio add-fade` |
| 11 | **컷·트랜지션·모션** | 컷 속도 + 전환 종류 + 키프레임 | `video add-transition --name`, `keyframe add` |
| 12 | **CTA·엔딩** | 마지막 문구? 아웃트로 로고? | 마지막 `text add` + `image add` + `fade_out` |

> 타입별 전문은 `references/brief-questions.md` 참조 (쇼츠·슬라이드쇼·가사·강의·홍보·브이로그·인터뷰 7종).

**Phase 2 체크포인트**: 6개 답으로 **타임라인 초안**을 구간별 표로 요약 → 승인.

```
타임라인 초안입니다:
| 시간 | 트랙 | 내용 | 효과 |
|------|------|------|------|
| 0~3s | V1+T1 | 훅 텍스트 "이거 모르면..." | fade_in + vivid 필터 |
| 3~15s | V1 | room1.mp4 | dissolve → room2.mp4 |
| ...

이대로 가도 괜찮으세요?
```

### Phase 3 — 출력·디테일 (선택 4개)

"알아서 해줘" 답하면 디폴트로 스킵 가능. 세부 조정 원하면 물어보기.

```
마지막 4개만 확인하면 렌더까지 자동으로 돌립니다. 세부 조정 없으면 "디폴트"라고만 답주세요:

13) **필터·색보정 강도**: 자동(톤에 맞춤) / 사용자 지정 수치
    디폴트 — CINEMATIC: `cinematic` 0.4 + brightness -0.05 + contrast 0.15
            VIVID:     `vivid` 0.5 + saturation 0.15
            MINIMAL:   필터 없음 + 기본 색감

14) **인트로·아웃트로 애니메이션 강도**
    디폴트 — 쇼츠/릴스: intro `zoom_in` + outro `fade_out`
            강의:    없음
            홍보:    intro `fade_in` + outro `fade_out` + CTA `bounce_in`

15) **렌더 방식**:
    A. `render` (CapCut GUI 경유) — 정확함, 모든 필터 반영, 느림, GUI 필요
    B. `render-headless` (ffmpeg 직접) — 빠름, 일부 필터/효과 미지원, 무인 서버 OK
    디폴트 — 프로덕션/최종: A / 프리뷰·반복 테스트: B

16) **출력**: 해상도(720P/1080P/2K/4K) + 저장 경로·파일명
    디폴트 — 1080P, 프로젝트 폴더에 `<name>_<timestamp>.mp4`
```

**Phase 3 체크포인트**: 최종 파이프라인 전체를 bash 블록으로 출력 → 승인 후 실행.

### 질문 건너뛰기 규칙 (페이즈별)

| 상황 | 스킵 대상 |
|------|----------|
| 요청에 Phase 1의 6축 모두 언급 | Phase 1 전체 스킵, 확인만 |
| Phase 1 답변이 타입까지 명확 | Phase 2는 답 안 온 6축만 부분 질문 |
| "빨리", "알아서" 선언 | Phase 3 전체 스킵, 디폴트 선언하고 실행 |
| 완전 자율 위임 ("그냥 만들어줘") | `cli-anything-capcut plan "..." --assets-dir ...`로 위임 + 결과 먼저 보여드리고 수정 루프 |

### 요청 → Phase 매핑 (자동 결정 테이블)

| 요청 예시 | 판정 | 행동 |
|----------|------|------|
| "영상 하나 만들어줘" | Phase 1 전체 필요 | Phase 1 6개 질문 |
| "제품 릴스 30초 만들어줘" | 1·3번만 답 있음 | Phase 1의 2,4,5,6번 질문 |
| "D:/사진/ 100장으로 시네마틱 슬라이드쇼 만들어줘" | 1·3·4·6번 답 있음 | Phase 1의 2,5만 물음 → Phase 2(슬라이드쇼) |
| "쇼츠 만들어줘, 소재 D:/촬영/, 시네마틱으로" | Phase 1 대부분 커버 → Phase 2로 | Phase 2 6개 |
| "알아서 해줘, 빨리" | 전부 위임 | `plan` 명령으로 위임, 초안 먼저 보여줌 |
| "이 JSON으로 바로 렌더" | 이미 recipe 있음 | Brief 스킵, `import-recipe` 바로 |

### 최종 요약 포맷 (Phase 3 승인 직전)

```markdown
## 📋 최종 브리프 확인

**기획** (Phase 1)
- 내용: [릴스 30초 / 제품 소개]
- 타겟: [20~30대 여성 / 예약 유도]
- 플랫폼: [인스타 릴스 9:16 / 30초]
- 소재: [room1.mp4, room2.mp4, bgm.mp3, logo.png]
- 레퍼런스: [xxx.url / "노을 감성"]
- 톤: **CINEMATIC**

**구조** (Phase 2)
- 훅: 텍스트 "이번 주말, 여기" 0~3s
- 흐름: room1(0-15s) → dissolve → room2(15-27s) → 로고(27-30s)
- 자막: 제공된 SRT, `youtube-subtitle` 스타일
- 오디오: bgm A1 volume 0.3, fade_in 1s / fade_out 2s
- 컷·모션: 느린 줌 1.0→1.05, dissolve 0.7s
- CTA: "예약하기 링크" 27~30s title-center + bounce_in

**출력** (Phase 3)
- 필터: `cinematic` 0.4 + brightness -0.05 + contrast 0.15
- 애니메이션: intro fade_in, outro fade_out
- 렌더: `render` (GUI, 정확)
- 해상도·파일: 1080P → `D:/out/reel_<timestamp>.mp4`

**실행할 파이프라인** (16개 명령):
```bash
cli-anything-capcut project new -n "my_reel" --preset portrait
cli-anything-capcut video add ...
...
cli-anything-capcut render -p my_reel.session.json -o D:/out/reel.mp4 --resolution 1080P --save-first
```

이대로 진행할까요?
```

이 단계의 승인을 받은 뒤에만 실제 실행. Phase 3까지 다 지나면 **오해로 렌더 재실행하는
일은 거의 사라집니다** — 이게 질문 16개를 감수하는 이유입니다.

---

## ⚡ Quick Start (90% of cases)

> **전제조건**: `cli-anything-capcut` CLI가 PATH에 있어야 합니다. 미설치/문제 시:
> `cli-anything-capcut diagnose` (예전 `doctor`) 로 환경 점검. 기본 설치는
> `pip install -e ./agent-harness` (pyCapCut 리포 안에서).

```bash
# 0. 환경 점검 (한 번만)
cli-anything-capcut diagnose

# 1. 프로젝트 생성 (세로 쇼츠면 --preset portrait)
cli-anything-capcut project new -n "my_video" --preset landscape
# → my_video.session.json 생성

# 2. 비디오 추가 (한글/공백 경로 OK — staging이 자동 처리)
cli-anything-capcut video add -p my_video.session.json \
  -f "D:/내 영상/촬영본.mp4" -s 0s -d auto --track V1
# → op_0 반환

# 3. SRT 자막 (스타일 프리셋 사용 — 'youtube-subtitle' 등 내장 5종)
cli-anything-capcut srt import -p my_video.session.json \
  -f "D:/subs.srt" --track T1 --style youtube-subtitle

# 4. 필터 + 이펙트 (트랙 자동 관리)
cli-anything-capcut effect add-filter -p my_video.session.json \
  --name cinematic --intensity 0.4
cli-anything-capcut effect add -p my_video.session.json \
  --name vignette -s 0s -d auto

# 5. 비디오 인트로/아웃트로 애니메이션 (--role 주의: --category 아님)
cli-anything-capcut video add-animation -p my_video.session.json \
  --track V1 --segment-ref op_0 --role intro --name fade_in
cli-anything-capcut video add-animation -p my_video.session.json \
  --track V1 --segment-ref op_0 --role outro --name fade_out

# 6. BGM (--volume 0.0~1.0)
cli-anything-capcut audio add -p my_video.session.json \
  -f "D:/bgm.mp3" -s 0s -d auto --track A1 --volume 0.3

# 7. 검증 → 미리보기 → 저장 → 렌더 (전체 파이프라인)
cli-anything-capcut validate -p my_video.session.json     # replay dry-run
cli-anything-capcut review   -p my_video.session.json     # 자동 QA (갭/겹침/볼륨/자막속도/렌더호환)
cli-anything-capcut preview  -p my_video.session.json --open  # HTML 간트차트 (옵션: --thumbs)
cli-anything-capcut save     -p my_video.session.json     # CapCut 드래프트 디스크 저장
cli-anything-capcut render   -p my_video.session.json -o "D:/out.mp4" --resolution 1080P --save-first
# CapCut GUI 없이 빠르게: render-headless (V1 concat + V2+ overlay + xfade 지원)
```

### 자막 없는 영상 (변형)

```bash
cli-anything-capcut project new -n "visual_only" --preset landscape
cli-anything-capcut video add -p visual_only.session.json -f "D:/clip.mp4" -s 0s -d auto --track V1
cli-anything-capcut audio add -p visual_only.session.json -f "D:/bgm.mp3" -s 0s -d auto --track A1 --volume 0.5
cli-anything-capcut audio add-fade -p visual_only.session.json --track A1 --segment-ref op_1 --fade-in 1s --fade-out 2s
cli-anything-capcut effect add-filter -p visual_only.session.json --name cinematic --intensity 0.4
cli-anything-capcut keyframe add -p visual_only.session.json \
  --track V1 --segment-ref op_0 --property uniform_scale --time 0s --value 1.0
cli-anything-capcut keyframe add -p visual_only.session.json \
  --track V1 --segment-ref op_0 --property uniform_scale --time 5s --value 1.05
cli-anything-capcut review  -p visual_only.session.json
cli-anything-capcut save    -p visual_only.session.json
```

---

## 🚀 한 방 프리셋 (project new + ops + save 한 번에)

복잡한 워크플로우를 매번 재발명하지 않고, 자주 쓰는 형태는 단일 명령으로 끝내세요.

| 작업 | 명령 |
|------|------|
| 이미지 폴더 → 슬라이드쇼 | `preset slideshow -n NAME -f IMAGE_DIR --duration 3s --transition dissolve --audio "D:/bgm.mp3" --preset-size 9x16` |
| 오디오 + SRT → 가사 영상 | `preset lyric-video -n NAME -a song.mp3 -s lyrics.srt -b bg.jpg --position subtitle-bottom` |
| 기존 세션에 인트로/아웃트로 붙이기 | `preset intro-outro -p sess.json --intro intro.png --outro outro.png --transition dissolve` |
| 메인 영상 위 PIP 오버레이 | `preset pip -p sess.json -f overlay.mp4 --corner top-right --scale 0.35` |
| 쇼츠/릴스 첫 3초 자동 훅 (shake+zoom+flash+bold text) | `preset hook -p sess.json -t "이거 모르면 가격 30% 더 낸다" --category pattern-interrupt --duration 3s` |
| 이미지 N장 → 켄번스 슬라이드쇼 (줌/팬 키프레임 자동) | `preset kenburns -p sess.json --folder D:/images --duration-each 4s --pattern alternating --intensity 0.2` |

> **언제 쓰나**: 사용자가 "이미지 폴더로 슬라이드쇼", "노래에 가사 자막", "인트로/아웃트로 붙여줘",
> "PIP 합성", "쇼츠 첫 3초 임팩트", "제품 사진 슬라이드쇼" 같은 정형 작업을 요청할 때.
> CLI 호출 5~10개를 1개로 줄임.

### `preset hook` 카테고리 (10종 — content-formulas.md 섹션 1.2)

| 카테고리 | 연출 특징 | 추천 상황 |
|---------|----------|----------|
| `curiosity` | flash 강함 + zoom 1.10 | "여러분 이거 알고 계셨어요?" |
| `shock` | flash 강 + shake 강 (0.7) | "사기당했어요" |
| `pattern-interrupt` | shake 최강 (0.9) + color invert flash | 기본값. 가장 범용 |
| `number` | 숫자 카운트다운 톤 (shake 약) | "3가지 이유" |
| `promise` | 부드러운 zoom | "5초 안에 알려드릴게요" |
| `contrarian` | 느린 zoom + 진지 (shake 약) | "사람들이 틀린 이유" |
| `fear` | 낮은 shake + 짧은 flash | "이거 모르면 큰일" |
| `question` | 큰 텍스트 중앙 | "왜 그럴까요?" |
| `authority` | 부드러운 zoom, shake 없음 | 전문가 톤 |
| `pov` | 미니멀, shake 약 | 1인칭 브이로그 |

### `preset kenburns` 패턴 (6종)

| 패턴 | 동작 |
|------|------|
| `alternating` | 짝수 index 줌인(1.0→1+intensity), 홀수 index 줌아웃 (기본값, 가장 자연스러움) |
| `random` | 매 이미지마다 줌인/줌아웃/pan-lr/pan-tb 중 랜덤 (재현하려면 `--seed INT`) |
| `zoom-in` | 전체 줌인만 |
| `zoom-out` | 전체 줌아웃만 |
| `pan-lr` | scale 고정 1.1, 좌 → 우 팬 (transform_x -0.05 → +0.05) |
| `pan-tb` | scale 고정 1.1, 상 → 하 팬 (transform_y -0.05 → +0.05) |

> **intensity 권장**: 0.1(서서히) / 0.2(기본) / 0.3(강함). 0.3 넘으면 흔들림 체감.
> **headless 렌더 호환**: `render-headless` 가 `uniform_scale` / `transform_x/y` 키프레임 선형 보간을 지원하므로 GUI 없이도 결과물 동일.

---

## 🤖 자연어 → 레시피 (plan / plan-refine)

자연어 요청을 그대로 레시피 JSON으로 변환할 수 있습니다 (Claude API 내장).

```bash
# 1. 자연어 지시 → 레시피
cli-anything-capcut plan "30초 SaaS 제품 소개. 로고 3초 fade_in → 데모 영상 20초 + cinematic 필터 → CTA 텍스트 5초. BGM 깔고." \
  --width 1920 --height 1080 --duration 30s --assets-dir D:/myassets \
  -o demo.recipe.json

# 2. 검증 후 적용
cli-anything-capcut validate-recipe -f demo.recipe.json
cli-anything-capcut import-recipe -p demo.session.json -f demo.recipe.json

# 3. 레시피 수정
cli-anything-capcut plan-refine -i demo.recipe.json -o demo.v2.recipe.json \
  --feedback "CTA 폰트 더 크게, 배경음악 볼륨 0.3으로 낮춰"
```

> **언제 쓰나**: 사용자가 명령어 시퀀스를 직접 짜기 싫어할 때, 또는 요청이 추상적("시네마틱하게",
> "유튜브 쇼츠 느낌으로")일 때. `--assets-dir`로 사용 가능한 파일을 한정하면 환각이 줄어듦.

---

## 핵심 규칙 (v0.4.x)

| 규칙 | 설명 |
|------|------|
| 한글/공백 경로 OK | `staging`이 자동으로 ASCII 캐시 폴더로 복사. 영문 경로 강제 불필요 |
| 시간 = 문자열 | `"3s"`, `"500ms"`, `"auto"`, `"+2s"`, `"1m30s"`, `"3000000"`(us). 베어 `"3.5"`=3.5초 |
| `--segment-ref op_N` | sub-op는 creation op 반환 ID로 대상 지정 (`--segment` 위치기반은 비추) |
| 색보정 -1.0~+1.0 | `color adjust --brightness 0.1` (예전 0~100 아님). temperature도 -1(cool)~+1(warm) |
| 필터 intensity 0.0~1.0 | `effect add-filter --intensity 0.4` (예전 40 아님) |
| 애니메이션은 `--role` | `--role intro|outro|loop` (text) / `intro|outro|group` (video). 예전 `--category` 아님 |
| 트랜지션은 `--name` | `video add-transition --name dissolve` (예전 `--type` 아님) |
| 이미지 duration 명시 | `--duration auto` 불가. `-d 3s` 등 명시 |
| 텍스트 fade 금지 | 텍스트엔 `add-fade` 없음. `keyframe add --property alpha` 사용 |
| 트랙 자동 생성 | `--track V1`/`T1`/`A1` 지정 시 자동. `track add` 불필요 |
| 저장 전 review | `validate` (구조) → `review` (품질) → `save` 순서 |
| `--color` 자동범위 | 0–255 또는 0.0–1.0 자동 감지. `[1.0,1.0,1.0]` 또는 `255,255,255` |

## ❌ Anti-patterns

| 하지 마세요 | 대신 |
|------------|------|
| `draft_content.json` 직접 수정 | CLI 사용 (`project new` → ops → `save`) |
| CapCut MCP 도구 호출 | CLI (해당 MCP 없음) |
| 한글 경로 회피용 수동 복사 | `staging`이 자동 처리. 그냥 그대로 사용 |
| `--category intro` (애니메이션) | `--role intro` (v0.4 변경) |
| `--type dissolve` (트랜지션) | `--name dissolve` (v0.4 변경) |
| `--brightness 10` (0~100 가정) | `--brightness 0.1` (-1.0~+1.0) |
| `--intensity 40` (필터) | `--intensity 0.4` (0~1.0) |
| `add-with-transition` / `add-with-animation` | v0.4에서 제거됨. 분리해서 호출 |
| `video chroma-key` / `video reverse` / `video freeze-frame` / `video blend-mode` | **v0.4.3에서 복원됨** — draft_content.json 패치 방식. `--segment-ref op_N` 형식 사용 |
| `color curves` / `color hsl` / `video lut` / `video speed-curve` | **v0.4.4에서 복원됨** — draft_content.json 패치 방식. 일부 JSON 키 이름은 GUI 검증 권장 |
| `--segment 0` (위치 기반) | `--segment-ref op_0` (ID 기반) |
| `alias search-all` | `alias search -k 키워드` |
| 텍스트에 `add-fade` | `keyframe add --property alpha --time 0s --value 0.0` |

## 🔄 v0.3 → v0.4 명칭 변경표

| v0.3 (구) | v0.4 (현) |
|-----------|-----------|
| `doctor` | `diagnose` |
| `validate-full` | `validate` (+ `review` 별도) |
| `recipe-validate` | `validate-recipe` |
| `recipe-apply` | `import-recipe` |
| `save --register` | `save` (디폴트가 등록) |
| `save-skip-errors` | `save --skip-errors` 또는 `save --auto-fix` |
| `alias search-all` | `alias search -k <kw>` |
| `video add-filter` | `effect add-filter` |
| `video add-mask` | `mask add` |
| `video add-background` | `background add` |
| `text/image/video add-with-*` | 제거됨 — 분리 호출 |
| `--category intro` (animation) | `--role intro` |
| `--type dissolve` (transition) | `--name dissolve` |

---

## 🔍 Quick Lookup (하고 싶은 것 → 명령어)

| 하고 싶은 것 | 명령어 |
|-------------|--------|
| 환경 점검 | `diagnose` |
| 프로젝트 생성 | `project new -n NAME --preset landscape` (또는 portrait/square/4k/9x16/16x9/1x1) |
| 프로젝트 상태 (검증+갭+겹침) | `project status -p p.session.json` |
| 비디오 추가 | `video add -f FILE -s 0s -d auto --track V1` |
| 이미지 추가 | `image add -f FILE -s auto -d 3s --track V1` |
| 오디오 추가 | `audio add -f FILE -s 0s -d auto --track A1 --volume 0.5` |
| 텍스트 추가 | `text add -t "TEXT" -s 0s -d 3s --font arial --size 6.0 --color 255,255,255 --clip-settings subtitle-bottom` |
| 텍스트 (저장된 스타일) | `text add -t "TEXT" -s 0s -d 3s --style youtube-subtitle` |
| 텍스트 (위치 직접) | `text add -t "..." --position-x 0 --position-y -0.7` |
| SRT 자막 | `srt import -f FILE --track T1 --style youtube-subtitle` |
| AI 자동 자막 (v0.5.1+) | `text auto-srt --audio input.mp4 --model small --language ko --initial-prompt "도메인 전문 용어 예시"` |
| 필터 (전역) | `effect add-filter --name cinematic --intensity 0.4` |
| 이펙트 (전역) | `effect add --name vignette -s 0s -d auto` |
| 트랜지션 | `video add-transition --track V1 --segment-ref op_0 --name dissolve --duration 0.7s` |
| 비디오 인트로 | `video add-animation --track V1 --segment-ref op_0 --role intro --name fade_in` |
| 비디오 아웃트로 | `video add-animation --track V1 --segment-ref op_0 --role outro --name fade_out` |
| 텍스트 애니메이션 | `text add-animation --track T1 --segment-ref op_5 --role intro --name typewriter` |
| 키프레임 (줌) | `keyframe add --track V1 --segment-ref op_0 --property uniform_scale --time 0s --value 1.0` |
| 키프레임 (알파/페이드) | `keyframe add --track T1 --segment-ref op_5 --property alpha --time 0s --value 0.0` |
| 색보정 | `color adjust --track V1 --segment-ref op_0 --brightness 0.05 --contrast 0.1 --saturation -0.1` |
| 색상 휠 | `color wheels --track V1 --segment-ref op_0 --shadow-hue 220 --shadow-sat 0.15 --highlight-hue 40 --highlight-sat 0.1` |
| 비디오 페이드 | `video add-fade --track V1 --segment-ref op_0 --fade-in 0.5s --fade-out 0.5s` |
| 오디오 페이드 | `audio add-fade --track A1 --segment-ref op_1 --fade-in 1s --fade-out 2s` |
| 오디오 효과 | `audio add-effect --track A1 --segment-ref op_1 --name noise-reduction` |
| 마스크 | `mask add --track V1 --segment-ref op_0 --type circle --size 0.5 --feather 20` |
| 배경 채우기 (블러) | `background add --track V1 --segment-ref op_0 --mode blur --blur 0.75` |
| 배경 채우기 (단색) | `background add --track V1 --segment-ref op_0 --mode color --color "#000000"` |
| 스티커 | `sticker add -f sticker.png -s 0s -d 3s --track V2` |
| 텍스트 스타일 패치 | `text style-patch --track T1 --segment-ref op_5 --font ... --border ...` (버그 우회) |
| 역재생 (v0.4.3+) | `video reverse --track V1 --segment-ref op_0` |
| 프리즈 프레임 (v0.4.3+) | `video freeze-frame --track V1 --segment-ref op_0 [--duration 2s]` |
| 블렌드 모드 (v0.4.3+) | `video blend-mode --track V1 --segment-ref op_0 --mode multiply` |
| 크로마 키/그린스크린 (v0.4.3+) | `video chroma-key --track V1 --segment-ref op_0 --color "#00FF00" --intensity 0.5` |
| LUT 필터 (v0.4.4+) | `video lut --track V1 --segment-ref op_0 --file "lut.cube" --intensity 0.8` |
| 속도 커브 (v0.4.4+) | `video speed-curve --track V1 --segment-ref op_0 --points "0,1.0;0.5,2.0;1.0,1.0"` |
| 컬러 커브 (v0.4.4+) | `color curves --track V1 --segment-ref op_0 --rgb "0,0;0.5,0.7;1,1"` |
| HSL 채널별 (v0.4.4+) | `color hsl --track V1 --segment-ref op_0 --target red --hue 10 --saturation -20 --lightness 5` |
| 쇼츠 훅 자동 (0~3s) | `preset hook -p sess.json -t "..." --category pattern-interrupt` |
| 켄번스 자동 (이미지 슬라이드쇼) | `preset kenburns -p sess.json --folder DIR --duration-each 4s --pattern alternating` |
| 검증 (구조) | `validate -p p.session.json` |
| 검증 (품질 QA) | `review -p p.session.json` (또는 `--severity warning`, `--only volume,gaps`) |
| 미리보기 | `preview -p p.session.json --open` (또는 `--thumbs` 로 첫 프레임 인라인) |
| 저장 | `save -p p.session.json` (실패 시 `--auto-fix --max-attempts 3`) |
| 렌더 (CapCut GUI) | `render -p p.session.json -o out.mp4 --resolution 1080P --save-first` |
| 렌더 (ffmpeg 직접) | `render-headless -p p.session.json -o out.mp4 --crf 20 --preset medium` |
| Undo | `undo -p p.session.json` (또는 `-n 3`, `--type add_filter`) |
| 히스토리 | `history -p p.session.json` (또는 `--filter add_video`) |
| ASCII 타임라인 | `timeline -p p.session.json` |
| 통계 | `stats -p p.session.json` |
| 특정 시각 활성 세그먼트 | `segments-at -p p.session.json --time 5s` |
| 갭/겹침 검출 | `gap-detect -p p.session.json` / `overlap-detect -p p.session.json` |
| 에이전트용 상태+다음 | `agent status -p p.session.json` |
| 에러 해석 | `agent explain-error -e "에러 메시지"` |
| Alias 검색 | `alias search -k "키워드"` (또는 `alias list --class TransitionType`) |
| 미디어 정보 | `media-info FILE` |
| 폴더 → 일괄 import | `asset bulk-import -p p.session.json -f /folder` |
| 미디어 한 폴더로 묶기 | `asset relocate -p p.session.json -o /collected --update-session` |
| 트랜스코드 | `asset transcode -i in.mov -o out.mp4 --crf 22` |
| 세션 비교 | `diff-session -p A.session.json --other B.session.json` |
| 세션 합치기 | `merge-session -p A.session.json --other B.session.json --offset auto` |
| 미디어 경로 일괄 치환 | `session find-replace-media -p p.session.json --pattern OLD --replacement NEW --dry-run` |
| 세션 압축 | `session compact -p p.session.json --dry-run` |
| 세션 자동 save | `session watch -p p.session.json --interval 2` |
| 레시피 export | `export-recipe -p p.session.json -o r.json` |
| 스크립트 export (재현용) | `export-script -p p.session.json -o repro.sh` |
| 스타일 프리셋 목록 | `style list` (또는 `--category text`) |
| 스타일 프리셋 저장 | `style save MYNAME --category text --font arial --size 6 --color 255,255,255 --border '...'` |
| 스타일 프리셋 적용 | `style apply-video --track V1 --segment-ref op_0 --style cinematic-warm` |
| Staging 캐시 확인 | `staging list` / `staging stats` / `staging clear` |

> 모든 sub-op엔 `-p session.json` 필수. 전역 `--json` 플래그로 기계 파싱 가능 출력.

## 트랙 & 시간

**트랙 컨벤션:**
| Type | Name | Layer | 용도 |
|------|------|-------|------|
| Video | V1, V2 | V2가 V1 위 | 메인, PiP, 오버레이 |
| Audio | A1, A2, A3 | 믹싱 | A1=나레이션, A2=BGM, A3=SFX |
| Text | T1, T2 | T2가 T1 위 | T1=자막, T2=타이틀 |
| Effect/Filter | (자동) | — | `effect add` / `effect add-filter` 호출 시 자동 트랙 |

**시간 형식:** `3s`, `1.5s`, `1m30s`, `500ms`, `auto`, `+2s`, `3000000`(us). 베어 `"3.5"` = 3.5초.

## 워크플로우 패턴 (CRITICAL)

전체 파이프라인은 **검증 → 미리보기 → 저장 → 렌더** 4단계입니다. 각 단계는 다른 일을 하므로 건너뛰지 마세요.

```
[ops 추가]
   │
   ├─ validate          # replay dry-run — op 간 의존/시간 충돌 체크
   ├─ review            # 품질 QA — 갭/겹침/볼륨밸런스/자막속도/해상도/렌더호환성
   ├─ preview --open    # 사람 검증 — HTML 간트차트로 트랙 구조 시각화
   ├─ save              # 디스크 기록 — CapCut 드래프트 폴더에 commit
   └─ render            # MP4 추출 — CapCut GUI(--save-first 권장) 또는 render-headless
```

> **review에서 warning 이상이면 멈추기**: `review --severity warning --fail-on-warning` 으로 CI에서도
> 안전. `--only volume,subtitles`로 특정 체크만도 가능.

## Combo / Recipe / Batch

v0.4에선 옛 `add-with-*` combo 명령이 사라졌습니다. 대신 다음 3가지를 상황에 맞게 사용:

| 방법 | 장점 | 단점 | 사용 시점 |
|------|------|------|----------|
| 개별 CLI 명령 | undo로 즉시 롤백 가능 | 호출 횟수 많음 | 탐색적/디버깅 |
| `batch -f ops.json` | 한 번에 여러 op, 빠름 | 프로젝트 생성 미포함 | 기존 세션에 일괄 추가 |
| `import-recipe -f r.json` | 프로젝트 메타+ops 묶음 적용 | 별도 JSON 필요 | 새 프로젝트 처음부터, 재사용 |
| `preset slideshow/lyric-video/intro-outro/pip` | 정형 작업 0~1줄 | 커스터마이즈 제한 | 슬라이드쇼/가사/인트로/PIP 등 정형 |
| `plan` | 자연어로 끝 | LLM 호출, 비결정적 | 사용자가 명령 짜기 싫을 때 |

## Recipe System

```bash
cli-anything-capcut validate-recipe -f recipe.json     # 구조만 검증 (replay 없이)
cli-anything-capcut import-recipe -p sess.json -f recipe.json   # 적용
cli-anything-capcut export-recipe -p sess.json -o r.json        # 내보내기
```

**Recipe 구조:**
```json
{
  "name": "demo", "width": 1920, "height": 1080, "fps": 30,
  "operations": [
    {"id": "clip1", "op": "add_video", "args": {"file": "D:/v.mp4", "track": "V1", "start": "0s", "duration": "auto"}},
    {"op": "add_video_animation", "args": {"track": "V1", "segment_ref": "clip1", "role": "intro", "name": "fade_in"}}
  ]
}
```

> **op 이름은 v0.4 명세** — `add_video_filter`/`add_video_mask`/`add_video_background`는
> recipe에선 `add_filter`/`add_mask`/`add_background`로 통일. `references/operations.md` 참조.

**템플릿**: `references/recipes/` 5종 (luxury-b2b, social-short, cinematic, tutorial, music-video).
사용법은 `references/recipe-guide.md`. 옛 `--category` / `--type` / 0~100 색값 등이 있으면
각 레시피를 v0.4 스펙으로 업데이트해야 함.

**batch**:
```bash
cli-anything-capcut batch -p sess.json -f ops.json --skip-errors
# ops.json = [{"id":"c1","op":"add_video","args":{...}}, {...}]
```

## 스타일 프리셋 (재사용)

`style` 명령으로 자주 쓰는 텍스트/비디오/오디오 조합을 이름으로 저장하고 한 줄로 적용.

**내장 프리셋**:
- text: `cinematic`, `lifestyle-brand`, `minimal-caption`, `news-title`, `youtube-subtitle`
- video: `cinematic-warm`, `corporate-clean`, `social-punchy`
- audio: `bgm-background`, `podcast-voice`, `sfx-short`

```bash
cli-anything-capcut style list
cli-anything-capcut style save my-bold --category text --font arial --size 7 --bold --color 255,235,0 \
  --border '{"alpha":1,"color":[0,0,0],"width":0.1}' --description "노란 굵은 강조"
cli-anything-capcut style apply-video -p p.session.json --track V1 --segment-ref op_0 --style cinematic-warm
cli-anything-capcut text add -p p.session.json -t "OPEN" --style my-bold -s 0s -d 2s
```

## 에이전트 셀프-디버그

```bash
# 다음 추천 작업 + 세션 종합
cli-anything-capcut agent status -p p.session.json

# 임의의 에러 메시지 해석
cli-anything-capcut agent explain-error -e "RuntimeError: segment_ref 'op_5' not found"

# 자동 복구 모드로 저장 (실패 op 격리하고 재시도)
cli-anything-capcut save -p p.session.json --auto-fix --max-attempts 3
```

## Alias (enum 검색)

```bash
cli-anything-capcut alias classes                    # 전체 카테고리
cli-anything-capcut alias list --class TransitionType
cli-anything-capcut alias search -k "fade"           # 한자/영어 모두 매치
cli-anything-capcut alias resolve "fade_in"          # 영어 alias → 중문 enum
```

**자주 쓰는 alias** (검증됨):
- **TransitionType**: dissolve, fade, blur, slide_left, slide_right, slide_up, flash, black_flash, glitch
- **IntroType (video)**: fade_in, zoom_in, slide_up, bounce_in, blur_open
- **OutroType (video)**: fade_out, zoom_out, blur_close, bounce_out
- **FilterType**: cinematic, vintage, warm, cool, film, vivid, bw, dreamy, sepia
- **VideoSceneEffectType**: vignette, blur, glitch, light_leak, soft_light, lens_flare, film_grain, bokeh
- **TextIntro**: typewriter, fade_in, karaoke, slide_up, bounce_in
- **TextOutro**: fade_out, dissolve_up, trail, blur_out
- **AudioSceneEffectType**: noise-reduction, echo, reverb

> **모르는 이름은 항상 `alias search -k "..."`로 검색**. enum은 v0.4에서도 한자 baseline.

## ClipSettings Presets

`--clip-settings`/`--position` 주요 값: `center`, `fill`, `fit`, `top`, `bottom`,
`pip-top-right`, `pip-top-left`, `pip-bottom-right`, `pip-bottom-left`,
`subtitle-bottom`, `subtitle-top`, `title-center`, `lower-third`, `upper-left`, `watermark-br`,
`small-center`, `top-third`, `bottom-third`, `left`, `right`.

위치만 미세조정하려면 `text add --position-x 0 --position-y -0.7` 처럼 직접 좌표 (-1~1).

## 한글 경로와 staging

`video add`/`audio add`/`image add` 등에 한글/공백 경로를 그대로 넘겨도 됩니다 — staging 레이어가
ASCII 캐시 폴더로 자동 복사하고 세션엔 캐시 경로를 기록합니다. 옛 "영문 경로 강제" 룰은 v0.4에서
폐기됨.

```bash
cli-anything-capcut staging stats   # 캐시 크기/파일 수
cli-anything-capcut staging list    # 어떤 파일들이 staged 되어 있는지
cli-anything-capcut staging clear   # 디스크 회수가 필요할 때만
```

> 단, 캐시 경로 자체는 **읽기/쓰기 동안 유지되어야 함**. CapCut이 드래프트를 열 때 그 경로를
> 참조하므로, `staging clear`는 작업 완료/렌더 후에만.

## 에러 복구

```
save 실패 → diagnose → validate → agent explain-error "MSG" → undo --type TYPE → save --auto-fix
```

| 에러 | 해결 |
|------|------|
| `segment_ref 'op_5' not found` | `history`로 op ID 확인. recipe라면 `id` 필드 오타 체크 |
| `File not found` | staging 가능한지 확인 (`asset relocate`로 정리) |
| `Track 'V1' not found` | creation op의 `track` 인자 확인. 기본 자동 생성됨 |
| `Fade not supported on Text` | `keyframe add --property alpha` 사용 |
| `Duration 'auto' not supported for image` | `-d 3s` 등 명시 |
| `Invalid enum 'fade_in_xxx'` | `alias search -k "fade"`로 정확한 alias 확인 |
| `--category not recognized` | `--role` 로 변경 (v0.4) |

**방어 패턴**: `project clone` 또는 별도 디렉토리 백업 → 작업 → `validate` → `review` →
`save --auto-fix` → `preview --open` 으로 사람 확인 → `render`.

## References

### Brief·창작 가이드 (영상 기획·감각)

| 파일 | 내용 | 언제 읽나 |
|------|------|----------|
| `references/brief-questions.md` | 3페이즈 16질문 · 타입별 템플릿 · 디폴트 정책 | **사용자 요청 모호하면 제일 먼저** |
| `references/video-design.md` | BOLD 원칙 · 시네마토그래피 5원칙 · **10무드 색보정 레시피**(-1.0~+1.0) · 자막 safe zone·폰트·크기 · 톤별 크리에이터 큐레이션 | Phase 1 톤 결정 + Phase 3 색·자막 |
| `references/content-formulas.md` | 훅 10 카테고리(한국어 50+ 예시·230만뷰 공식) · 컷 템포 13장르 ASL 매트릭스 · BGM 14장르 BPM·볼륨·페이드 | **Phase 2 구조·상세 전용** |
| `references/anti-slop-video.md` | AI slop TOP 5 + 30 안티패턴 · ❌→✅ · 검증 함수 pseudocode | **렌더 전 검증 필수** |

### CLI 사용 레퍼런스

| 파일 | 내용 | 언제 읽나 |
|------|------|----------|
| `references/operations.md` | v0.4 op 전체 목록 + recipe args 스펙 | recipe JSON 작성/디버깅 |
| `references/render-workflow.md` | validate/review/preview/save/render/render-headless 상세 | 렌더 단계 결정/문제 |
| `references/recipe-guide.md` | recipe 플레이스홀더 치환, 적용 워크플로우 | 레시피 템플릿 사용 |
| `references/advanced.md` | 색보정 패턴, 그린스크린 한계, 세션 관리, REPL, 에러 복구 | 복잡한 색보정/세션 분기 |
| `references/recipes/*.json` | 5개 레시피 템플릿 (v0.4 스펙) | 새 프로젝트 시작점 |
