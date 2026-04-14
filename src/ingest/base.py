"""IngestSource — 모든 소스 어댑터의 추상 기반 클래스."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.raw_document import RawDocument


class IngestSource(ABC):
    """소스 독립 수집 인터페이스.

    JIRA, Confluence, Email 등 어떤 소스든 이 ABC를 구현하면
    동일한 분류 파이프라인에서 처리된다.

    구현 필수 메서드:
        test_connection()       — 연결 확인 (Step 1)
        fetch_candidate_count() — 처리 가능 문서 수 조회 (Step 2)
        fetch_documents()       — 문서 수집 (Step 3)
        fetch_updated_since()   — 증분 동기화

    선택 메서드:
        list_document_types()   — 소스의 문서 타입 목록 (디버깅/설정용)
    """

    source_name: str = "unknown"

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """연결 상태 확인.

        Returns:
            (success, message) — 성공 여부와 상세 메시지.
        """
        ...

    @abstractmethod
    def fetch_candidate_count(
        self,
        project_key: str,
        domain_keywords: list[str],
    ) -> int:
        """필터 조건에 맞는 처리 가능 문서 수 반환 (is_processable 기준).

        Args:
            project_key:     프로젝트/공간 식별자
            domain_keywords: 도메인 키워드 목록 (OR 조건으로 필터)
        """
        ...

    @abstractmethod
    def fetch_documents(
        self,
        project_key: str,
        domain_keywords: list[str],
        max_results: int = 200,
    ) -> list[RawDocument]:
        """조건에 맞는 RawDocument 목록 반환.

        is_processable = False 인 문서는 여기서 걸러서 반환하지 않는다.
        """
        ...

    @abstractmethod
    def fetch_updated_since(
        self,
        project_key: str,
        since_iso: str,
    ) -> list[RawDocument]:
        """증분 동기화 — since_iso 이후 변경된 문서만 반환.

        Args:
            since_iso: ISO 8601 문자열 (예: "2024-01-01T00:00:00")
        """
        ...

    def list_document_types(self, project_key: str) -> list[dict[str, str]]:
        """소스의 문서/이슈 타입 목록 반환 (선택 구현).

        타입 매핑 확인 및 디버깅 용도.
        Returns: [{"id": "...", "name": "...", "description": "..."}, ...]
        """
        return []
