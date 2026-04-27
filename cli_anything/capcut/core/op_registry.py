"""Operation 레지스트리.

Session에 기록되는 op 이름과 그 분류를 정의. MVP에서는 핵심 op만 포함.
"""

from __future__ import annotations

# 세그먼트를 "생성"하는 op. 트랙 상의 segment_ref 계산과 `auto` 시작 계산에 사용.
CREATION_OPS: set[str] = {
    "add_video",
    "add_image",
    "add_audio",
    "add_text",
    "add_sticker",
    "add_effect",        # effect도 트랙 세그먼트
    "add_filter",        # filter도 트랙 세그먼트
}

# 세그먼트를 장식/수정만 하는 op. 생성은 아니지만 시간 범위가 있음.
MODIFIER_OPS: set[str] = {
    "add_video_transition",
    "add_video_fade",
    "add_video_keyframe",
    "add_video_animation",
    "add_text_animation",
    "add_audio_effect",
    "add_audio_fade",
}

# 시간(start/duration)을 가진 op. offset shifting과 timeline 분석에 사용.
TIMED_SEGMENT_OPS: set[str] = CREATION_OPS | MODIFIER_OPS

# save() 시 draft_content.json을 후처리(직접 패치)해야 하는 op.
# pyCapCut이 제대로 반영 못 하는 필드 대응:
#   - 버그 #17: text add --font   (폰트 미적용)
#   - 버그 #18: text add --border (테두리 색 미적용)
#   - 버그 #19: text add --shadow (그림자 미적용)
#   - 버그 #20: text add --color  ("None" 문자열로 저장됨)
#   - 버그 #21: text 위치 옵션 부재 → clip.transform 직접 패치
POSTPROCESS_OPS: set[str] = {
    "text_style_patch",      # font_path, border_*, shadow_*, font_color 패치
    "text_transform_patch",  # clip.transform.x/y 패치
    "color_adjust",          # 밝기/대비/채도/온도/하이라이트/그림자 (Phase 11)
    "color_wheels",          # shadows/midtones/highlights 색조 (Phase 11)
    # v0.3 복원 (v0.4.3)
    "set_reverse",           # 역재생 플래그
    "set_freeze_frame",      # 프리즈 프레임 (speed=0)
    "set_blend_mode",        # 블렌드 모드 (track_attribute.blend_mode)
    "set_chroma_key",        # 크로마 키 / 그린스크린
    # v0.3 복원 (v0.4.4)
    "add_lut",               # LUT 파일 적용 (materials.video_luts + enable_lut)
    "set_speed_curve",       # 속도 커브 (speed material curve 모드 + 포인트)
    "add_color_curves",      # 컬러 커브 (materials.color_curves + enable_color_curves)
    "add_hsl_adjust",        # HSL 채널별 조정 (materials.material_colors + enable_color_correct_adjust)
}
