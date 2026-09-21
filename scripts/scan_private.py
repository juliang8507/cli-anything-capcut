"""공개 저장소에 들어가면 안 되는 문자열을 스캔한다.

이 저장소는 개인 개발본에서 공개본으로 주기적으로 동기화된다. 동기화할 때마다
사람이 기억해서 익명화하는 방식은 언젠가 실패하므로, CI 게이트로 막는다.

Run::

    python scripts/scan_private.py

git 이 추적하는 파일만 본다. 위반이 하나라도 있으면 종료 코드 1.
"""

from __future__ import annotations

import sys as _sys

# 위반 내용에 한글이 섞인다. 영어 로캘 Windows(cp1252) 에서 죽지 않도록 고정.
for _stream in (_sys.stdout, _sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# (이름, 정규식, 설명) — 공개되면 안 되는 것.
PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("실명(한글)", r"기훈", "개인 실명"),
    ("실명(영문)", r"(?i)park\s*kihoon|parkkihoon", "개인 실명"),
    ("이메일", r"[\w.+-]+@(?:gmail|naver|daum|kakao)\.com", "개인 이메일"),
    ("개인 작업 경로", r"[A-Za-z]:[\\/]+main\b", "E:/main, D:/main 등 로컬 허브"),
    # 주의: `D:/촬영/` 같은 한글 경로 일반은 잡지 않는다. 한글 경로 처리가
    # 이 도구의 핵심 기능이라 문서 예제와 테스트 데이터에 정상적으로 등장한다.
    # 오탐으로 게이트가 자주 깨지면 아무도 게이트를 믿지 않게 된다.
    # 실제로 위험한 것은 사용자 폴더명과 개인 허브 하위 폴더다.
    ("한글 사용자 폴더", r"[Uu]sers[\\/]+[가-힣]", r"C:\Users\<한글이름>"),
    ("개인 폴더", r"_연구|_소재|_임시", "메인 허브 하위 폴더"),
    ("타 프로젝트", r"써니데이|마음결|maeumgyeol", "개인 프로젝트 고유명"),
    ("API 키", r"sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[\w-]{20,}", "비밀키"),
    ("비밀 대입", r"(?i)(api[_-]?key|secret|password)\s*=\s*[\"'][^\"'\s]{12,}", "하드코딩된 비밀"),
)

# 정당한 예외. 위 패턴에 걸리지만 공개해도 되는 것.
ALLOWED: tuple[str, ...] = (
    "juliang8507",            # 공개 저장소 계정명
    "<non-ASCII name>",       # 익명화된 표현 그 자체
    "runneradmin",            # GitHub Actions 러너 사용자
    "C:/Users/test/",         # 테스트 픽스처의 가짜 경로
    "C:\\Users\\test\\",
)

# 스캔에서 제외할 경로 (바이너리/생성물).
SKIP_SUFFIXES = {".ttf", ".otf", ".ttc", ".png", ".jpg", ".gif", ".mp4", ".mp3", ".ico", ".pyc"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    files = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = REPO_ROOT / line
        if path.suffix.casefold() in SKIP_SUFFIXES:
            continue
        if path.is_file():
            files.append(path)
    return files


def scan() -> int:
    compiled = [(name, re.compile(pattern), note) for name, pattern, note in PATTERNS]
    violations: list[tuple[str, int, str, str]] = []

    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, regex, _note in compiled:
                match = regex.search(line)
                if match is None:
                    continue
                if any(allowed in line for allowed in ALLOWED):
                    continue
                violations.append((rel, lineno, name, line.strip()[:120]))

    if not violations:
        print(f"OK: {len(tracked_files())} 개 추적 파일에서 위반 0 건")
        return 0

    print(f"공개 금지 문자열 {len(violations)} 건:")
    print()
    for rel, lineno, name, snippet in violations:
        print(f"  {rel}:{lineno}")
        print(f"    [{name}] {snippet}")
    print()
    print("공개 저장소에 올리기 전에 위 내용을 익명화하거나 제거할 것.")
    print("정당한 예외라면 scripts/scan_private.py 의 ALLOWED 에 추가한다.")
    return 1


if __name__ == "__main__":
    sys.exit(scan())
