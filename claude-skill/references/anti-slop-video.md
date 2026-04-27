# AI Slop 안티패턴 — 렌더 전 검증 체크리스트

> **이 파일의 역할**: 렌더 전에 에이전트가 반드시 통과시켜야 할 ❌→✅ 체크리스트.
> **언제 읽나**: Phase 3 완료 후, `save` 직전. 검증 실패하면 에이전트가 사용자에게 경고.

## 핵심 원칙

2026년 YouTube의 **20%+가 "AI slop"으로 분류**됨. 시청자는 이미 AI 시그니처 패턴을 무의식적으로 학습. 아래 6 카테고리 × 30개 안티패턴 중 **TOP 5만 피해도 AI slop 티의 90% 제거**.

## ⭐ TOP 5 (이것만이라도 지키기)

1. **폰트 Inter/Roboto/Arial/맑은고딕 금지** → Pretendard Bold, Montserrat Bold, Black Han Sans
2. **"안녕하세요/Hi everyone/오늘은/Today" 시작 금지** → 첫 3초 훅 의무
3. **TTS 후처리 의무** → room tone -45dB + 랜덤 pause 300~600ms + EQ 고음 -2dB
4. **컷 길이 균등화 금지** → Pictory "every scene roughly the same" 1순위 지문
5. **자막 정중앙 금지** → lower third (y=0.78) 디폴트, 정중앙은 emphasis만

---

## 1. 컷·템포 (5)

| ❌ | ✅ | Why |
|---|---|---|
| 모든 컷에 dissolve | **5% 이하**, 시간·장소 전환에만 | AI 자동편집 시그니처 |
| 같은 길이 컷 반복 | ASL 지키되 ±30% 변동 | 뇌가 "자동생성" 감지 |
| 비트 무관 컷 | BGM 120 BPM → 0.5초 단위에 맞춤 | 싱크 안 맞으면 어색 |
| 불필요 슬로모션 | 감정·강조 포인트에만 | 시간 채우기 티 |
| silence 0 | 1~2회 의도적 2~3초 정적 | 호흡·강조 공간 |

## 2. 텍스트·자막 (5)

| ❌ | ✅ | Why |
|---|---|---|
| Inter/Roboto/Arial/맑은고딕 | **Pretendard Bold / Montserrat Bold / Black Han Sans** | 가장 뚜렷한 AI 지문 |
| 모든 자막 정중앙 | **lower third (y=0.78)** 디폴트 | 자연스런 시선 |
| 자막 색 계속 바뀜 | 한 영상 = 1~2색 일관 | 산만함 = AI |
| 매 컷 다른 애니메이션 | 한 영상 = 1 패턴 (예: word-by-word pop) | 일관성 |
| 글자 30자 초과 | 영문 32~42자 / 한글 16~22자 / 최대 2줄 | 가독성 |

## 3. 색보정·필터 (5)

| ❌ | ✅ | Why |
|---|---|---|
| LUT intensity 100% | **0.3~0.5** | 색 뭉개짐 |
| saturation +0.4 이상 | +0.30 상한 | 빨강이 핫핑크 |
| 모든 씬에 vignette | 드라마틱 씬만 | 자동 적용 티 |
| 필름 그레인 과도 | intensity 0.2~0.3 | 노이즈 AI slop |
| 디폴트 필터 그대로 | `video-design.md` 섹션 3 수치 커스텀 | 템플릿 티 |

## 4. BGM·사운드 (5)

| ❌ | ✅ | Why |
|---|---|---|
| 장르 미스매치 | `content-formulas.md` 섹션 3 매트릭스 | 무드 파괴 |
| BGM 볼륨 > VO | **VO 대비 -18~-20 dB**, 나레이션 있으면 0.15 | 마스킹 |
| whoosh·tick 남발 | 컷 5개당 1회 이하 | 과도한 SFX = AI |
| TTS 원본 그대로 | room tone + pause + EQ 후처리 | 인간 목소리 흉내 |
| SFX 전혀 없음 | 강조 지점 2~3개 | 몰입감 |

## 5. 스토리·구성 (5)

| ❌ | ✅ | Why |
|---|---|---|
| "안녕하세요 여러분" / "Hi everyone" | 첫 3초 훅 (`content-formulas.md` 섹션 1.2) | 즉시 스와이프 |
| 불릿식 나레이션 나열 | 스토리 곡선 (Hook→Body→Climax→Outro) | 영상 ≠ 텍스트 |
| ChatGPT 한국어: "파헤쳐보겠습니다", "함께 알아보겠습니다", "이번 영상에서는", "결론적으로 말씀드리면" | 구어체, 개인 경험 1줄 | LLM 지문 |
| ChatGPT 영어: "delve", "furthermore", "moreover", "in conclusion", "leverage", "utilize", "pivotal" | 일상 단어 | LLM 지문 |
| 같은 인트로·아웃트로 템플릿 | 영상마다 변형 | 템플릿 티 |

## 6. 영상 소스 (4)

| ❌ | ✅ | Why |
|---|---|---|
| 스톡 영상 클리셰 (비즈니스맨 악수, 웃는 가족) | 본인 촬영 또는 Pexels 덜 쓰인 것 | 즉시 식별 |
| AI 이미지 결함 (손 6개, 눈 이상) | 얼굴·손 가린 각도 | 즉시 식별 |
| 해상도 불일치 클립 | 전부 동일 해상도 정규화 | 프로 인상 |
| **AI 영상 클립 3초 초과** | 3초 이하, 빠른 컷에 섞기 | 유체·직물 결함 노출 |

---

## 7. 사람답게 만드는 반전 기법

- 미세 손떨림 (카메라 정적 대신)
- 불규칙 컷 길이 (±30% 변동)
- 점프컷 3~5초 간격 (Reels +32% 인게이지)
- 자연 잡음 유지 (완벽 무음 X)
- silence beat 1회 (2~3초 정적)
- 손가락·그림자 프레임 침범

## 8. 검증 함수 (pseudocode)

```python
def validate_anti_slop(recipe):
    errors, warnings = [], []

    # 1. 폰트
    BAD_FONTS = ["Inter", "Roboto", "Arial", "맑은 고딕", "Helvetica", "Noto Sans"]
    for t in recipe.text_ops:
        if t.font in BAD_FONTS:
            errors.append(f"폰트 '{t.font}' → Pretendard/Montserrat/Black Han Sans")

    # 2. 인트로
    first = recipe.text_ops[0].text if recipe.text_ops else ""
    BAD_INTROS = ["안녕하세요", "Hi everyone", "오늘은", "Today"]
    if any(p in first for p in BAD_INTROS):
        errors.append(f"인트로 클리셰 '{first[:20]}' → 훅으로 교체")

    # 3. 컷 길이 변동성
    cuts = [op.duration for op in recipe.video_ops]
    if len(cuts) > 3 and stdev(cuts)/mean(cuts) < 0.15:
        warnings.append("컷 길이 편차 < 15% → 변동 늘리기")

    # 4. 자막 위치
    for t in recipe.text_ops:
        if t.clip_settings in ["center", "title-center"] and not t.is_emphasis:
            warnings.append("정중앙 자막 과다 → lower-third")

    # 5. LUT intensity
    for f in recipe.filter_ops:
        if f.intensity > 0.7:
            warnings.append(f"필터 intensity {f.intensity} > 0.7 → 0.3~0.5")

    # 6. BGM 볼륨
    if recipe.has_narration and recipe.bgm_volume > 0.2:
        errors.append(f"나레이션 있는데 BGM {recipe.bgm_volume} > 0.2 → 0.15")

    # 7. ChatGPT 어휘
    BAD_KO = ["파헤쳐보겠습니다", "함께 알아보겠습니다", "이번 영상에서는", "결론적으로 말씀드리면"]
    BAD_EN = ["delve", "furthermore", "moreover", "in conclusion", "leverage", "utilize", "pivotal"]
    for sub in recipe.subtitles:
        for w in BAD_KO + BAD_EN:
            if w in sub.text:
                warnings.append(f"ChatGPT 어휘 '{w}' → 구어체")

    return {"errors": errors, "warnings": warnings}
```

**사용**: 렌더 직전 호출 → `errors` 있으면 **빌드 차단**, `warnings`는 사용자에게 보고.

## 9. 통과 체크리스트 (10개)

TOP 5 + 카테고리별 대표 1개 = **10개만 통과해도 티 거의 없음**:

1. ☐ Pretendard/Montserrat 폰트
2. ☐ 인트로 클리셰 차단
3. ☐ TTS 후처리 (room tone + pause + EQ)
4. ☐ 컷 길이 변동 ±30%
5. ☐ 자막 lower-third 디폴트
6. ☐ dissolve 5% 이하
7. ☐ saturation 0.30 상한
8. ☐ BGM 볼륨 -18~-20 dB (나레이션 0.15)
9. ☐ ChatGPT 어휘 구어체 변환
10. ☐ AI 영상 클립 3초 이하

## 출처

- Pictory, Synthesia, InVideo AI 결과 분석
- YouTube "AI slop", "how to spot AI video" 분석
- Reddit r/editors, r/VideoEditing
- 한국: 뉴스토마토 "AI 슬롭 덮친 쇼츠 생태계"
