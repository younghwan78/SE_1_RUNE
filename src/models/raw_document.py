"""Source-agnostic document model.

모든 IngestSource(JIRA, Email, Confluence 등)가 공통으로 반환하는 모델.
Classification 파이프라인은 소스 종류를 몰라도 동작한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawDocument(BaseModel):
    """소스 독립 문서 모델."""

    # ── 공통 필드 ─────────────────────────────────────────────────────────────
    id: str = Field(description="문서 고유 ID (JIRA: 'CAM-001', Email: 'msg-uuid')")
    source: str = Field(description="소스 종류: 'jira' | 'email' | 'confluence'")
    title: str = Field(description="제목 (JIRA: summary, Email: subject)")
    body: str = Field(description="평문화된 본문")
    url: str = Field(default="", description="원본 링크")
    author: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    # ── 계층 / 관계 정보 ──────────────────────────────────────────────────────
    parent_id: str | None = Field(default=None, description="상위 문서 ID (JIRA Epic Link)")
    child_ids: list[str] = Field(default_factory=list, description="하위 문서 ID 목록")
    related_ids: list[str] = Field(default_factory=list, description="연결 문서 ID (issuelinks 등)")

    # ── 보조 신호 ─────────────────────────────────────────────────────────────
    labels: list[str] = Field(default_factory=list, description="레이블 (없을 수 있음)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="소스별 추가 필드")

    # ── 필터링 ────────────────────────────────────────────────────────────────

    @property
    def is_processable(self) -> bool:
        """제목과 본문이 모두 있어야 처리 가능.

        빈 Epic, description 없는 Task/Subtask는 파이프라인에서 제외.
        """
        return bool(self.title.strip()) and bool(self.body.strip())

    @property
    def text_for_classification(self) -> str:
        """LLM 분류에 넘길 통합 텍스트."""
        parts = [f"Title: {self.title}"]
        if self.labels:
            parts.append(f"Labels: {', '.join(self.labels)}")
        if self.body:
            parts.append(f"Body:\n{self.body[:800]}")
        return "\n".join(parts)

    @property
    def jira_issue_type(self) -> str:
        """JIRA 이슈 타입 (metadata에서 추출, 없으면 빈 문자열)."""
        return self.metadata.get("jira_type", "")
