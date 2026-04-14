"""ClassificationEngine — Pass 1: RawDocument → MBSE 타입 분류.

분류 우선순위:
  1. 키워드 스코어링 (신뢰도 ≥ 0.65 → 확정, LLM 호출 없음)
  2. LLM 분류      (키워드 불확실 시)
  3. Epic 기본값   (키워드도 LLM도 낮은 신뢰도 → Requirement, needs_review=True)

신뢰도 임계값:
  LLM_REVIEW_THRESHOLD = 0.75 → 미만이면 needs_review = True → UI 검토 플래그
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from pydantic import BaseModel, Field

from src.classification.keywords import keyword_classify
from src.models.raw_document import RawDocument

logger = logging.getLogger(__name__)

_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
_VALID_TYPES = frozenset({"Requirement", "Architecture_Block", "Design_Spec", "Verification", "Issue"})


# ── 결과 모델 ─────────────────────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    """Pass 1 분류 결과."""
    doc_id: str
    mbse_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    method: str = Field(description="'keyword' | 'llm' | 'epic_default'")
    needs_review: bool = False


# ── 엔진 ──────────────────────────────────────────────────────────────────────

class ClassificationEngine:
    """Pass 1 분류 엔진.

    사용법:
        engine = ClassificationEngine(domain_context="카메라 HAL 시스템 엔지니어링")
        results = engine.classify_batch(documents, log_fn=st.write)
    """

    KEYWORD_THRESHOLD: float = 0.65   # 키워드로 확정하는 최소 신뢰도
    LLM_REVIEW_THRESHOLD: float = 0.75  # 이 미만이면 사용자 검토 필요

    def __init__(self, domain_context: str = "") -> None:
        """
        Args:
            domain_context: 도메인 설명 (LLM 프롬프트에 주입).
                            예: "카메라 HAL SoC 시스템 엔지니어링, 4K 파이프라인"
        """
        self._domain_context = domain_context
        self._llm_client = None

    # ── Public API ────────────────────────────────────────────────────────────

    def classify_batch(
        self,
        documents: list[RawDocument],
        log_fn: Callable[[str], None] | None = None,
    ) -> list[ClassificationResult]:
        """문서 배치를 분류하여 결과 반환.

        - 키워드로 분류 가능한 것은 LLM 호출 없이 처리
        - 나머지만 LLM 배치 호출
        """
        results: list[ClassificationResult] = []
        llm_queue: list[RawDocument] = []

        for doc in documents:
            result = self._try_keyword_classify(doc)
            if result:
                results.append(result)
                if log_fn:
                    review_mark = " ⚠️ 검토필요" if result.needs_review else ""
                    log_fn(f"  [키워드] {doc.id}: {result.mbse_type} ({result.confidence:.0%}){review_mark}")
            else:
                llm_queue.append(doc)

        if llm_queue:
            if log_fn:
                log_fn(f"  → LLM 분류 대상: {len(llm_queue)}개 (키워드 신뢰도 낮음)")
            llm_results = self._llm_classify_batch(llm_queue, log_fn)
            results.extend(llm_results)

        return results

    def apply_user_corrections(
        self,
        results: list[ClassificationResult],
        corrections: dict[str, str],
    ) -> list[ClassificationResult]:
        """사용자 수정 반영.

        Args:
            corrections: {doc_id: corrected_mbse_type}
        """
        updated = []
        for r in results:
            if r.doc_id in corrections:
                corrected_type = corrections[r.doc_id]
                updated.append(r.model_copy(update={
                    "mbse_type": corrected_type,
                    "reasoning": f"[USER_CORRECTED] {r.reasoning}",
                    "needs_review": False,
                }))
            else:
                updated.append(r)
        return updated

    # ── 키워드 분류 ───────────────────────────────────────────────────────────

    def _try_keyword_classify(self, doc: RawDocument) -> ClassificationResult | None:
        """키워드 스코어링 시도. 신뢰도 부족 시 None 반환."""
        kw_type, kw_conf = keyword_classify(doc.title, doc.body, doc.labels)

        # Epic이지만 키워드 신뢰도 없음 → Requirement 기본값 (낮은 신뢰도)
        if doc.jira_issue_type in ("Epic", "에픽") and not kw_type:
            return ClassificationResult(
                doc_id=doc.id,
                mbse_type="Requirement",
                confidence=0.55,
                reasoning="Epic 타입 → Requirement 기본 분류 (키워드 신호 없음, 검토 필요)",
                method="epic_default",
                needs_review=True,
            )

        if kw_type:
            return ClassificationResult(
                doc_id=doc.id,
                mbse_type=kw_type,
                confidence=kw_conf,
                reasoning=f"키워드 스코어링: '{kw_type}' (신뢰도 {kw_conf:.2f})",
                method="keyword",
                needs_review=kw_conf < self.LLM_REVIEW_THRESHOLD,
            )

        return None  # LLM으로 위임

    # ── LLM 분류 ──────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._llm_client is None:
            import instructor
            from anthropic import Anthropic
            self._llm_client = instructor.from_anthropic(
                Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            )
        return self._llm_client

    def _llm_classify_batch(
        self,
        documents: list[RawDocument],
        log_fn: Callable[[str], None] | None = None,
    ) -> list[ClassificationResult]:
        """LLM으로 배치 분류."""

        class _Single(BaseModel):
            id: str
            mbse_type: str = Field(
                description="Requirement | Architecture_Block | Design_Spec | Verification | Issue"
            )
            confidence: float = Field(ge=0.0, le=1.0)
            reasoning: str = Field(description="제목/내용 기반 분류 이유 (1~2문장)")

        class _Batch(BaseModel):
            classifications: list[_Single]

        summaries = [
            {
                "id": d.id,
                "jira_type": d.jira_issue_type,
                "title": d.title,
                "body_preview": d.body[:500],
                "labels": d.labels,
            }
            for d in documents
        ]

        user_msg = f"""다음 문서들을 MBSE 타입으로 분류하세요.

{json.dumps(summaries, ensure_ascii=False, indent=2)}

각 문서에 대해:
- mbse_type: Requirement | Architecture_Block | Design_Spec | Verification | Issue 중 정확히 하나
- confidence: 0.0~1.0 (내용이 명확하면 높게, 모호하면 낮게)
- reasoning: 제목/내용 기반 분류 근거 (1~2문장)
"""

        try:
            client = self._get_client()
            batch_result: _Batch = client.messages.create(
                model=_MODEL,
                max_tokens=2048,
                system=self._build_system_prompt(),
                messages=[{"role": "user", "content": user_msg}],
                response_model=_Batch,
                max_retries=2,
            )

            results = []
            clf_map = {c.id: c for c in batch_result.classifications}
            for doc in documents:
                clf = clf_map.get(doc.id)
                if clf is None:
                    # LLM 응답에서 누락된 경우 fallback
                    results.append(ClassificationResult(
                        doc_id=doc.id,
                        mbse_type="Design_Spec",
                        confidence=0.0,
                        reasoning="LLM 응답 누락 — fallback",
                        method="llm",
                        needs_review=True,
                    ))
                    continue

                mbse_type = clf.mbse_type if clf.mbse_type in _VALID_TYPES else "Design_Spec"
                result = ClassificationResult(
                    doc_id=doc.id,
                    mbse_type=mbse_type,
                    confidence=clf.confidence,
                    reasoning=clf.reasoning,
                    method="llm",
                    needs_review=clf.confidence < self.LLM_REVIEW_THRESHOLD,
                )
                results.append(result)

                if log_fn:
                    review_mark = " ⚠️ 검토필요" if result.needs_review else " ✅"
                    log_fn(
                        f"  [LLM] {doc.id}: {mbse_type} "
                        f"({clf.confidence:.0%}){review_mark}"
                    )

            return results

        except Exception as exc:
            logger.error("LLM 분류 배치 실패: %s", exc)
            return [
                ClassificationResult(
                    doc_id=d.id,
                    mbse_type="Design_Spec",
                    confidence=0.0,
                    reasoning=f"LLM 실패 fallback: {exc}",
                    method="llm",
                    needs_review=True,
                )
                for d in documents
            ]

    def _build_system_prompt(self) -> str:
        domain_section = (
            f"\n\n## 도메인 컨텍스트\n{self._domain_context}"
            if self._domain_context
            else ""
        )
        return f"""You are a senior MBSE analyst. Classify engineering documents into MBSE ontology types based on CONTENT, not the issue type label.

## MBSE Types

**Requirement** — What the system MUST do.
  - "shall", "must", performance specs, compliance mandates, constraints
  - 한국어: 요구사항, 요건, 규격, 성능 요구

**Architecture_Block** — How the system is STRUCTURED.
  - Modules, interfaces, subsystems, HW/SW partitioning, design decisions
  - 한국어: 아키텍처, 모듈, 인터페이스, 서브시스템

**Design_Spec** — HOW something is implemented.
  - Algorithms, drivers, APIs, register maps, code-level details
  - 한국어: 구현, 상세 설계, 알고리즘

**Verification** — Evidence that requirements are met.
  - Test cases, benchmarks, V&V activities, compliance tests
  - 한국어: 시험, 검증, 테스트

**Issue** — Problems and risks.
  - Bugs, defects, blockers, risks, known limitations
  - 한국어: 버그, 결함, 위험, 장애

## Rules
- Classify by CONTENT, not JIRA issue type (the label is often wrong)
- confidence < 0.75 if the content is ambiguous
- confidence < 0.60 if very unclear (user review needed){domain_section}"""
