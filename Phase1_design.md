# Phase 1 Design: Source-Agnostic MBSE Ingestion Pipeline

## 배경 및 문제 정의

사내 JIRA는 MBSE 표준 이슈 타입을 따르지 않는다.
- 모든 작업이 Epic / Task / Subtask / Story로만 구성됨
- 이슈 타입으로 Requirement, Architecture_Block 등 구분 불가
- Label은 보조 신호일 뿐, 없는 경우도 많음
- **결론: 제목 + 본문 내용 기반으로 분류해야 함**

향후 Email, Confluence 등 다양한 소스를 추가할 계획이므로
**소스 독립적(source-agnostic) 파이프라인** 설계가 필수.

---

## 아키텍처 개요

```
Layer 1 — Ingest (소스별 어댑터)
  JiraIngestSource       ← 현재
  ConfluenceIngestSource ← 미래
  EmailIngestSource      ← 미래

        ↓ 모두 RawDocument 반환

Layer 2 — Classification Engine (Pass 1)
  키워드 스코어링 → 신뢰도 ≥ 0.65: 확정
  LLM 분류       → 신뢰도 ≥ 0.75: 확정, 미만: 검토 플래그

        ↓ 사용자 1차 검증 (Step 3.5)

Layer 3 — Relationship Inference (Pass 2)
  JIRA 계층 구조 + 분류 타입 조합 → 관계 패턴 매칭
  LLM 관계 추론 (분류 결과를 컨텍스트로 활용)

        ↓ 사용자 최종 검증 (Step 5)

Layer 4 — Knowledge Graph
  NetworkXBackend (현재) / Neo4jBackend (미래)
```

---

## 핵심 모델: RawDocument

```python
class RawDocument(BaseModel):
    id: str                      # JIRA: "CAM-001", Email: "msg-uuid"
    source: str                  # "jira" | "email" | "confluence"
    title: str                   # JIRA: summary, Email: subject
    body: str                    # 평문화된 본문
    url: str                     # 원본 링크
    author: str
    created_at: datetime
    parent_id: str | None        # JIRA: Epic link / parent
    child_ids: list[str]
    related_ids: list[str]       # issuelinks, mentions
    labels: list[str]            # 보조 신호 (없을 수 있음)
    metadata: dict[str, Any]     # source-specific 필드

    @property
    def is_processable(self) -> bool:
        return bool(self.title.strip()) and bool(self.body.strip())
```

**필터링 원칙**: `is_processable = False`인 문서(빈 Epic, description 없는 Task)는 파이프라인에서 제외.

---

## 2-Pass 분류 전략

### Pass 1: Content-based Classification

```
Epic → 기본 Requirement (키워드로 보정)
Task/Subtask → 키워드 스코어링 우선, 불확실 시 LLM
Story → 키워드 스코어링, 불확실 시 LLM

신뢰도 임계값:
  keyword ≥ 0.65 → 확정 (LLM 호출 없음, 비용 절감)
  llm ≥ 0.75    → 확정
  llm < 0.75    → needs_review = True → UI에서 사용자 수정
```

키워드 가중치:
- 제목(title): 3
- 레이블(labels): 2
- 본문(body): 1

### Pass 2: Relationship Inference

분류 결과 + JIRA 계층 구조로 관계 패턴 자동 매핑:

| JIRA 구조 | 타입 조합 | 추론 관계 |
|---|---|---|
| Epic → Task | Req → ArchBlock | allocates |
| Epic → Task | Req → DesignSpec | decomposes |
| Task → Subtask | ArchBlock → DesignSpec | realizes |
| Task → Subtask | DesignSpec → Verification | verifies |
| issuelink (blocks) | any → Issue | affects |

불명확한 관계 → LLM 추론 (Pass 1 타입 결과를 컨텍스트로 포함)

---

## 5단계 반복 워크플로

```
Step 1: JIRA MCP / REST API 연결 확인
        - 토큰 설정 → 연결 테스트
        - 이슈 타입 목록 조회

Step 2: 프로젝트 + 도메인 키워드 설정
        - project_key 입력
        - domain keyword 입력 (JQL text~ 필터)
        - 처리 가능한 이슈 수 미리보기 (is_processable 기준)

Step 3: LLM 1차 분류 실행
        - 배치 단위 처리
        - 키워드 → LLM 순서로 분류
        - 신뢰도 분포 표시

Step 3.5: 사용자 분류 검증 (필수)
        - 분류 결과 테이블 제시
        - needs_review 항목 강조
        - 사용자 수정 → 확정 분류 풀 생성
        (오류 분류된 채로 Pass 2 진행 시 연쇄 오류 발생 방지)

Step 4: Traceability 추론
        - 확정 분류 결과 기반
        - 계층 구조 패턴 매칭 → LLM 추론
        - 엣지 목록 표시

Step 5: 최종 리포트 + 사용자 승인
        - 분류 요약 (타입별 수, 신뢰도 분포)
        - 갭 분석 (검증 없는 요구사항, 고아 노드 등)
        - 트레이서빌리티 체인 완성도
        - 승인 → Knowledge Graph MERGE
```

---

## 확장성 설계 원칙

1. **IngestSource ABC**: 모든 소스는 `RawDocument` 반환. 파이프라인은 소스를 모름.
2. **factory 패턴**: `INGEST_SOURCE=jira|confluence|email` 환경 변수로 전환.
3. **MCP 지원 경로**: `JiraIngestSource`는 REST API 기반. MCP가 가용하면 `JiraMcpSource`로 교체 가능 (동일 ABC 구현).
4. **ClassificationEngine 도메인 컨텍스트**: `domain_context` 파라미터로 도메인별 프롬프트 보강. 카메라, 네트워크, 전력 등 도메인 추가 시 키워드 사전만 확장.

---

## 구현 파일 목록

```
src/
  models/
    raw_document.py              ← RawDocument (소스 독립 모델)
  ingest/
    __init__.py
    base.py                      ← IngestSource ABC
    jira_source.py               ← JiraIngestSource
    factory.py                   ← get_ingest_source()
  classification/
    __init__.py
    keywords.py                  ← 키워드 패턴 + 스코어링
    engine.py                    ← ClassificationEngine (Pass 1)
  ui/
    pages/
      06_ingest_pipeline.py      ← 5-step 워크플로 UI
```

---

## 결정 사항 요약

| 항목 | 결정 |
|---|---|
| 이슈 타입 의존 여부 | 없음. 내용 기반 분류 |
| 빈 Epic/Task 처리 | 파이프라인에서 제외 (is_processable) |
| Label 활용 | 보조 신호 (가중치 2, 없어도 동작) |
| 신뢰도 결정 | LLM이 결정, 사용자 피드백으로 보정 |
| 분류 검증 시점 | Pass 1 완료 후, Pass 2 전에 반드시 수행 |
| 도메인 확장 | keywords.py 키워드 사전 + 프롬프트 컨텍스트 |
| 소스 확장 | IngestSource ABC 구현 추가만으로 확장 |
