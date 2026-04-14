"""IngestSource 팩토리.

환경 변수:
    INGEST_SOURCE=auto (기본) | file | jira

자동 감지 (auto):
    1. data/jira_fetch/ 에 JSON 파일 있음  → FileIngestSource
    2. JIRA_URL + JIRA_TOKEN 환경 변수 있음 → JiraIngestSource
    3. 둘 다 없음                           → FileIngestSource (빈 상태, UI에서 안내)
"""
from __future__ import annotations

import os
from pathlib import Path

from src.ingest.base import IngestSource

_FETCH_DIR = Path("data/jira_fetch")


def get_ingest_source(mode: str | None = None) -> IngestSource:
    """IngestSource 인스턴스 반환.

    Args:
        mode: 'auto' | 'file' | 'jira'. None이면 INGEST_SOURCE 환경 변수 사용.
    """
    resolved = mode or os.getenv("INGEST_SOURCE", "auto")

    if resolved == "file":
        from src.ingest.file_source import FileIngestSource
        return FileIngestSource()

    if resolved == "jira":
        from src.ingest.jira_source import JiraIngestSource
        return JiraIngestSource()

    if resolved == "auto":
        return _auto_detect()

    raise ValueError(
        f"지원하지 않는 INGEST_SOURCE: '{resolved}'. "
        f"지원 목록: auto | file | jira"
    )


def detect_mode() -> str:
    """현재 환경에서 사용 가능한 소스 모드를 문자열로 반환.

    Returns:
        'file' | 'jira' | 'none'
    """
    if _has_json_files():
        return "file"
    if _has_jira_env():
        return "jira"
    return "none"


def _auto_detect() -> IngestSource:
    if _has_json_files():
        from src.ingest.file_source import FileIngestSource
        return FileIngestSource()
    if _has_jira_env():
        from src.ingest.jira_source import JiraIngestSource
        return JiraIngestSource()
    # 둘 다 없으면 FileIngestSource 반환 (UI에서 파일 없음 안내)
    from src.ingest.file_source import FileIngestSource
    return FileIngestSource()


def _has_json_files() -> bool:
    return _FETCH_DIR.exists() and bool(list(_FETCH_DIR.glob("*.json")))


def _has_jira_env() -> bool:
    return bool(os.getenv("JIRA_URL")) and bool(os.getenv("JIRA_TOKEN"))
