"""cli-anything-capcut — CapCut CLI 하네스."""

# 소스에 적힌 버전이 단일 진실이다. pyproject 가 이 값을 읽어가므로 중복이 없다.
#
# 설치 메타데이터(importlib.metadata)를 먼저 보던 때는 editable 설치나 오래된
# 설치가 남아 있으면 `diagnose` 가 실제 코드와 다른 버전을 보고했다(실측: 코드는
# 0.5.5 인데 0.4.1 로 출력). 진단 명령이 틀린 값을 말하면 그걸로 판단하는 사람이
# 잘못된 결론을 낸다. 그래서 소스를 먼저 믿고, 설치본과 다르면 함께 알린다.
__version__ = "0.5.7"


def installed_version() -> str | None:
    """설치된 배포판이 보고하는 버전. 설치되어 있지 않으면 None."""
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    try:
        return _pkg_version("cli-anything-capcut")
    except PackageNotFoundError:
        return None
