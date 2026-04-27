# Render & Validation Pipeline (v0.4)

CLI는 5개 단계 명령으로 결과물 품질을 보장합니다. 각 단계는 *다른 종류*의 문제를 잡으므로 건너뛰지 마세요.

```
ops 추가 → validate → review → preview → save → render
            (구조)    (품질)   (눈)    (디스크) (MP4)
```

## 1. validate — replay dry-run

세션의 op 시퀀스를 실제 적용하지 않고 모의 실행해 op 간 의존성/시간 충돌을 확인합니다.

```bash
cli-anything-capcut validate -p my.session.json
# 실패 시 어떤 op가 깨졌는지 출력 → undo / edit-op 또는 segment_ref 수정
```

> **언제 실패?** 잘못된 segment_ref, 음수 duration, 트랙 존재하지 않음, 한자 enum 미존재 등.

## 2. review — 자동 품질 QA

CLI가 검사하는 항목 (8종):

| 체크 | 의미 |
|------|------|
| `gaps` | 트랙 안 의도하지 않은 빈 구간 |
| `overlaps` | 트랙 안 세그먼트 겹침 |
| `volume` | 너무 큰/작은 오디오, 클리핑 |
| `subtitles` | 자막 표시 시간이 너무 짧거나 김 (가독성) |
| `media` | 미디어 파일 존재/접근 가능 |
| `resolution` | 미디어 해상도 vs 프로젝트 해상도 |
| `duration` | 트랙 길이 일관성 |
| `render` | 렌더 호환성 (지원 안 되는 op 등) |

```bash
cli-anything-capcut review -p my.session.json                          # 전체
cli-anything-capcut review -p my.session.json --severity warning       # warning 이상만
cli-anything-capcut review -p my.session.json --only volume,subtitles  # 특정만
cli-anything-capcut review -p my.session.json --fail-on-warning        # CI용 (warning면 exit 1)
```

> **워크플로우 권장**: 자막 들어간 영상은 `review --only subtitles,volume,gaps --fail-on-warning`
> 으로 자막 속도/볼륨/갭만 빠르게 확인 후 진행.

## 3. preview — HTML 간트차트 미리보기

세션의 트랙/세그먼트를 self-contained HTML로 렌더해서 브라우저로 열어줍니다.
사람의 눈으로 “이게 내가 원하는 구조 맞나?” 확인하기 위해.

```bash
cli-anything-capcut preview -p my.session.json --open
# 옵션: --thumbs (각 비디오/이미지 첫 프레임을 ffmpeg로 추출해 인라인. 느림)
# 옵션: -o my.preview.html (저장 경로)
```

> **언제 thumbs 켜나?** 어떤 클립이 어디 있는지 헷갈릴 때, 또는 사용자에게 확인 받을 때.
> 일반 디버깅엔 끄고 시작.

## 4. save — CapCut 드래프트 디스크 저장

`project new` 시 만든 세션 JSON을 실제 CapCut 드래프트 폴더에 commit합니다.
이 단계가 끝나야 CapCut GUI에서 프로젝트가 보입니다.

```bash
cli-anything-capcut save -p my.session.json
```

**실패 시 옵션 3가지**:

| 옵션 | 동작 | 언제 |
|------|------|------|
| (없음, 기본) | 첫 에러에서 멈춤 | 보통 |
| `--skip-errors` | 실패한 op 건너뛰고 계속 | 빠른 prototype |
| `--auto-fix --max-attempts 3` | 실패 op를 격리(quarantine)하고 반복 재replay | 신뢰도 높이기 |

> **권장**: 자동화 파이프라인에선 항상 `--auto-fix`. 인터랙티브 디버깅에선 옵션 없이.

## 5. render — MP4 export

두 가지 방식.

### A. `render` (CapCut GUI 자동 제어)

CapCut을 띄워서 메뉴를 자동 클릭해 export. 모든 효과/필터/애니메이션이 정확히 보이는 ground truth.

```bash
cli-anything-capcut render -p my.session.json -o "D:/out.mp4" \
  --resolution 1080P --framerate 30 --save-first --timeout 1800
```

| 옵션 | 의미 |
|------|------|
| `--resolution` | 720P/1080P/2K/4K/8K |
| `--framerate` | 24/25/30/50/60 |
| `--save-first` | render 전에 자동 save (드래프트 갱신) — 권장 |
| `--timeout` | export 타임아웃(초). 기본 1200(20분), 긴 영상은 늘리기 |
| `-o` 생략 | CapCut 기본 출력 폴더 사용 |

> **단점**: CapCut이 설치/실행돼야 함. GUI 자동화이므로 다른 창 활성화하면 깨짐. 무인 서버 X.

### B. `render-headless` (ffmpeg 직접)

CapCut 없이 ffmpeg로 직접 합성. 빠르고 무인 서버 OK. 단, 일부 op(필터/이펙트)는 미지원.

```bash
cli-anything-capcut render-headless -p my.session.json -o "D:/out.mp4" \
  --crf 20 --preset medium
# 옵션: --allow-unsupported (미지원 op 무시하고 진행)
# 옵션: --dry-run (ffmpeg 명령만 출력)
```

| 옵션 | 의미 |
|------|------|
| `--crf` | x264 품질 0~51, 18~28 권장 (낮을수록 고품질, 큰 파일) |
| `--preset` | ultrafast/veryfast/fast/medium/slow/veryslow (느릴수록 작은 파일) |
| `--allow-unsupported` | 지원 안 되는 op는 무시하고 진행 (결과에 반영 안 됨) |
| `--dry-run` | ffmpeg 명령만 출력 (디버깅) |

**지원**: V1 concat + V2+ overlay + xfade 트랜지션 + 오디오 믹싱. **미지원**: 비디오 필터/이펙트, 키프레임 애니메이션 일부, 색보정 일부, 텍스트 스타일 세부.

> **선택 매트릭스**:
>
> | 상황 | 추천 |
> |------|------|
> | 최종 납품용 | `render --save-first` (정확함) |
> | 빠른 미리보기 / CI | `render-headless --crf 23 --preset fast` |
> | 자동 워크플로우 / 무인 | `render-headless` 만 |
> | 효과 가득한 시네마틱 | `render` (headless는 효과 빠짐) |

## 통합 워크플로우 (recommended)

```bash
NAME="my_video"
SESS="${NAME}.session.json"

# 0. 환경
cli-anything-capcut diagnose

# 1. 프로젝트 + ops
cli-anything-capcut project new -n "$NAME" --preset landscape
cli-anything-capcut video add -p "$SESS" -f "D:/내 영상/v.mp4" -s 0s -d auto --track V1
cli-anything-capcut srt   import -p "$SESS" -f "D:/subs.srt" --track T1 --style youtube-subtitle
cli-anything-capcut audio add -p "$SESS" -f "D:/bgm.mp3" -s 0s -d auto --track A1 --volume 0.3
cli-anything-capcut effect add-filter -p "$SESS" --name cinematic --intensity 0.4

# 2. 검증 단계
cli-anything-capcut validate -p "$SESS"
cli-anything-capcut review   -p "$SESS" --severity warning --fail-on-warning

# 3. 사람 확인
cli-anything-capcut preview  -p "$SESS" --open

# 4. 저장 + 렌더
cli-anything-capcut save     -p "$SESS" --auto-fix --max-attempts 3
cli-anything-capcut render   -p "$SESS" -o "D:/${NAME}.mp4" --resolution 1080P --save-first
```

## 에러 → 명령 매트릭스

| 에러 종류 | 진단 | 복구 |
|----------|------|------|
| validate 실패 | `agent explain-error -e "MSG"` | `undo --type X` 또는 `edit-op` |
| review warning (subtitle 너무 빠름) | `review --only subtitles --json` | SRT 편집 또는 segment duration 조정 |
| save 실패 (한 op 깨짐) | `save --auto-fix --max-attempts 3` | 격리 후 재replay |
| save 다중 실패 | `validate` → `history --filter add_X` | 문제 op 일괄 `delete-op` |
| render GUI 멈춤 | `--timeout` 늘리기 또는 `render-headless` | CapCut 재시작 |
| render-headless 결과 빠진 효과 | `render` (GUI) | 또는 `--allow-unsupported`로 진행 |
