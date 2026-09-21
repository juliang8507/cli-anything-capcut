# CapCut GUI 실측 검증 (2026-09-01)

이번 수정의 모든 판정은 `draft_content.json` 수준이었다. 실제로 CapCut이 그 값을
읽는지는 별개 문제이므로 GUI로 직접 열어 확인했다.

- CapCut 9.3.0.3970 (설치본 중 최신)
- CLI로 생성한 검증 draft 2종을 실제로 열어 확인

## 확인된 것

| 항목 | 결과 |
|---|---|
| CLI 생성 draft 인식 | ✅ 프로젝트 목록에 나타나고 정상적으로 열린다 |
| 비디오 세그먼트 | ✅ 타임라인에 정확한 위치·길이로 배치 |
| 텍스트 세그먼트 | ✅ 2개 세그먼트가 지정한 시각(0~4s, 4~8s)에 배치 |
| 텍스트 내용 | ✅ 한글 포함 정확히 표시, 프리뷰에 렌더됨 |
| 폰트 크기 | ✅ 지정값 반영 |
| **폰트** | ❌ **적용되지 않음 — `Font: System` 으로 표시** |

## 폰트가 적용되지 않는다 (핵심 발견)

두 경로 **모두** 실패했다.

- 번들 폰트: `materials.texts[].font_resource_id = '7044878305576620546'` (alegreya)
- 로컬 TTF: `materials.texts[].font_path = 'C:\\Windows\\Fonts\\malgunbd.ttf'`

CapCut UI 의 Font 필드는 둘 다 `System` 으로 표시한다.

**CapCut 이 그 필드를 지우지는 않는다.** 프로젝트를 열면 CapCut 이 draft 를 다시 저장하는데
(파일 mtime 갱신 확인), 그 후에도 우리가 넣은 `font_resource_id` 와 `font_path` 가
그대로 남아 있다. 즉 **인식하지 못해 무시**하는 것이지 거부하는 것이 아니다.

### 참고 — CapCut 자신이 쓰는 형식

사용자의 기존 draft 표본에서 CapCut 이 저장한 폰트 필드는 이렇다:

```json
"font_path": "C:/Users/<사용자>/AppData/Local/CapCut/Apps/8.2.0.3462/Resources/Font/SystemFont/en.ttf",
"font_size": 15.0,
"font_title": "none",
"fonts": []
```

우리 값과의 차이:
1. **경로 구분자** — CapCut 은 정방향 슬래시(`/`), 우리는 역슬래시(`\\`)
2. **경로 위치** — CapCut 은 자기 앱 폴더 안의 폰트, 우리는 `C:\Windows\Fonts`

원인이 (1) 경로 형식인지, (2) CapCut 폰트 폴더 밖을 거부하는 것인지,
(3) `font_id`/`font_name`/`font_title` 같은 동반 필드가 필요한 것인지는 **미확정**이다.
공개 스키마 문서(gist renezander030)는 `content` JSON 안 `styles[].font{id,path}` 구조를
언급하지만, 실제 CapCut 저장본에는 그 필드가 **없었다**.

## 확인하지 못한 것

- **postprocess 8종(reverse/blend-mode/chroma-key/lut/speed-curve/curves/hsl/freeze-frame)의
  시각 확인.** CapCut 이 메인 창과 Design Studio webview 를 함께 띄우는 구조여서
  GUI 자동화 클릭이 의도한 창에 전달되지 않았다. 파일 수준에서는 전부 검증됐다.
- dangling 참조 1건(pycapcut 책임)을 CapCut 이 어떻게 처리하는지.

## 이 검증이 드러낸 교훈

CHANGELOG 상단에 박은 완료 판정 기준은 이랬다:

> op 를 추가한 기능은 CLI 실행 → save → 산출 draft 필드 확인까지 통과해야 완료로 적는다.

**폰트는 이 기준을 통과했지만 실제로는 동작하지 않는다.** draft 에 필드가 있어도
CapCut 이 읽지 않으면 사용자에게는 아무 일도 일어나지 않는다.

즉 이 저장소가 겪은 원래 문제(테스트는 통과하는데 기능은 죽어 있음)가
한 층 위에서 반복된 셈이다. 판정 기준에 다음을 덧붙여야 한다:

> 사용자가 눈으로 보는 결과(폰트·효과 등 렌더 결과)를 바꾸는 기능은
> CapCut GUI 에서 실제로 반영되는지 확인해야 완료로 적는다.


---

# 후속 — 원인 규명과 해결 (2026-09-01)

위 검증에서 "폰트가 적용되지 않는다" 로 끝냈으나, 조사를 넓혀 원인을 찾고 고쳤다.

## 원인

CapCut 은 텍스트 material 레벨의 `font_path` / `font_resource_id` 를 **읽지 않는다.**
실제로 읽는 곳은 `materials.texts[].content` (JSON 인코딩 문자열) 안의

```
styles[0].font = {"id": "...", "path": "..."}
```

사용자가 CapCut GUI 로 만든 기존 draft 를 전수 조사해 이 구조를 찾았다.
우리가 만든 draft 의 `styles[0]` 에는 `font` 키가 아예 없었다.

## 실측 매트릭스

| 조합 | 결과 |
|---|---|
| material 레벨 `font_path`/`font_resource_id` 만 | `Font: System` (적용 안 됨) |
| `content.styles[].font = {id, path}` (캐시 폰트) | 실제로 렌더됨 |
| `{"id": "", "path": "C:/Windows/Fonts/malgunbd.ttf"}` | `Font: Malgun Gothic Bold` 로 인식 |
| `font` 객체에 `id` 키 **없이** `path` 만 | **CapCut 프로세스 크래시** |

`id` 키는 반드시 존재해야 하고 값은 빈 문자열이어도 된다. 이 사실은 CapCut 이
두 번 죽는 것을 보고 좁혀 확인했다.

## 참고한 외부 사례

`renezander030/capcut-cli` (JS, 활발) 는 폰트를 **지정하지 않고 복제**한다 —
`copyTextStyle` 로 기존 캡션 스타일을 미러링하고 `harvest-enums` 로 실제 draft 에서
폰트 id 를 수확한다. 소스 주석에 *"nameless font ids ... are never guessed"* 라고 적혀 있다.
폰트 id 는 발명할 수 없다는 것을 그들도 같은 결론으로 다룬 셈이다.

## 해결 (R13)

- postprocess 가 `content` 를 파싱해 `styles[0].font` 를 주입. `range`/`size`/`fill` 등
  기존 style 키는 보존한다.
- 폰트 별칭을 "이 PC 에 실제 파일이 있는 것" 으로 재정의하고 세 곳을 실행 시 스캔:
  CapCut 캐시 4개 / CapCut SystemFont 18개 / Windows 한글 폰트 24개.
- 로컬에 없는 번들 폰트는 이유를 밝히는 오류로 중단.

**GUI 재검증 결과**: `--font malgun_gothic_bold` -> `Malgun Gothic Bold`,
`--font jua` -> `한도`. 폰트가 CapCut 에서 정확히 인식된다.
