# CapCut 하네스 메모

`pyCapCut` 라이브러리 기반. CapCut / 剪映(JianYing) draft 생성기의 파이썬 포트.

## 핵심 객체
| 클래스 | 역할 |
|--------|------|
| `DraftFolder(folder_path)` | 드래프트 폴더 루트. `create_draft(name, w, h, fps)`로 `ScriptFile` 반환 |
| `ScriptFile(w, h, fps)` | 드래프트 하나. `add_track`, `add_segment`, `save()`, `dump(path)` |
| `VideoSegment / AudioSegment / TextSegment / StickerSegment` | 타임라인 세그먼트 |
| `TrackType` | 비디오/오디오/텍스트/효과/필터/스티커 트랙 구분 |

## 드래프트 폴더 기본 경로
- **Windows CapCut (글로벌)**: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
- **Windows 剪映 (중문)**: `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft`
- **Mac CapCut**: `~/Movies/CapCut/User Data/Projects/com.lveditor.draft`

## Session 모델 (재구성 중)
이벤트 소스: 사용자 커맨드를 JSON op log로 기록하고, 매번 전체 log를 replay해서 `ScriptFile`을 다시 빌드.

```json
{
  "schema_version": 2,
  "draft_folder": "...",
  "draft_name": "...",
  "width": 1920, "height": 1080, "fps": 30,
  "operations": [
    {"id": "op_1", "op": "add_track", "args": {"type": "video", "name": "V1"}},
    {"id": "op_2", "op": "add_video", "args": {"file": "...", "start": "0s", "duration": "5s", "track": "V1"}}
  ]
}
```

## 알려진 이슈 (재구현 시 수정)
1. `tim("3000000")`이 0을 반환하는 pyCapCut 버그 → `parse_time_value()` 래퍼로 처리
2. `replay` 경로에서 트랙 자동 생성이 안 되어 `add_track` 먼저 필요
3. 별칭 매핑과 실제 pyCapCut enum이 어긋남 (dissolve → 溶解 대신 叠化 등)

전체 22개 버그 목록은 CHANGELOG 참조.
