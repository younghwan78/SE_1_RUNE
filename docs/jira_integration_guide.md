# JIRA REST API 연동 가이드

> 이 가이드는 `DATASOURCE_MODE=jira`로 전환하여 실제 JIRA 데이터를 Knowledge Graph에 연결하는 전 과정을 설명합니다.

---

## 목차

1. [사전 확인 사항](#1-사전-확인-사항)
2. [인증 토큰 발급](#2-인증-토큰-발급)
3. [환경 변수 설정](#3-환경-변수-설정)
4. [패키지 설치](#4-패키지-설치)
5. [이슈 타입 매핑 확인](#5-이슈-타입-매핑-확인)
6. [연결 테스트](#6-연결-테스트)
7. [데이터 수집 실행](#7-데이터-수집-실행)
8. [커스터마이징](#8-커스터마이징)
9. [증분 동기화 (운영 환경)](#9-증분-동기화-운영-환경)
10. [트러블슈팅](#10-트러블슈팅)

---

## 1. 사전 확인 사항

### JIRA 환경 종류 확인

| 환경 | URL 형태 | 인증 방식 |
|------|----------|----------|
| **Jira Cloud** | `https://회사명.atlassian.net` | API Token |
| **Jira Server (On-premise)** | `https://jira.내부도메인.com` | Personal Access Token (PAT) |
| **Jira Data Center** | `https://jira.내부도메인.com` | Personal Access Token (PAT) |

> 사내 시스템은 대부분 **Jira Server 또는 Data Center**입니다.  
> URL에 `atlassian.net`이 없으면 On-premise로 판단하고 `JIRA_CLOUD=false`로 설정합니다.

### 필요한 JIRA 권한

연동 계정에 아래 권한이 있어야 합니다:
- **Browse Projects** — 프로젝트 읽기
- **View Issues** — 이슈 목록 조회
- **View Development Tools** — 이슈 링크 조회 (없어도 기본 동작은 가능)

IT 부서 또는 JIRA 관리자에게 확인 요청하세요.

---

## 2. 인증 토큰 발급

### A. Jira Cloud — API Token

1. `https://id.atlassian.com/manage-profile/security/api-tokens` 접속
2. **Create API token** 클릭
3. 레이블 입력 (예: `req-tracker-ai`) → **Create**
4. 토큰을 복사하여 `.env`의 `JIRA_TOKEN`에 붙여넣기

```
JIRA_EMAIL=your.email@company.com
JIRA_TOKEN=ATATT3x...  (API Token)
JIRA_CLOUD=true
```

### B. Jira Server / Data Center — Personal Access Token (PAT)

> PAT은 Jira Server 8.14+, Data Center 에서 지원됩니다. 이전 버전은 [Basic Auth](#b-1-이전-버전--basic-auth) 참고.

1. JIRA 우상단 프로필 아이콘 → **Profile**
2. 좌측 메뉴 → **Personal Access Tokens**
3. **Create token** 클릭
4. 이름 입력, 만료일 설정 (보안 정책에 따라) → **Create**
5. 토큰 복사

```
JIRA_EMAIL=your.email@company.com
JIRA_TOKEN=NjAx...  (PAT)
JIRA_CLOUD=false
```

> **주의**: PAT 방식에서는 `JIRA_EMAIL`이 무시되고 토큰만으로 인증됩니다.  
> (atlassian-python-api 내부적으로 처리)

#### B-1. 이전 버전 — Basic Auth

PAT을 지원하지 않는 구버전 Jira Server:

```
JIRA_EMAIL=your.username      # JIRA 로그인 ID (이메일 아닐 수 있음)
JIRA_TOKEN=your-password      # JIRA 비밀번호
JIRA_CLOUD=false
```

> Basic Auth는 보안상 권장하지 않습니다. 가능하면 PAT으로 업그레이드하세요.

---

## 3. 환경 변수 설정

`.env.example`을 복사하고 아래를 수정합니다:

```bash
cp .env.example .env
```

```ini
# .env

DATASOURCE_MODE=jira        # dummy → jira 로 변경

# JIRA 기본 설정
JIRA_URL=https://jira.your-company.com   # 끝에 / 없이
JIRA_EMAIL=hong.gildong@company.com
JIRA_TOKEN=YOUR_TOKEN_HERE
JIRA_PROJECT_KEY=CAM                      # JIRA 프로젝트 키 (대문자)

# On-premise: false / Cloud: true (기본값)
JIRA_CLOUD=false

# 선택: 특정 스프린트만 수집 (빈 값이면 전체 수집)
# JIRA_JQL_EXTRA=AND sprint in openSprints()

# 선택: 이슈 타입 커스텀 매핑 (JSON 문자열)
# JIRA_TYPE_MAP={"Technical Task":"Design_Spec","System Requirement":"Requirement"}
```

---

## 4. 패키지 설치

```bash
uv add atlassian-python-api
```

> `pyproject.toml`에 자동으로 추가됩니다.

---

## 5. 이슈 타입 매핑 확인

사내 JIRA는 회사마다 커스텀 이슈 타입이 있습니다.  
먼저 실제 타입 목록을 확인한 뒤 매핑을 설정합니다.

### 타입 목록 조회 스크립트

```bash
# 프로젝트 루트에서 실행
uv run python -c "
from src.datasource.jira_adapter import JiraAdapter
adapter = JiraAdapter()
types = adapter.list_issue_types()
for t in types:
    print(f'  {t[\"name\"]:30s}  {t.get(\"description\",\"\")[:50]}')
"
```

### 매핑 예시

조회 결과가 아래와 같다면:
```
Epic                  시스템/고객 요구사항
Story                 아키텍처 결정 사항
Task                  구현 태스크
Sub-task              세부 구현
Bug                   버그/결함
Test Plan             검증 계획
Risk                  리스크 항목
```

`.env`에 아래를 추가:
```ini
JIRA_TYPE_MAP={"Epic":"Requirement","Story":"Architecture_Block","Task":"Design_Spec","Sub-task":"Design_Spec","Bug":"Issue","Test Plan":"Verification","Risk":"Issue"}
```

### 기본 매핑 테이블 (수정 없이 동작하는 타입)

| JIRA 이슈 타입 | Ontology 타입 |
|---------------|---------------|
| Epic | Requirement |
| Requirement | Requirement |
| Feature | Requirement |
| Story | Architecture_Block |
| Architecture | Architecture_Block |
| Task | Design_Spec |
| Sub-task | Design_Spec |
| Design | Design_Spec |
| Implementation | Design_Spec |
| Bug | Issue |
| Risk | Issue |
| Impediment | Issue |
| Test | Verification |
| Test Case | Verification |
| Verification | Verification |
| **그 외** | Design_Spec (fallback) |

---

## 6. 연결 테스트

본격 수집 전 연결을 검증합니다.

```bash
uv run python -c "
import os
from dotenv import load_dotenv
load_dotenv()

from src.datasource.jira_adapter import JiraAdapter

print('JIRA 연결 테스트 시작...')
print(f'  URL:     {os.getenv(\"JIRA_URL\")}')
print(f'  Project: {os.getenv(\"JIRA_PROJECT_KEY\")}')
print(f'  Cloud:   {os.getenv(\"JIRA_CLOUD\", \"true\")}')
print()

adapter = JiraAdapter()

# 최근 5개 티켓만 조회
import os; os.environ['JIRA_MAX_RESULTS'] = '5'
tickets = adapter.fetch_all_tickets()
print(f'수집된 티켓 수: {len(tickets)}')
for t in tickets:
    print(f'  [{t.id}] {t.type:20s} {t.summary[:50]}')
"
```

기대 출력:
```
JIRA 연결 테스트 시작...
  URL:     https://jira.your-company.com
  Project: CAM
  Cloud:   false

수집된 티켓 수: 5
  [CAM-001] Requirement         4K@60fps 레이턴시 요구사항
  [CAM-002] Requirement         HDR10 정지 영상 캡처
  ...
```

---

## 7. 데이터 수집 실행

### Streamlit UI에서 실행 (권장)

1. `.env`의 `DATASOURCE_MODE=jira` 확인
2. `uv run streamlit run src/ui/app.py` 실행
3. **⚙️ Agent Run** 페이지에서 "파이프라인 실행" 클릭

> Phase 1 (LangGraph 파이프라인) 구현 후 완전 동작.  
> 현재는 데이터 수집 및 그래프 로딩까지 동작합니다.

### 명령줄에서 직접 수집 (개발/디버깅용)

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.factory import get_adapter
from src.graph.factory import get_backend
from src.graph.loader import load_graph_from_tickets

print('데이터 수집 중...')
adapter = get_adapter()
tickets = adapter.fetch_all_tickets()
print(f'티켓 {len(tickets)}개 수집 완료')

print('그래프 로딩 중...')
backend = get_backend(persist=True)
load_graph_from_tickets(backend, tickets)

subgraph = backend.query_full_graph()
print(f'그래프 노드: {len(subgraph.nodes)}, 엣지: {len(subgraph.edges)}')
"
```

---

## 8. 커스터마이징

### 수집 범위 제한 (JQL 필터)

특정 스프린트 또는 기간만 수집:

```ini
# 현재 열린 스프린트만
JIRA_JQL_EXTRA=AND sprint in openSprints()

# 특정 스프린트 지정
JIRA_JQL_EXTRA=AND sprint = "Sprint 12"

# 최근 3개월
JIRA_JQL_EXTRA=AND created >= -90d

# 특정 에픽 하위 이슈만
JIRA_JQL_EXTRA=AND "Epic Link" = CAM-001

# 복합 조건
JIRA_JQL_EXTRA=AND sprint in openSprints() AND labels = "camera-hal"
```

### 커스텀 필드 추가 수집

사내 JIRA에 추가된 커스텀 필드(설계 문서 링크, 리뷰어 등)를 가져오려면 `jira_adapter.py`의 `fetch_all_tickets` 내 `fields` 리스트에 필드 ID를 추가합니다:

```python
# 커스텀 필드 ID 확인: JIRA 관리자에게 요청하거나
# https://jira.company.com/rest/api/2/field  에서 직접 조회
fields=[
    ...,
    "customfield_10100",   # 예: 설계 문서 링크
    "customfield_10101",   # 예: 리뷰어
]
```

---

## 9. 증분 동기화 (운영 환경)

전체 재수집 대신 변경분만 가져오는 방식:

```python
from src.datasource.jira_adapter import JiraAdapter
from datetime import datetime, timedelta

adapter = JiraAdapter()

# 최근 24시간 변경분
since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
new_tickets = adapter.fetch_updated_since(since)

print(f"변경된 티켓: {len(new_tickets)}개")
```

### 주기적 동기화 스케줄링 (Windows Task Scheduler / cron)

```bash
# cron 예시 (매일 오전 9시)
0 9 * * * cd /path/to/req-tracker-ai && uv run python -m src.sync.incremental >> logs/sync.log 2>&1
```

---

## 10. 트러블슈팅

### 연결 오류: `401 Unauthorized`

| 원인 | 해결 |
|------|------|
| API Token/PAT 만료 | 토큰 재발급 후 `.env` 업데이트 |
| Cloud인데 `JIRA_CLOUD=false` | `JIRA_CLOUD=true`로 변경 |
| On-premise에서 이메일 대신 사용자명 필요 | `JIRA_EMAIL`에 이메일 대신 JIRA 로그인 ID 사용 |
| VPN 미연결 | 사내 VPN 연결 후 재시도 |

### `403 Forbidden`

프로젝트 접근 권한 없음. JIRA 관리자에게 아래 권한 요청:
- Browse Projects
- View Issues

### `No issues found` (빈 결과)

```bash
# JQL 직접 테스트
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter
a = JiraAdapter()
result = a._client.jql(f'project = {a._project_key}', limit=1)
print('total:', result.get('total'))
print('keys:', [i['key'] for i in result.get('issues', [])])
"
```

- `total: 0` → 프로젝트 키 오류 (대소문자 확인) 또는 권한 부족
- `total: N` → `JIRA_JQL_EXTRA` 조건 확인

### Description이 빈 문자열로 나옴

Jira Cloud의 ADF 포맷 파싱 문제. 원본 확인:

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter
a = JiraAdapter()
issue = a._client.issue('CAM-001')
import json; print(json.dumps(issue['fields']['description'], indent=2, ensure_ascii=False)[:500])
"
```

ADF 구조가 예상과 다르면 `jira_adapter.py`의 `_adf_to_text()` 함수를 보강하세요.

### Sprint 필드가 빈 값

커스텀 필드 ID가 다를 수 있습니다. 실제 필드 ID 확인:

```bash
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from src.datasource.jira_adapter import JiraAdapter
a = JiraAdapter()
issue = a._client.issue('CAM-001')
for k, v in issue['fields'].items():
    if 'sprint' in k.lower() or 'sprint' in str(v).lower():
        print(k, ':', str(v)[:100])
"
```

찾은 필드 ID를 `jira_adapter.py`의 `fetch_all_tickets` 내 `fields` 리스트와 `_extract_sprint`에 반영하세요.

### SSL 인증서 오류 (사내 On-premise)

```python
# jira_adapter.py의 _build_client에서
return Jira(
    url=self._url,
    username=self._email,
    password=self._token,
    cloud=self._is_cloud,
    verify_ssl=False,   # 사내 자체 서명 인증서인 경우
)
```

> 보안 정책에 따라 IT 부서에 CA 인증서 파일을 받아 `verify_ssl="/path/to/ca.pem"`으로 설정하는 것이 더 안전합니다.

---

## 참고 링크

- [atlassian-python-api 문서](https://atlassian-python-api.readthedocs.io/)
- [JIRA REST API v3 레퍼런스](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [JQL 문법 가이드](https://support.atlassian.com/jira-software-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [ADF 스펙](https://developer.atlassian.com/cloud/jira/platform/apis/document/)
