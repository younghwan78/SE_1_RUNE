# Req-Tracker AI — MBSE Traceability Knowledge Graph POC

**Ulysses Camera HAL** 프로젝트의 MBSE 추적성 관리를 AI + Knowledge Graph로 자동화하는 POC.  
기존 JIRA flat list 방식의 한계를 시각적으로 비교하고, 숨겨진 연결 누락·충돌을 자동 탐지합니다.

---

## 빠른 시작 (Demo — Dummy Data)

### 사전 요구사항

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 패키지 매니저

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# Windows PowerShell:
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 설치

```bash
git clone https://github.com/younghwan78/SE_1_RUNE.git
cd SE_1_RUNE

# 의존성 설치 (uv가 자동으로 venv 생성)
uv sync
```

### 실행

```bash
# 방법 1 — uv run (권장)
uv run streamlit run src/ui/app.py

# 방법 2 — 직접 실행
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # macOS/Linux
streamlit run src/ui/app.py
```

브라우저에서 `http://localhost:8501` 접속.

> **참고**: 기본값은 `DATASOURCE_MODE=dummy`이므로 `.env` 없이 즉시 실행 가능합니다.

---

## 데모 시나리오 (권장 순서)

| 순서 | 페이지 | 목적 |
|------|--------|------|
| 1 | 📋 Flat View | 기존 JIRA 방식의 한계 체험 — 수작업 교차 확인의 고통 |
| 2 | 🕸️ Graph View | AI 구성 Knowledge Graph 시각화 — 숨겨진 연결 즉시 파악 |
| 3 | ⚙️ Agent Run | LLM 파이프라인 실행 (Phase 1 구현 후 활성화) |
| 4 | ✅ Approvals | Human-in-the-Loop 승인 워크플로우 |
| 5 | 📊 Metrics | Before/After KPI 비교 |

### Graph View 조작법

- **hover**: 노드/엣지 위에 마우스를 올리면 상세 툴팁 표시
- **click**: 노드/엣지 클릭 시 고정 팝업 패널 표시 (✕로 닫기)
- **drag**: 노드를 드래그하여 위치 재배치
- **scroll**: 마우스 휠로 확대/축소
- **사이드바 필터**: 노드 타입별 표시/숨김, 고아 노드 강조, AI 추론 엣지 전용 보기

---

## 프로젝트 구조

```
src/
  models/          # OntologyNode, OntologyEdge, ProposedUpdate, GapFinding
  datasource/      # DataSourceAdapter → DummyAdapter | JiraAdapter
  graph/           # GraphBackend → NetworkXBackend | Neo4jBackend
  agent/           # LangGraph 파이프라인 (Phase 1)
  staging/         # SQLite 승인 큐
  metrics/         # KPI 계산 엔진
  ui/
    app.py         # Streamlit 진입점
    pages/         # 5페이지 UI
    components/    # graph_renderer.py (pyvis), styles.py
data/dummy/        # ulysses_tickets.json (18개 시나리오 티켓)
```

---

## 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 필요한 값 입력
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATASOURCE_MODE` | `dummy` | `dummy` \| `jira` |
| `GRAPH_BACKEND` | `networkx` | `networkx` \| `neo4j` |
| `ANTHROPIC_API_KEY` | — | Claude API 키 (Agent Run 페이지 사용 시) |
| `JIRA_URL` | — | JIRA 서버 URL (JIRA 모드 시) |
| `JIRA_EMAIL` | — | JIRA 계정 이메일 |
| `JIRA_TOKEN` | — | JIRA API 토큰 또는 PAT |
| `JIRA_PROJECT_KEY` | — | JIRA 프로젝트 키 (예: `CAM`) |

> JIRA 연동 상세 가이드: [`docs/jira_integration_guide.md`](docs/jira_integration_guide.md)

---

## 데모 데이터 (Ulysses Camera HAL)

**도메인**: Sony IMX789 센서 / 4K60 파이프라인 / HDR TME

18개 가상 JIRA 티켓에 **의도적으로 심어둔 지식 갭** 8개:

| Gap | 유형 | 설명 |
|-----|------|------|
| G-01 | 충돌 | CAM-020/021이 동시에 CAM-010 구현 주장 |
| G-02 | 충돌 | CAM-022 DVFS 스파이크가 CAM-001 레이턴시 예산 위협 |
| G-03 | 고아 노드 | CAM-023 MIPI 스펙에 부모 요구사항 없음 |
| G-04 | 고아 노드 | CAM-050 3A 알고리즘에 요구사항/아키텍처/검증 없음 |
| G-05 | 검증 누락 | CAM-010 아키텍처에 직접 검증 없음 |
| G-06 | 검증 누락 | CAM-023 MIPI 스펙 검증 계획 없음 |
| G-07 | 구현 누락 | CAM-051 GDPR 요구사항을 구현하는 설계 없음 |
| G-08 | 교차 영역 | CAM-041 메모리 버그 → CAM-001 레이턴시 간접 영향 |

---

## Phase 로드맵

- [x] **Phase 0**: 기반 인프라 + 5페이지 Streamlit UI + pyvis 그래프
- [ ] **Phase 1**: LangGraph 파이프라인 (`src/agent/`) — 갭 G-01~G-08 자동 탐지
- [ ] **Phase 2**: JIRA REST API 실데이터 연동 (`DATASOURCE_MODE=jira`)
- [ ] **Phase 3**: Neo4j 프로덕션 백엔드 (`GRAPH_BACKEND=neo4j`)

---

## 기술 스택

| 영역 | 라이브러리 |
|------|-----------|
| UI | Streamlit |
| 그래프 시각화 | pyvis (vis.js 9.1.2) |
| 그래프 DB (데모) | NetworkX |
| 그래프 DB (프로덕션) | Neo4j |
| LLM 오케스트레이션 | LangGraph + langchain-anthropic |
| 데이터 검증 | Pydantic v2 + instructor |
| 패키지 관리 | uv |
