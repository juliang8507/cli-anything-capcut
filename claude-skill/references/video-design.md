# 영상 디자인 — 감각·색·자막·레퍼런스

> **이 파일의 역할**: 에이전트가 톤·색감·자막 스타일·레퍼런스를 결정할 때 참조.
> **언제 읽나**: 사용자 요청에 "멋지게", "감성", "시네마틱" 같은 모호한 톤 표현이 있을 때. Brief Phase 1-6(톤 BOLD 선택) 직후.

## 1. BOLD 원칙 (frontend-design 영상판)

평균값은 잊혀집니다. **하나만 강조하고 극단으로 밀어붙이세요**.

- **하나만 주인공** — 한 컷에 주제는 단 하나. 나머지는 조연
- **극단 지향** — 어두운 영상이면 더 어둡게, 밝은 영상이면 더 밝게
- **Unforgettable Moment** — 영상 전체에서 시청자가 멈추는 1초 설계
- **시그니처 한 가지** — 색감·폰트·트랜지션 중 하나는 "이 사람 영상" 식별 가능
- **Safe = Death** — brightness 0, contrast 0, saturation 0은 영상의 죽음

## 2. 시네마토그래피 5원칙

| 원칙 | CapCut 활용 |
|------|-------------|
| **Rule of Thirds** | `clip_settings` X/Y 오프셋. 인물 눈을 상단 1/3 라인에 |
| **Leading Lines** | 줌·크롭 시 라인 보존. 주제로 유도하는 선 살리기 |
| **Depth 3레이어** | 전경(선명·고채도) + 중경 + 배경(흐림·저채도) |
| **Negative Space** | 자막을 화면 가득 채우지 말 것. 주변 여백 |
| **Visual Hierarchy** | 주인공만 highlight, 주변은 -0.05~-0.1 contrast로 죽이기 |

**색 심리**: 따뜻한 색(빨강·주황·노랑)=다가옴, 차가운 색(파랑·초록)=멀어짐 → 주인공 웜·배경 쿨이 깊이감 공식.

**거장 시그니처**
- **Roger Deakins** (Blade Runner 2049): 한 영상 = 한 색대비 (warm vs cool) + 백라이트 실루엣
- **Emmanuel Lubezki** (Revenant): 자연광·golden hour + 후반 desaturation

**Consistency**: 폰트 1~2개 / 색팔레트 3색 이내 / 트랜지션 3종 이내 / 피부톤 orange luminance +10~15 일정

## 3. 색보정 — 10무드 레시피 (CapCut CLI -1.0~+1.0)

**변환 공식**: CapCut UI 값 ÷ 100 = CLI 값. 예: UI contrast +20 → `--contrast 0.2`

### 3.1 CINEMATIC (Blade Runner / Dune)
```bash
color adjust --brightness -0.05 --contrast 0.15 --saturation -0.10 \
  --temperature -0.05 --highlights 0.10 --shadows -0.15
# teal-orange: color wheels --shadow-hue 200 --shadow-sat 0.20 --highlight-hue 30 --highlight-sat 0.15
```

### 3.2 VIVID / SNS POP (MrBeast / TikTok 광고)
```bash
color adjust --brightness 0.10 --contrast 0.20 --saturation 0.30 \
  --temperature 0.05 --vibrance 0.25 --sharpen 0.15
```
⚠️ **saturation 0.3 상한** (이상은 빨강이 핫핑크).

### 3.3 MINIMAL (Apple 키노트)
```bash
color adjust --brightness 0.05 --contrast 0.10 --saturation -0.15 \
  --temperature 0.0 --highlights 0.05 --shadows 0.05
```

### 3.4 노을 / Golden Hour
```bash
color adjust --brightness 0.08 --contrast 0.12 --saturation 0.10 \
  --temperature 0.25 --highlights -0.20 --shadows 0.15
# color wheels --shadow-hue 220 --shadow-sat 0.10 --highlight-hue 40 --highlight-sat 0.20
```
하늘 디테일 살리려면 highlights 강하게 누름.

### 3.5 레트로 / VHS
```bash
color adjust --brightness 0.05 --contrast -0.15 --saturation -0.25 \
  --temperature 0.15 --highlights -0.10 --shadows 0.20
# + effect add-filter --name film --intensity 0.5 + film_grain + vignette
```
핵심: shadow +0.15~+0.25로 milky black (옛 프린트 느낌).

### 3.6 B&W 필름 누아르
```bash
color adjust --brightness -0.05 --contrast 0.40 --saturation -1.0 \
  --highlights 0.15 --shadows -0.25
```
**회색 최소화, 극단 콘트라스트**가 핵심.

### 3.7 쿨·블루 / 사이버펑크
```bash
color adjust --brightness -0.10 --contrast 0.25 --saturation 0.10 \
  --temperature -0.30 --highlights 0.10 --shadows -0.20
# color wheels --shadow-hue 240 --shadow-sat 0.30 --highlight-hue 300 --highlight-sat 0.25
```

### 3.8 웜·오렌지 (카페·라이프스타일·라운지)
```bash
color adjust --brightness 0.10 --contrast 0.10 --saturation 0.05 \
  --temperature 0.20 --shadows 0.10
```
💎 **럭셔리 제품 영상 기본 추천**.

### 3.9 MOODY (Netflix Original)
```bash
color adjust --brightness -0.15 --contrast 0.30 --saturation -0.30 \
  --temperature -0.15 --highlights -0.10 --shadows -0.05
```
shadows를 -0.05 정도만 내림 (milky black 트렌드).

### 3.10 PASTEL (일본·한국 감성 vlog)
```bash
color adjust --brightness 0.15 --contrast -0.10 --saturation -0.20 \
  --temperature 0.05 --highlights -0.15 --shadows 0.20
# color wheels --shadow-hue 180 --shadow-sat 0.10 --highlight-hue 340 --highlight-sat 0.15
```

### 무드 치트시트

| 무드 | bright | contrast | sat | temp | 한 줄 |
|------|--------|----------|-----|------|-------|
| CINEMATIC | -0.05 | +0.15 | -0.10 | -0.05 | teal-orange + crushed blacks |
| VIVID | +0.10 | +0.20 | **+0.30** | +0.05 | 스크롤 멈추는 강도 |
| MINIMAL | +0.05 | +0.10 | -0.15 | 0.0 | 중립 깔끔 |
| 노을 | +0.08 | +0.12 | +0.10 | **+0.25** | 강한 웜 |
| 빈티지 | +0.05 | -0.15 | -0.25 | +0.15 | milky black |
| B&W 노아르 | -0.05 | **+0.40** | **-1.0** | 0 | 극단 콘트라스트 |
| 사이버 | -0.10 | +0.25 | +0.10 | **-0.30** | 어둠+네온 |
| 웜/카페 | +0.10 | +0.10 | +0.05 | +0.20 | 안락함 (**라이프스타일 기본**) |
| MOODY | **-0.15** | +0.30 | -0.30 | -0.15 | 어둡지만 milky |
| PASTEL | **+0.15** | -0.10 | -0.20 | +0.05 | high-key 부드러움 |

## 4. 자막 타이포그래피

### 4.1 플랫폼 Safe Zone

**YouTube Shorts / TikTok (9:16)**
- 상단 15~20% 가림 (사용자명·For You)
- **하단 25% 가림** (좋아요·댓글·공유 UI)
- 안전 영역: **중간 60%**만 사용
- 좌우 5~10% 마진, 자막 너비 70~80%

**16:9 가로 (YouTube 본편)**
- 상단 5%, 하단 10% safe zone
- 자막은 하단 1/3 영역 중앙

### 4.2 폰트 (2026 기준)

**한글**
| 폰트 | 용도 |
|------|------|
| **Pretendard** | 1순위 본문/자막 (모던, 무료, 가변) |
| **Noto Sans KR (본고딕)** | 자막 표준 (Google, 가독성 검증) |
| **Black Han Sans** | 타이틀/강조 (쇼츠 훅용) |
| **한글 캐주얼체 (G마켓 산스 등)** | 캐주얼 타이틀 (예능톤) |

**영문**
| 폰트 | 용도 |
|------|------|
| **Montserrat Bold** | **2026 자막 1순위** (geometric sans, 무료) |
| **Bebas Neue** | 타이틀 (콘덴스드 캡스, 쇼츠·썸네일 강자) |
| **Anton** | 타이틀 (Bebas보다 각진, 더 강한 임팩트) |

⚠️ **Inter는 UI 폰트라 자막엔 약함** — Montserrat가 표준

### 4.3 크기

| 플랫폼 | 본문 | 강조·타이틀 |
|--------|------|-------------|
| YouTube Shorts | 48~64px | 80~120px |
| TikTok | 48~72px | 96~144px |
| YouTube 가로 | 40~48px | 72~96px |

절대 36px 이하 금지. 휴대폰 1m 거리에서 읽혀야 OK.

### 4.4 가독성 기법 (배경 대응)

| 방법 | 설정 |
|------|------|
| 세미투명 박스 | 검정 60~80% opacity + 흰색 Bold. 모든 플랫폼 안전, WCAG AA |
| Stroke | 흰색 Bold + 검정 2~4px. TikTok/Shorts 표준 |
| Drop Shadow | 검정 blur 2~4px, offset 2~3px, opacity 60~80%. 영화 느낌 |
| 콤보 (최강) | Stroke 2px + Shadow blur 4px offset 2px. 알록달록 배경도 읽힘 |

**WCAG 2.1 AA**: 텍스트·배경 대비비 **4.5:1 이상**.

### 4.5 타이밍·글줄

| 항목 | 권장값 |
|------|-------|
| 한 줄 글자 | 영문 32~42자 / 한글 16~22자 |
| 동시 줄 수 | 최대 2줄 |
| 캡션 한 덩어리 | 쇼츠 1~4 단어 / 긴 영상 한 호흡 |
| 표시 시간 | 1.5~3초 |
| 오디오 싱크 | 0.1~0.3초 먼저 등장 (인지 보정) |

### 4.6 모션 타이포 패턴

| 패턴 | CapCut |
|------|--------|
| Word-by-Word Reveal | `text_animation --role intro --name rise/pop` |
| Karaoke (노래방식) | keyframe 알파 색 변화 |
| Typewriter | `text_animation --name typewriter` |
| Bounce/Pop | scale 키프레임 + `bounce` |
| Slide In | `slide_in_left/right` |
| Blur Reveal | `blur_open` (시네마틱 인트로) |

**2026 트렌드**: 단순 페이드 아웃. **word-by-word + scale pop** 이 쇼츠 표준.

## 5. 톤별 레퍼런스 크리에이터

사용자가 "이런 느낌"이라고 할 때 이 목록에서 가장 가까운 2~3명 언급하고 확인받으세요.

### CINEMATIC
- 국외: **Peter McKinnon**(cinematic vlog 교과서), **Matti Haapoja**, **Casey Neistat**, **Emmanuel Lubezki** 작품
- 한국: **CINEMATIC UNICORN**, **Moving Pictures**, **루츠 LOOTS**

### VIVID / SNS POP
- **MrBeast**(후크 3초 + 색감 과장), **Alex Hormozi**(비즈 쇼츠), **Gary Vee**
- 한국 쇼츠: **빵송국**, **워크맨**, **흥미로운 은둔**
- 뷰티: **이사배 RISABAE**, **Hyuna Kim**

### MINIMAL / CLEAN
- **Apple 제품 키노트**, **MKBHD**, **Unbox Therapy**, **Dezeen**
- 한국: **EO**, **Outstanding** (스타트업 다큐)

### MOODY / 어두운 시네마틱
- **Netflix 시리즈 트레일러**, **David Fincher** (Mindhunter, Fight Club)
- 한국: **그것이 알고싶다**, **tvN 드라마 트레일러**

### 노을·golden hour
- **Sam Kolder**, **Jon Olsson**, **Peter McKinnon Golden Hour 튜토리얼**

### PASTEL / 일본·한국 감성
- **Emma Chamberlain**, **ponzunon (포유)**, **김뚜깡**, **하코**

### 레트로 / VHS
- **Wong Kar-wai** 영화, **Stranger Things**, Synthwave 채널

### 사이버펑크 / 쿨블루
- **Blade Runner 2049**, **Cyberpunk 2077 트레일러**, **Tron: Legacy**
- YouTube: **Neon Icons**, **Synthwave Avenue**

### 💎 럭셔리·라이프스타일
- **Aman Resorts 공식**(최상급 럭셔리, 미니멀+시네마틱)
- **Four Seasons**, **Rosewood Hotels**, **Belmond**, **Bulgari Hotels**
- 한국: 럭셔리 브랜드 공식 채널
- 감성 vlog: "라이프스타일 브이로그" 검색

### 플랫폼 벤치마크
- YouTube Shorts: **vidIQ**, **TubeBuddy**, **Hook Point**(Brendan Kane)
- 인스타 릴스: **HighOutputClub**, **Later.com**
- 틱톡: **Post Bridge**, **Socialync**
- 유튜브 본편: **Paddy Galloway**, **Colin and Samir**

### 편집 이론
- **Every Frame a Painting** (YouTube) — 편집 분석 클래식
- **Thomas Flight**, **In Depth Cine**, **Behind the Curtain**

### 색보정
- **Waqas Qazi** (DaVinci Resolve), **Ground Control Color**, **Noam Kroll**

## 6. 에이전트 워크플로우

사용자가 "이런 느낌으로":
1. 이 파일에서 가장 가까운 톤·크리에이터 **2~3** 언급
2. "○○ 채널의 △△ 영상 같은 느낌이에요?" 확인
3. 해당 무드의 구체 색보정 수치(섹션 3) + 폰트(섹션 4.2) + 컷 템포(`content-formulas.md` 참조) 적용

사용자 URL 주면:
1. yt-dlp로 메타데이터 확인 (제목·채널)
2. 이 파일에서 채널 매칭 → 톤 추정
3. Brief Phase 1-6 에 반영

## 출처
- Cinema-LUTs, Petapixel, Noam Kroll (teal-orange, blockbuster look)
- Opus Pro (Shorts·TikTok caption best practices)
- Filmmakers Academy, StudioBinder (composition, depth)
- KCI (한글 가독성 연구), Yuzzit (2026 subtitle fonts)
- BWill Creative (golden hour, pastel)
- British Cinematographer (Lubezki), Filmlocal (Deakins)
