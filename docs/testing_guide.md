# 테스트 가이드 — Req-Tracker AI

> 단계별 테스트 절차. API 키 없이 실행 가능한 Phase 0부터 시작하여 AI 파이프라인(Phase 1), JIRA 연동 순서로 진행합니다.

---

## 목차

1. [환경 준비 확인](#1-환경-준비-확인)
2. [Phase 0 — API 키 없이 Dummy 데이터 테스트](#2-phase-0--api-키-없이-dummy-데이터-테스트)
3. [Phase 1 — AI 파이프라인 테스트 (ANTHROPIC_API_KEY 필요)](#3-phase-1--ai-파이프라인-테스트)
4. [JIRA 연동 테스트](#4-jira-연동-테스트)
5. [단위 테스트 스크립트](#5-단위-테스트-스크립트)
6. [통합 테스트 스크립트](#6-통합-테스트-스크립트)
7. [트러블슈팅 체크리스트](#7-트러블슈팅-체크리스트)

---

## 1. 환경 준비 확인

### 1-1. Python 및 uv 버전 확인

```bash
python --version   # 3.11 이상
uv --version       # 0.4 이상
```

### 1-2. 의존성 설치

```bash
uv sync
```

### 1-3. 임포트 체인 전체 검증

```bash
uv run python -c "
import streamlit, networkx, pyvis, pydantic, instructor, langgraph
print('Core packages OK')

from src.models.ontology import OntologyNode, OntologyEdge, ProposedUpdate, GapFinding
from src.models.jira_ticket import JiraTicket
from src.models.graph_state import AgentState
print('Models OK')

from src.datasource.dummy_adapter import DummyAdapter
from src.datasource.factory import get_adapter
from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph
from src.metrics.traceability import MetricsEngine
from src.staging.sqlite_store import StagingStore
print('Infrastructure OK')

from src.agent.prompts import CLASSIFIER_SYSTEM, build_classification_prompt
from src.agent.nodes import _compute_confidence, _guess_relation
from src.agent.edges import batch_complete_check, advance_batch_index
from src.agent.graph import run_pipeline
print('Agent pipeline OK')
"
```

**기대 출력:**
```
Core packages OK
Models OK
Infrastructure OK
Agent pipeline OK
```

---

## 2. Phase 0 — API 키 없이 Dummy 데이터 테스트

### 2-1. 데이터 레이어 검증

```bash
uv run python -c "
from src.datasource.dummy_adapter import DummyAdapter
a = DummyAdapter()
tickets = a.fetch_all_tickets()
edges   = a.fetch_pre_computed_edges()
print(f'티켓: {len(tickets)}개')          # 기대: 18
print(f'사전 엣지: {len(edges)}개')       # 기대: 20
print(f'타입 종류: {sorted({t.type for t in tickets})}')
# 기대: ['Architecture_Block', 'Design_Spec', 'Issue', 'Requirement', 'Verification']

# 특정 티켓 확인
cam001 = next(t for t in tickets if t.id == 'CAM-001')
print(f'CAM-001 타입: {cam001.type}')     # 기대: Requirement
print(f'CAM-001 linked: {cam001.linked_issue_ids}')  # 기대: []
"
```

### 2-2. 그래프 백엔드 검증

```bash
uv run python -c "
from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph

b = get_backend(persist=False)
load_dummy_graph(b)
sg = b.query_full_graph()

print(f'노드: {len(sg.nodes)}개')         # 기대: 18
print(f'엣지: {len(sg.edges)}개')         # 기대: 20
print(f'추론 엣지: {sum(1 for e in sg.edges if e.is_inferred)}개')  # 기대: 4

orphans = b.query_orphan_nodes()
print(f'고아 노드: {len(orphans)}개')     # 기대: 5
print(f'고아 IDs: {sorted([o.id for o in orphans])}')
# 기대: ['CAM-040', 'CAM-041', 'CAM-042', 'CAM-050', 'CAM-051']
"
```

### 2-3. 트레이서빌리티 체인 검증

```bash
uv run python -c "
from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph

b = get_backend(persist=False)
load_dummy_graph(b)

# CAM-001 → ancestors 탐색 (엣지 방향: child→parent)
chain = b.get_traceability_chain('CAM-001')
print(f'CAM-001 체인 경로 수: {len(chain)}')     # 기대: 10 이상
print(f'첫 두 경로: {[[n.id for n in p] for p in chain[:2]]}')

# 도달 가능한 타입 확인
types = b.get_reachable_node_types('CAM-001')
print(f'CAM-001에서 도달 가능 타입: {types}')
# 기대: {'Verification', 'Architecture_Block', 'Design_Spec', 'Issue'}

# 충돌 탐지 (G-01)
conflicts = b.detect_conflicts()
print(f'충돌: {len(conflicts)}개')               # 기대: 1개 (CAM-020/021)
print(f'충돌 노드: {conflicts[0].affected_node_ids}')
# 기대: ['CAM-010', 'CAM-020', 'CAM-021']

# 이웃 노드 조회
neighbors = b.get_neighbors('CAM-010')
print(f'CAM-010 이웃: {sorted(neighbors)}')
# 기대: ['CAM-001', 'CAM-011', 'CAM-020', 'CAM-021', 'CAM-030']
"
```

### 2-4. 메트릭 엔진 검증

```bash
uv run python -c "
from src.graph.factory import get_backend
from src.graph.loader import load_dummy_graph
from src.metrics.traceability import MetricsEngine

b = get_backend(persist=False)
load_dummy_graph(b)
r = MetricsEngine(b).compute_all()

print(f'총 노드:          {r.total_nodes}')         # 기대: 18
print(f'총 엣지:          {r.total_edges}')         # 기대: 20
print(f'커버리지:         {r.coverage_score:.1f}%') # 기대: 25.0%
print(f'고아 노드 비율:   {r.orphan_rate:.1f}%')   # 기대: 27.8%
print(f'검증 커버리지:    {r.verification_coverage:.1f}%')  # 기대: 66.7%
print(f'AI 추론 엣지:     {r.inferred_edges}개')    # 기대: 4
print(f'갭 탐지:          {len(r.gaps)}개')         # 기대: 9
"
```

### 2-5. SQLite 스테이징 큐 검증

```bash
uv run python -c "
import uuid
from src.staging.sqlite_store import StagingStore
from src.models.ontology import OntologyNode, OntologyEdge, ProposedUpdate

s = StagingStore()
print(f'초기 pending: {s.count_pending()}')    # 기대: 0

# enqueue 테스트
node = OntologyNode(id='TEST-001', type='Requirement', name='test', description='test')
edge = OntologyEdge(source_id='TEST-001', target_id='TEST-002', relation='satisfies', reasoning='test')
bid  = uuid.uuid4().hex
upd  = ProposedUpdate(nodes=[node], edges=[edge], confidence_score=0.9, batch_id=bid)
s.enqueue(upd)
print(f'enqueue 후 pending: {s.count_pending()}')  # 기대: 1

# 조회
pending = s.get_pending()
print(f'노드 수: {len(pending[0].nodes)}')    # 기대: 1
print(f'엣지 수: {len(pending[0].edges)}')    # 기대: 1

# 승인
s.mark_approved(bid)
print(f'승인 후 pending: {s.count_pending()}')     # 기대: 0
print('SQLite 스테이징 OK')
"
```

### 2-6. Streamlit UI 전 페이지 확인

```bash
uv run streamlit run src/ui/app.py --server.port 8501
```

브라우저에서 `http://localhost:8501` 접속 후 체크리스트:

| 페이지 | 확인 항목 | 기대 결과 |
|--------|-----------|-----------|
| Home | 메트릭 카드 4개 | Nodes: 18, Edges: 20, Gaps: 9, Coverage: 25% |
| 📋 Flat View | 테이블 표시 | 18개 행, JIRA Type 컬럼, AI Type 컬럼 없음 |
| 📋 Flat View | info 배너 | "AI 분류 결과 없음 — Agent Run 페이지에서..." |
| 📋 Flat View | 타입 필터 | 5가지 타입으로 필터링 동작 |
| 🕸️ Graph View | 그래프 렌더링 | 18개 노드, 물리 시뮬레이션 동작 |
| 🕸️ Graph View | hover tooltip | 마우스 올리면 다크 툴팁 표시 |
| 🕸️ Graph View | click popup | 클릭 시 ✕ 닫기 버튼 있는 패널 표시 |
| 🕸️ Graph View | 사이드바 레전드 | Node Types + Edge Relations 섹션 |
| ⚙️ Agent Run | 환경 상태 표시 | ANTHROPIC_API_KEY 미설정 오류 표시 |
| ⚙️ Agent Run | 실행 버튼 | API 키 없으면 버튼 비활성화 |
| ✅ Approvals | 대기 목록 | 비어있음 또는 이전 테스트 항목 |
| 📊 Metrics | KPI 대시보드 | Before/After 비교 표 |

---

## 3. Phase 1 — AI 파이프라인 테스트

### 3-1. ANTHROPIC_API_KEY 설정

```bash
cp .env.example .env
# .env 파일 편집:
# ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 3-2. 프롬프트 품질 단위 테스트 (API 호출 없음)

```bash
uv run python -c "
from src.agent.prompts import (
    CLASSIFIER_SYSTEM, RELATIONSHIP_SYSTEM,
    build_classification_prompt, build_relationship_prompt, build_gap_detection_prompt
)
import json

# 분류 프롬프트 생성 테스트
tickets = [
    {'id': 'CAM-001', 'jira_type': 'Epic', 'summary': '4K@60fps, 100ms 이하 레이턴시', 'description': 'End-to-end latency must be below 100ms for 4K60 pipeline', 'labels': ['latency', 'requirement']},
    {'id': 'CAM-022', 'jira_type': 'Task', 'summary': 'ISP DVFS 전력 관리', 'description': 'Dynamic Voltage Frequency Scaling causes 12-18ms latency spikes', 'labels': ['power', 'dvfs']},
]
prompt = build_classification_prompt(json.dumps(tickets, ensure_ascii=False, indent=2))
print(f'분류 프롬프트 길이: {len(prompt)}자')
assert 'CAM-001' in prompt
assert 'CAM-022' in prompt
print('분류 프롬프트 생성 OK')

# 관계 추론 프롬프트 생성 테스트
rel_prompt = build_relationship_prompt(
    json.dumps([{'id': 'CAM-022', 'type': 'Design_Spec', 'name': 'DVFS', 'description': 'latency spike'}]),
    json.dumps([{'id': 'CAM-001', 'type': 'Requirement', 'name': 'latency req'}]),
    json.dumps([]),
)
print(f'관계 프롬프트 길이: {len(rel_prompt)}자')
assert '[INFERRED]' in RELATIONSHIP_SYSTEM
print('관계 추론 프롬프트 OK')
"
```

### 3-3. 헬퍼 함수 단위 테스트

```bash
uv run python -c "
from src.agent.nodes import _guess_relation, _compute_confidence
from src.models.ontology import OntologyNode

# 관계 타입 추정 로직 검증
def make_node(id, type):
    return OntologyNode(id=id, type=type, name=id, description='')

cases = [
    ('Design_Spec',       'Requirement',    'satisfies'),
    ('Design_Spec',       'Architecture_Block', 'implements'),
    ('Architecture_Block','Requirement',    'satisfies'),
    ('Verification',      'Requirement',    'verifies'),
    ('Verification',      'Design_Spec',    'verifies'),
    ('Issue',             'Requirement',    'affects'),
]
for src_type, tgt_type, expected in cases:
    src = make_node('SRC', src_type)
    tgt = make_node('TGT', tgt_type)
    result = _guess_relation(src, 'TGT', {'TGT': tgt})
    status = '✅' if result == expected else '❌'
    print(f'{status} {src_type} → {tgt_type}: {result} (기대: {expected})')

# 신뢰도 계산 검증
n_no_ai  = [make_node('A', 'Requirement')]
n_all_ai = [make_node('B', 'Requirement')]
n_all_ai[0].ai_classified = True

conf_no_ai  = _compute_confidence(n_no_ai, [])
conf_all_ai = _compute_confidence(n_all_ai, [])
print(f'신뢰도 (AI 없음): {conf_no_ai}')    # 기대: 0.7
print(f'신뢰도 (AI 있음): {conf_all_ai}')   # 기대: 0.9
assert conf_all_ai > conf_no_ai, '신뢰도: AI 분류 시 높아야 함'
print('헬퍼 함수 테스트 통과')
"
```

### 3-4. 파이프라인 소규모 실행 테스트 (API 호출 발생 — 비용 주의)

> **주의**: 아래 명령은 Claude API를 실제로 호출합니다. 티켓 3개 × 2배치 = 약 4-6회 API 호출.

```bash
uv run python -c "
import os
from dotenv import load_dotenv
load_dotenv()

assert os.getenv('ANTHROPIC_API_KEY'), 'ANTHROPIC_API_KEY가 설정되지 않았습니다'

from src.datasource.dummy_adapter import DummyAdapter
from src.graph.factory import get_backend
from src.agent.graph import run_pipeline

# 3개 티켓만 테스트 (CAM-001, CAM-010, CAM-022)
all_tickets = DummyAdapter().fetch_all_tickets()
test_tickets = [t for t in all_tickets if t.id in ('CAM-001', 'CAM-010', 'CAM-022')]
backend = get_backend(persist=False)

logs = []
def log(msg): logs.append(msg); print(msg)
def prog(pct): print(f'  진행: {pct}%')

result = run_pipeline(
    tickets=test_tickets,
    backend=backend,
    batch_size=3,
    log_fn=log,
    progress_fn=prog,
)
print()
print(f'결과: 노드={result[\"nodes_created\"]}, 엣지={result[\"edges_created\"]}, 갭={result[\"gaps_found\"]}')
print(f'run_id: {result[\"run_id\"]}')

# 결과 검증
sg = backend.query_full_graph()
print(f'그래프 노드: {len(sg.nodes)}')
for node in sg.nodes:
    flag = '🔄' if node.original_jira_type and node.original_jira_type != node.type else '✅'
    print(f'  {flag} {node.id}: {node.original_jira_type} → {node.type} (AI: {node.ai_classified})')
" 2>&1
```

**기대 출력 패턴:**
```
🚀 파이프라인 시작 (run_id=xxxxxxxx, tickets=3, batch_size=3)
🔍 [Batch 1] 3개 티켓 분류 중...
  CAM-001: Requirement → Requirement ✅ 유지 (신뢰도: 95%)
  CAM-010: Architecture_Block → Architecture_Block ✅ 유지 (신뢰도: 88%)
  CAM-022: Design_Spec → Design_Spec ✅ 유지 (신뢰도: 82%)
🔗 관계 추론 중...
  🤖 CAM-022 --affects--> CAM-001
📋 승인 큐 적재: 3개 노드, X개 엣지
✅ 자동 승인 (신뢰도 XX% ≥ 75%)
📊 파이프라인 완료 리포트
```

### 3-5. 전체 파이프라인 실행 (Streamlit UI)

1. `.env` 파일에 `ANTHROPIC_API_KEY` 설정
2. `uv run streamlit run src/ui/app.py`
3. **⚙️ Agent Run** 페이지 접속
4. Batch Size: 5, Threshold: 0.75 설정
5. **🚀 파이프라인 실행** 클릭
6. 실시간 로그 확인

**완료 후 검증 체크리스트:**

| 항목 | 확인 방법 | 기대 결과 |
|------|-----------|-----------|
| Flat View AI Type 컬럼 | 📋 Flat View 접속 | "AI Type" 컬럼 표시, 재분류 항목에 🔄 표시 |
| 재분류 배너 | Flat View 상단 | "AI 분류 결과 로드됨 — N개 노드 분석 완료" |
| Graph View 갱신 | 🕸️ Graph View → Reload Graph | 새 엣지 추가 확인 |
| AI 추론 엣지 | Graph View 사이드바 | "Inferred Edges Only" 토글로 확인 |
| 승인 대기 목록 | ✅ Approvals | 신뢰도 낮은 배치 표시 (있는 경우) |
| 갭 개수 변화 | 📊 Metrics | 갭 목록 업데이트 확인 |

### 3-6. 재분류 품질 검증

아래 티켓들은 JIRA 타입이 실제 내용과 맞는지 AI가 검증해야 할 항목입니다:

```bash
uv run python -c "
# 파이프라인 실행 후 재분류 결과 확인
from src.graph.factory import get_backend
b = get_backend(persist=True)
sg = b.query_full_graph()

reclassified = [(n.id, n.original_jira_type, n.type) for n in sg.nodes
                if n.ai_classified and n.original_jira_type != n.type]
print(f'재분류된 노드: {len(reclassified)}개')
for id, orig, new in reclassified:
    print(f'  {id}: {orig} → {new}')

# AI가 새로 찾은 엣지
inferred = [e for e in sg.edges if e.is_inferred]
print(f'AI 추론 엣지: {len(inferred)}개')
for e in inferred:
    print(f'  {e.source_id} --{e.relation}--> {e.target_id}')
    print(f'  reasoning: {e.reasoning[:80]}...')
"
```

---

## 4. JIRA 연동 테스트

> 자세한 설정은 `docs/jira_integration_guide.md` 참고.

### 4-1. 연결 테스트 (읽기 전용)

```bash
# .env에 JIRA 설정 완료 후
uv run python -c "
import os
from dotenv import load_dotenv
load_dotenv()

# 설정 확인
for key in ['JIRA_URL', 'JIRA_EMAIL', 'JIRA_PROJECT_KEY', 'JIRA_CLOUD']:
    val = os.getenv(key, '(미설정)')
    print(f'{key}: {val}')
print()

from src.datasource.jira_adapter import JiraAdapter
adapter = JiraAdapter()
print('클라이언트 초기화 OK')

# 이슈 타입 목록 조회 (API 호출)
types = adapter.list_issue_types()
print(f'이슈 타입 목록 ({len(types)}개):')
for t in types:
    print(f'  - {t[\"name\"]}')
"
```

### 4-2. 소규모 수집 테스트 (최근 5개)

```bash
uv run python -c "
import os
os.environ['JIRA_MAX_RESULTS'] = '5'

from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter

adapter = JiraAdapter()
tickets = adapter.fetch_all_tickets()
print(f'수집: {len(tickets)}개')
for t in tickets:
    print(f'  [{t.id}] {t.type:20s} {t.summary[:50]}')
    if t.description:
        print(f'    description: {t.description[:80]}...')
"
```

### 4-3. 타입 매핑 검증

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter

adapter = JiraAdapter()
tickets = adapter.fetch_all_tickets()

# 타입 분포 확인
from collections import Counter
type_counts = Counter(t.type for t in tickets)
print('타입 분포:')
for t, cnt in sorted(type_counts.items()):
    print(f'  {t:25s}: {cnt}개')

# 알 수 없는 타입 확인 (Design_Spec으로 fallback된 것들)
from src.datasource.jira_adapter import _DEFAULT_TYPE_MAP
jira_types = set()
# 원본 JIRA 타입은 로그에서 확인하거나 adapter._client.jql()로 직접 조회
"
```

### 4-4. 증분 동기화 테스트

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter
from datetime import datetime, timedelta

adapter = JiraAdapter()

# 최근 7일 변경분
since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00')
updated = adapter.fetch_updated_since(since)
print(f'최근 7일 변경: {len(updated)}개')
for t in updated[:5]:
    print(f'  [{t.id}] {t.summary[:50]}')
"
```

---

## 5. 단위 테스트 스크립트

아래는 복사해서 바로 실행 가능한 전체 단위 테스트입니다. `pytest` 없이도 동작합니다.

```bash
uv run python -c "
import sys

passed = []
failed = []

def test(name, fn):
    try:
        fn()
        passed.append(name)
        print(f'✅ {name}')
    except Exception as e:
        failed.append((name, str(e)))
        print(f'❌ {name}: {e}')

# ── 데이터 모델 ────────────────────────────────────────────────────────
def test_ontology_node():
    from src.models.ontology import OntologyNode
    n = OntologyNode(
        id='CAM-001', type='Requirement',
        name='latency', description='100ms',
        original_jira_type='Epic', ai_classified=True
    )
    assert n.ai_classified == True
    assert n.original_jira_type == 'Epic'

def test_ontology_edge():
    from src.models.ontology import OntologyEdge
    e = OntologyEdge(
        source_id='A', target_id='B', relation='satisfies',
        reasoning='[INFERRED] semantic match', is_inferred=True
    )
    assert e.is_inferred == True
    assert e.reasoning.startswith('[INFERRED]')

def test_proposed_update_serialization():
    import uuid
    from src.models.ontology import OntologyNode, OntologyEdge, ProposedUpdate
    upd = ProposedUpdate(
        nodes=[OntologyNode(id='X', type='Issue', name='bug', description='desc')],
        edges=[OntologyEdge(source_id='X', target_id='Y', relation='affects', reasoning='r')],
        confidence_score=0.85,
        batch_id=uuid.uuid4().hex,
    )
    json_str = upd.model_dump_json()
    restored = ProposedUpdate.model_validate_json(json_str)
    assert restored.confidence_score == 0.85
    assert len(restored.nodes) == 1

# ── 더미 어댑터 ────────────────────────────────────────────────────────
def test_dummy_adapter_counts():
    from src.datasource.dummy_adapter import DummyAdapter
    a = DummyAdapter()
    tickets = a.fetch_all_tickets()
    edges   = a.fetch_pre_computed_edges()
    assert len(tickets) == 18
    assert len(edges)   == 20
    assert any(t.id == 'CAM-001' for t in tickets)

def test_dummy_adapter_types():
    from src.datasource.dummy_adapter import DummyAdapter
    tickets = DummyAdapter().fetch_all_tickets()
    expected = {'Requirement', 'Architecture_Block', 'Design_Spec', 'Verification', 'Issue'}
    actual   = {t.type for t in tickets}
    assert actual == expected, f'타입 불일치: {actual}'

def test_dummy_adapter_fetch_single():
    from src.datasource.dummy_adapter import DummyAdapter
    t = DummyAdapter().fetch_ticket('CAM-001')
    assert t.id == 'CAM-001'
    assert t.type == 'Requirement'

# ── 그래프 백엔드 ──────────────────────────────────────────────────────
def test_graph_load():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    sg = b.query_full_graph()
    assert len(sg.nodes) == 18
    assert len(sg.edges) == 20

def test_graph_merge_idempotent():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    load_dummy_graph(b)  # 두 번 로드
    sg = b.query_full_graph()
    assert len(sg.nodes) == 18, f'중복 노드 발생: {len(sg.nodes)}'
    assert len(sg.edges) == 20, f'중복 엣지 발생: {len(sg.edges)}'

def test_graph_orphans():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    orphans = b.query_orphan_nodes()
    orphan_ids = sorted([o.id for o in orphans])
    expected   = ['CAM-040', 'CAM-041', 'CAM-042', 'CAM-050', 'CAM-051']
    assert orphan_ids == expected, f'고아 노드 불일치: {orphan_ids}'

def test_graph_traceability_chain():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    chain = b.get_traceability_chain('CAM-001')
    assert len(chain) > 0, 'CAM-001 체인이 비어 있음'
    # CAM-010 (arch)이 CAM-001 체인에 포함돼야 함
    all_ids = {n.id for path in chain for n in path}
    assert 'CAM-010' in all_ids

def test_graph_reachable_types():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    types = b.get_reachable_node_types('CAM-001')
    assert 'Architecture_Block' in types
    assert 'Design_Spec' in types

def test_graph_conflicts():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    b = get_backend(persist=False)
    load_dummy_graph(b)
    conflicts = b.detect_conflicts()
    assert len(conflicts) >= 1
    ids = conflicts[0].affected_node_ids
    assert 'CAM-010' in ids
    assert 'CAM-020' in ids
    assert 'CAM-021' in ids

# ── 메트릭 엔진 ───────────────────────────────────────────────────────
def test_metrics_baseline():
    from src.graph.factory import get_backend
    from src.graph.loader import load_dummy_graph
    from src.metrics.traceability import MetricsEngine
    b = get_backend(persist=False)
    load_dummy_graph(b)
    r = MetricsEngine(b).compute_all()
    assert r.total_nodes == 18
    assert r.total_edges == 20
    assert r.coverage_score == 25.0
    assert r.orphan_rate   == pytest_approx(27.8, abs=0.5) if False else abs(r.orphan_rate - 27.8) < 0.5
    assert r.inferred_edges == 4
    assert len(r.gaps) == 9

# ── 스테이징 스토어 ───────────────────────────────────────────────────
def test_staging_round_trip():
    import uuid
    from src.staging.sqlite_store import StagingStore
    from src.models.ontology import OntologyNode, ProposedUpdate
    s = StagingStore()
    bid = 'TEST-' + uuid.uuid4().hex[:8]
    upd = ProposedUpdate(
        nodes=[OntologyNode(id='T1', type='Issue', name='t', description='d')],
        edges=[], confidence_score=0.8, batch_id=bid,
    )
    before = s.count_pending()
    s.enqueue(upd)
    assert s.count_pending() == before + 1
    s.mark_approved(bid)
    assert s.count_pending() == before

# ── 에이전트 헬퍼 ─────────────────────────────────────────────────────
def test_guess_relation():
    from src.agent.nodes import _guess_relation
    from src.models.ontology import OntologyNode
    src = OntologyNode(id='A', type='Design_Spec', name='a', description='')
    tgt = OntologyNode(id='B', type='Requirement', name='b', description='')
    assert _guess_relation(src, 'B', {'B': tgt}) == 'satisfies'
    src2 = OntologyNode(id='C', type='Verification', name='c', description='')
    assert _guess_relation(src2, 'B', {'B': tgt}) == 'verifies'
    src3 = OntologyNode(id='D', type='Issue', name='d', description='')
    assert _guess_relation(src3, 'B', {'B': tgt}) == 'affects'

def test_compute_confidence():
    from src.agent.nodes import _compute_confidence
    from src.models.ontology import OntologyNode
    n = OntologyNode(id='X', type='Requirement', name='x', description='')
    c_no_ai = _compute_confidence([n], [])
    n.ai_classified = True
    c_with_ai = _compute_confidence([n], [])
    assert c_no_ai  == 0.7
    assert c_with_ai == 0.9
    assert c_with_ai > c_no_ai

def test_adf_parser():
    from src.datasource.jira_adapter import _adf_to_text
    adf = {
        'type': 'doc', 'version': 1,
        'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': 'Hello '},
                {'type': 'text', 'text': 'World'},
            ]},
        ]
    }
    result = _adf_to_text(adf)
    assert 'Hello' in result
    assert 'World' in result

def test_batch_complete_check():
    from src.agent.edges import batch_complete_check
    from src.models.jira_ticket import JiraTicket

    def make_ticket(id):
        return JiraTicket(id=id, type='Issue', summary='s', description='d')

    state_mid  = {'tickets': [make_ticket(str(i)) for i in range(10)], 'batch_index': 0, 'batch_size': 5}
    state_last = {'tickets': [make_ticket(str(i)) for i in range(10)], 'batch_index': 5, 'batch_size': 5}

    assert batch_complete_check(state_mid)  == 'next_batch'
    assert batch_complete_check(state_last) == 'finalize'

# ── 테스트 실행 ───────────────────────────────────────────────────────
tests = [
    test_ontology_node, test_ontology_edge, test_proposed_update_serialization,
    test_dummy_adapter_counts, test_dummy_adapter_types, test_dummy_adapter_fetch_single,
    test_graph_load, test_graph_merge_idempotent, test_graph_orphans,
    test_graph_traceability_chain, test_graph_reachable_types, test_graph_conflicts,
    test_metrics_baseline, test_staging_round_trip,
    test_guess_relation, test_compute_confidence, test_adf_parser, test_batch_complete_check,
]

for t in tests:
    test(t.__name__, t)

print()
print(f'결과: {len(passed)}/{len(tests)} 통과', end='')
if failed:
    print(f', {len(failed)} 실패:')
    for name, err in failed:
        print(f'  ❌ {name}: {err}')
    sys.exit(1)
else:
    print(' — 전체 통과 ✅')
"
```

**기대 출력:**
```
✅ test_ontology_node
✅ test_ontology_edge
... (18개 항목)
결과: 18/18 통과 — 전체 통과 ✅
```

---

## 6. 통합 테스트 스크립트

API 키가 있을 때 전체 파이프라인을 End-to-End로 검증합니다.

```bash
uv run python -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()

if not os.getenv('ANTHROPIC_API_KEY'):
    print('ANTHROPIC_API_KEY 미설정 — 통합 테스트 건너뜀')
    sys.exit(0)

print('=== 통합 테스트 시작 ===')
print()

# 1. 데이터 로드
from src.datasource.dummy_adapter import DummyAdapter
tickets = DummyAdapter().fetch_all_tickets()
print(f'Step 1 ✅ 티켓 로드: {len(tickets)}개')

# 2. 그래프 백엔드 초기화
from src.graph.factory import get_backend
backend = get_backend(persist=False)
print('Step 2 ✅ 그래프 백엔드 초기화')

# 3. 파이프라인 실행 (전체 18개)
from src.agent.graph import run_pipeline
logs = []
result = run_pipeline(
    tickets=tickets,
    backend=backend,
    batch_size=5,
    log_fn=lambda m: logs.append(m),
    progress_fn=lambda p: None,
)
print(f'Step 3 ✅ 파이프라인 완료:')
print(f'  노드 생성: {result[\"nodes_created\"]}개')
print(f'  엣지 생성: {result[\"edges_created\"]}개')
print(f'  갭 탐지:   {result[\"gaps_found\"]}개')

# 4. 그래프 결과 검증
sg = backend.query_full_graph()
assert len(sg.nodes) == 18, f'노드 수 오류: {len(sg.nodes)}'

inferred = [e for e in sg.edges if e.is_inferred]
print(f'Step 4 ✅ AI 추론 엣지: {len(inferred)}개')

# G-02 갭: DVFS(CAM-022) → 레이턴시(CAM-001) affects 엣지 탐지 여부
dvfs_to_latency = [e for e in inferred if e.source_id == 'CAM-022' and e.target_id == 'CAM-001']
if dvfs_to_latency:
    print(f'Step 5 ✅ G-02 갭 감지: CAM-022 --affects--> CAM-001 발견')
else:
    print(f'Step 5 ⚠️  G-02 갭 미탐지 (CAM-022→CAM-001 affects 없음) — 프롬프트 개선 고려')

# 재분류 결과
reclassified = [n for n in sg.nodes if n.ai_classified and n.original_jira_type != n.type]
print(f'Step 6 ✅ 재분류: {len(reclassified)}개 노드')
for n in reclassified:
    print(f'  {n.id}: {n.original_jira_type} → {n.type}')

# 메트릭 비교 (Before vs After)
from src.metrics.traceability import MetricsEngine
r_after = MetricsEngine(backend).compute_all()
print()
print('=== Before vs After ===')
print(f'커버리지:      25.0% → {r_after.coverage_score:.1f}%')
print(f'고아 노드:     27.8% → {r_after.orphan_rate:.1f}%')
print(f'AI 추론 엣지:  4개   → {r_after.inferred_edges}개')
print(f'갭:            9개   → {len(r_after.gaps)}개')
print()
print('=== 통합 테스트 완료 ===')
"
```

---

## 7. 트러블슈팅 체크리스트

### 임포트 오류

| 오류 메시지 | 원인 | 해결 |
|------------|------|------|
| `ModuleNotFoundError: instructor` | instructor 미설치 | `uv add instructor` |
| `ModuleNotFoundError: langgraph` | langgraph 미설치 | `uv sync` |
| `ModuleNotFoundError: src.*` | 경로 문제 | 프로젝트 루트에서 `uv run python` 실행 |
| `KeyError: ANTHROPIC_API_KEY` | .env 미로드 | `from dotenv import load_dotenv; load_dotenv()` |

### 파이프라인 오류

| 오류 메시지 | 원인 | 해결 |
|------------|------|------|
| `anthropic.AuthenticationError` | API 키 오류 | `.env`의 `ANTHROPIC_API_KEY` 확인 |
| `instructor.exceptions.InstructorRetryException` | LLM 응답 파싱 실패 | 프롬프트 단순화 또는 `max_retries` 증가 |
| `RecursionError` in LangGraph | `recursion_limit` 부족 | `graph.py`의 `recursion_limit` 값 증가 |
| 노드가 그래프에 없음 | 신뢰도 임계값 미달 | `.env`의 `APPROVAL_THRESHOLD` 낮추거나 Approvals 페이지에서 수동 승인 |

### 메트릭 오류

| 현상 | 원인 | 해결 |
|------|------|------|
| 커버리지 0% | `nx.descendants` 사용 | `networkx_backend.py`의 `get_traceability_chain`이 `nx.ancestors` 사용하는지 확인 |
| 고아 노드 0개 | 엣지 방향 반전 | MBSE 엣지는 child→parent 방향 확인 |
| 갭 수 감소 | AI가 엣지 추가 | 정상 동작 (AI가 연결 누락 해소) |

### Streamlit UI 오류

| 현상 | 원인 | 해결 |
|------|------|------|
| 그래프 빈 화면 | 캐시 문제 | 사이드바 "🔄 Reload Graph" 클릭 |
| AI Type 컬럼 없음 | 파이프라인 미실행 | Agent Run 페이지에서 파이프라인 실행 |
| 클릭 팝업 안 나옴 | 브라우저 iframe 정책 | Chrome/Edge 사용 권장 |
| 페이지 흰 배경 | inject_global_css 누락 | 페이지 상단 `inject_global_css()` 확인 |
