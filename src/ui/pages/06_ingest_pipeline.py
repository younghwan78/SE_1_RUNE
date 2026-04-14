"""06_ingest_pipeline.py — 5-Step MBSE Ingestion Pipeline

Step 1: JIRA 연결 확인
Step 2: 프로젝트 + 도메인 키워드 설정 → 이슈 수 미리보기
Step 3: LLM 1차 분류 실행
Step 3.5: 사용자 분류 검증 (필수)
Step 4: Traceability 추론
Step 5: 최종 리포트 + Knowledge Graph 커밋
"""
from __future__ import annotations

import os

import streamlit as st

from src.ui.components.styles import (
    BG2, BORDER, NODE_ARCH, NODE_DESIGN, NODE_ISSUE, NODE_REQ, NODE_VERIF,
    PRIMARY, TEXT, TEXT_DIM, inject_global_css,
)

st.set_page_config(
    page_title="Ingest Pipeline",
    page_icon="🔄",
    layout="wide",
)
inject_global_css()

# ── 세션 상태 초기화 ──────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict = {
        "ip_step": 1,              # 현재 완료된 Step (1~5)
        "ip_source": None,         # IngestSource 인스턴스
        "ip_connected": False,
        "ip_project_key": "",
        "ip_domain_keywords": [],
        "ip_domain_context": "",
        "ip_candidate_count": 0,
        "ip_documents": [],        # list[RawDocument]
        "ip_clf_results": [],      # list[ClassificationResult]
        "ip_corrections": {},      # {doc_id: corrected_type}
        "ip_final_results": [],    # 사용자 수정 반영 후 확정 분류
        "ip_edges": [],            # Pass 2 추론된 엣지
        "ip_committed": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── 팔레트 ────────────────────────────────────────────────────────────────────

_TYPE_COLOR = {
    "Requirement":      NODE_REQ,
    "Architecture_Block": NODE_ARCH,
    "Design_Spec":      NODE_DESIGN,
    "Verification":     NODE_VERIF,
    "Issue":            NODE_ISSUE,
}
_VALID_TYPES = list(_TYPE_COLOR.keys())

# ── 헤더 ──────────────────────────────────────────────────────────────────────

st.title("🔄 Ingest Pipeline")
st.caption("JIRA → RawDocument → MBSE 분류 → Traceability → Knowledge Graph")

# ── 소스 모드 배지 ────────────────────────────────────────────────────────────
from src.ingest.factory import detect_mode as _detect_mode
_current_mode = _detect_mode()
_mode_label = {"file": "📄 File (MCP)", "jira": "🔌 JIRA REST API", "none": "⚠️ 소스 없음"}
_mode_color = {"file": "#4e8c68", "jira": "#5c84ad", "none": "#9e5555"}
st.markdown(
    f'<span style="background:{_mode_color.get(_current_mode,"#555")};color:#fff;'
    f'border-radius:4px;padding:3px 10px;font-size:12px;font-weight:700;">'
    f'소스: {_mode_label.get(_current_mode, _current_mode)}</span>'
    f'<span style="color:{TEXT_DIM};font-size:11px;margin-left:8px;">'
    f'INGEST_SOURCE={os.getenv("INGEST_SOURCE","auto")} | LLM_MODEL={os.getenv("LLM_MODEL","claude-sonnet-4-6")}</span>',
    unsafe_allow_html=True,
)

_step_labels = [
    "1 연결 확인",
    "2 프로젝트 설정",
    "3 LLM 분류",
    "3.5 분류 검증",
    "4 Traceability",
    "5 리포트",
]

# 진행 표시
_cols = st.columns(len(_step_labels))
for i, (col, label) in enumerate(zip(_cols, _step_labels)):
    step_num = i + 1
    done = step_num <= st.session_state.ip_step
    bg = PRIMARY if done else BG2
    fg = "#fff" if done else TEXT_DIM
    col.markdown(
        f'<div style="background:{bg};color:{fg};border-radius:6px;'
        f'padding:6px 0;text-align:center;font-size:12px;font-weight:600;">'
        f'{label}</div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── STEP 1: 소스 확인 ─────────────────────────────────────────────────────────

with st.expander("Step 1 — 데이터 소스 확인", expanded=(st.session_state.ip_step == 1)):
    from pathlib import Path as _Path
    from src.ingest.factory import get_ingest_source as _get_source

    _tab_file, _tab_jira = st.tabs(["📄 File (MCP)", "🔌 JIRA REST API"])

    # ── File 탭 ───────────────────────────────────────────────────────────────
    with _tab_file:
        st.markdown("**Claude MCP로 저장한 JSON 파일을 사용합니다. JIRA 자격증명 불필요.**")

        _fetch_dir = _Path("data/jira_fetch")
        _json_files = sorted(_fetch_dir.glob("*.json")) if _fetch_dir.exists() else []

        if _json_files:
            st.success(f"JSON 파일 {len(_json_files)}개 발견")
            for f in _json_files:
                st.markdown(
                    f'<span style="color:{TEXT_DIM};font-size:12px;">📄 {f.name} '
                    f'({f.stat().st_size // 1024} KB)</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.warning(f"`{_fetch_dir}` 에 JSON 파일이 없습니다.")
            st.markdown(
                f'<div style="background:{BG2};border:1px solid {BORDER};'
                f'border-radius:8px;padding:14px;margin-top:8px;">'
                f'<strong style="color:{TEXT};">Claude에게 요청하는 방법</strong><br><br>'
                f'<span style="color:{TEXT_DIM};font-size:13px;">'
                f'"PROJECT_KEY 프로젝트의 모든 이슈를 key, summary, description, '
                f'issuetype, parent, labels, status, priority 필드로 JSON 배열로 만들어서 '
                f'<code>data/jira_fetch/PROJECT_KEY_issues.json</code> 파일로 저장해줘"'
                f'</span></div>',
                unsafe_allow_html=True,
            )

        if st.button("File 소스로 연결", type="primary", key="connect_file"):
            from src.ingest.file_source import FileIngestSource
            source = FileIngestSource()
            ok, msg = source.test_connection()
            if ok:
                st.success(f"✅ {msg}")
                st.session_state.ip_source = source
                st.session_state.ip_source_mode = "file"
                st.session_state.ip_connected = True
                st.session_state.ip_step = max(st.session_state.ip_step, 2)
            else:
                st.error(f"❌ {msg}")

    # ── JIRA REST API 탭 ──────────────────────────────────────────────────────
    with _tab_jira:
        st.markdown("**JIRA REST API 직접 연결. `.env`에 자격증명 필요.**")

        with st.form("step1_jira_form"):
            _env_vars = {
                "JIRA_URL":   os.getenv("JIRA_URL", ""),
                "JIRA_EMAIL": os.getenv("JIRA_EMAIL", ""),
                "JIRA_TOKEN": "***" if os.getenv("JIRA_TOKEN") else "",
            }
            for k, v in _env_vars.items():
                icon = "✅" if v else "❌"
                st.markdown(
                    f'<span style="color:{TEXT_DIM};font-size:12px;">'
                    f'{icon} {k}: <code>{v or "미설정"}</code></span>',
                    unsafe_allow_html=True,
                )
            _jira_submitted = st.form_submit_button("JIRA 연결 테스트", type="primary")

        if _jira_submitted:
            _missing = [k for k in ["JIRA_URL", "JIRA_EMAIL"] if not os.getenv(k)]
            if not os.getenv("JIRA_TOKEN"):
                _missing.append("JIRA_TOKEN")
            if _missing:
                st.error(f".env에 다음 변수가 없습니다: {', '.join(_missing)}")
            else:
                try:
                    from src.ingest.jira_source import JiraIngestSource
                    _source = JiraIngestSource()
                    _ok, _msg = _source.test_connection()
                    if _ok:
                        st.success(f"✅ {_msg}")
                        st.session_state.ip_source = _source
                        st.session_state.ip_source_mode = "jira"
                        st.session_state.ip_connected = True
                        st.session_state.ip_step = max(st.session_state.ip_step, 2)
                    else:
                        st.error(f"❌ {_msg}")
                except ImportError:
                    st.error("터미널에서 실행: `uv add atlassian-python-api`")
                except KeyError as exc:
                    st.error(f"환경 변수 누락: {exc}")

    if st.session_state.ip_connected:
        _mode_str = st.session_state.get("ip_source_mode", "unknown")
        st.info(f"소스 연결 완료 ({_mode_str}). Step 2로 이동하세요.")

# ── STEP 2: 프로젝트 설정 ─────────────────────────────────────────────────────

with st.expander(
    "Step 2 — 프로젝트 + 도메인 키워드",
    expanded=(st.session_state.ip_step == 2),
):
    if not st.session_state.ip_connected:
        st.warning("Step 1 소스 연결을 먼저 완료하세요.")
    else:
        _src_mode = st.session_state.get("ip_source_mode", "file")

        with st.form("step2_form"):
            project_key = st.text_input(
                "프로젝트 키 (파일 필터 / JIRA JQL)",
                value=os.getenv("JIRA_PROJECT_KEY", ""),
                placeholder="예: CAM, PROJ, HW",
                help="File 모드: 파일명 또는 이슈 ID 접두사로 필터. 비우면 전체 파일 사용.",
            )
            domain_keywords_raw = st.text_input(
                "도메인 키워드 (쉼표 구분)",
                placeholder="예: camera, HAL, ISP, pipeline",
                help="해당 키워드가 제목/본문에 포함된 이슈만 수집. 비우면 전체.",
            )
            domain_context = st.text_area(
                "도메인 컨텍스트 (LLM 프롬프트 보강)",
                placeholder="예: 카메라 HAL SoC 시스템 엔지니어링. Sony IMX789 센서, 4K@60fps 파이프라인 개발 프로젝트.",
                height=80,
                help="도메인 설명을 입력하면 LLM 분류 정확도가 향상됩니다.",
            )
            max_results = st.number_input(
                "최대 수집 이슈 수",
                min_value=10, max_value=2000, value=500 if _src_mode == "file" else 200, step=10,
            )
            submitted2 = st.form_submit_button("이슈 수 확인", type="primary")

        if submitted2:
            domain_kws = [k.strip() for k in domain_keywords_raw.split(",") if k.strip()]
            source = st.session_state.ip_source

            with st.spinner("이슈 수 조회 중..."):
                total = source.fetch_candidate_count(project_key.strip(), domain_kws)

            # 파일 소스일 때 파일 목록도 표시
            if _src_mode == "file":
                from src.ingest.file_source import FileIngestSource
                _fs: FileIngestSource = source  # type: ignore
                _files = _fs.list_json_files()
                _file_info = f" ({', '.join(f.name for f in _files)})" if _files else ""
            else:
                _file_info = ""

            st.markdown(
                f'<div style="background:{BG2};border:1px solid {BORDER};'
                f'border-radius:8px;padding:16px;margin-top:8px;">'
                f'<span style="font-size:1.4rem;color:{TEXT};font-weight:700;">{total:,}개</span>'
                f'<span style="color:{TEXT_DIM};font-size:13px;"> 처리 가능 이슈{_file_info}</span><br>'
                f'<span style="color:{TEXT_DIM};font-size:12px;">'
                f'※ title/description 모두 없는 이슈는 자동 제외됩니다.</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # JIRA 소스일 때만 이슈 타입 목록 조회
            if _src_mode == "jira":
                issue_types = source.list_document_types(project_key.strip())
                if issue_types:
                    with st.expander("프로젝트 이슈 타입 목록 (참고용)"):
                        for t in issue_types:
                            st.markdown(
                                f'<span style="color:{TEXT_DIM};font-size:12px;">'
                                f'`{t["name"]}` — {t["description"] or "설명 없음"}</span>',
                                unsafe_allow_html=True,
                            )

            st.session_state.ip_project_key = project_key.strip()
            st.session_state.ip_domain_keywords = domain_kws
            st.session_state.ip_domain_context = domain_context.strip()
            st.session_state.ip_candidate_count = total
            st.session_state.ip_max_results = max_results
            st.session_state.ip_step = max(st.session_state.ip_step, 3)

# ── STEP 3: LLM 분류 ──────────────────────────────────────────────────────────

with st.expander(
    "Step 3 — LLM 1차 분류",
    expanded=(st.session_state.ip_step == 3),
):
    if st.session_state.ip_step < 3:
        st.warning("Step 2를 먼저 완료하세요.")
    else:
        st.markdown(
            f"**{st.session_state.ip_project_key}** 프로젝트에서 "
            f"최대 **{st.session_state.get('ip_max_results', 200)}개** 이슈를 수집하고 MBSE 타입으로 분류합니다."
        )
        if st.button("분류 시작", type="primary", key="run_clf"):
            log_area = st.empty()
            logs: list[str] = []

            def _log(msg: str) -> None:
                logs.append(msg)
                log_area.code("\n".join(logs[-30:]), language="")

            source = st.session_state.ip_source
            project_key = st.session_state.ip_project_key
            domain_kws = st.session_state.ip_domain_keywords
            max_results = st.session_state.get("ip_max_results", 200)
            domain_context = st.session_state.ip_domain_context

            with st.spinner("이슈 수집 중..."):
                _log("📥 JIRA 이슈 수집 시작...")
                documents = source.fetch_documents(project_key, domain_kws, max_results)
                _log(f"✅ 처리 가능 이슈: {len(documents)}개 수집 완료")

            if not documents:
                st.warning("처리 가능한 이슈가 없습니다. 키워드나 프로젝트 키를 확인하세요.")
            else:
                from src.classification.engine import ClassificationEngine
                engine = ClassificationEngine(domain_context=domain_context)

                with st.spinner(f"{len(documents)}개 이슈 분류 중..."):
                    _log(f"\n🔍 분류 시작 ({len(documents)}개)...")
                    results = engine.classify_batch(documents, log_fn=_log)

                st.session_state.ip_documents = documents
                st.session_state.ip_clf_results = results
                st.session_state.ip_step = max(st.session_state.ip_step, 4)

                # 분류 요약
                from collections import Counter
                type_counts = Counter(r.mbse_type for r in results)
                review_count = sum(1 for r in results if r.needs_review)
                method_counts = Counter(r.method for r in results)

                _log(f"\n📊 분류 완료")
                _log(f"  총 {len(results)}개 → 검토 필요: {review_count}개")
                for t, c in type_counts.most_common():
                    _log(f"  {t}: {c}개")

                st.success(f"분류 완료: {len(results)}개 (검토 필요: {review_count}개)")

# ── STEP 3.5: 사용자 분류 검증 ───────────────────────────────────────────────

with st.expander(
    "Step 3.5 — 분류 검증 (필수)",
    expanded=(st.session_state.ip_step == 4),
):
    if st.session_state.ip_step < 4:
        st.warning("Step 3 분류를 먼저 완료하세요.")
    elif not st.session_state.ip_clf_results:
        st.info("분류 결과가 없습니다.")
    else:
        results = st.session_state.ip_clf_results
        corrections: dict[str, str] = st.session_state.ip_corrections

        # 요약 메트릭
        from collections import Counter
        type_counts = Counter(r.mbse_type for r in results)
        review_needed = [r for r in results if r.needs_review]
        method_counts = Counter(r.method for r in results)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 분류", len(results))
        c2.metric("검토 필요", len(review_needed), delta=f"-{len(results)-len(review_needed)} 자동확정")
        c3.metric("키워드 분류", method_counts.get("keyword", 0) + method_counts.get("epic_default", 0))
        c4.metric("LLM 분류", method_counts.get("llm", 0))

        # 타입 분포
        st.markdown("**타입 분포**")
        dist_cols = st.columns(5)
        for i, mbse_type in enumerate(_VALID_TYPES):
            cnt = type_counts.get(mbse_type, 0)
            color = _TYPE_COLOR[mbse_type]
            dist_cols[i].markdown(
                f'<div style="background:{BG2};border-left:3px solid {color};'
                f'padding:8px 12px;border-radius:4px;font-size:12px;">'
                f'<span style="color:{color};font-weight:700;">{mbse_type.replace("_"," ")}</span><br>'
                f'<span style="color:{TEXT};font-size:1.2rem;font-weight:700;">{cnt}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # 검토 필요 항목 먼저 표시
        tab_review, tab_all = st.tabs([
            f"⚠️ 검토 필요 ({len(review_needed)}개)",
            f"전체 ({len(results)}개)",
        ])

        def _render_result_table(items: list, tab_key: str) -> None:
            for r in items:
                doc = next((d for d in st.session_state.ip_documents if d.id == r.doc_id), None)
                current_type = corrections.get(r.doc_id, r.mbse_type)
                color = _TYPE_COLOR.get(current_type, TEXT_DIM)
                corrected = r.doc_id in corrections

                with st.container():
                    cols = st.columns([1.2, 3, 1.8, 1.5, 0.8])
                    cols[0].markdown(
                        f'<span style="font-size:12px;color:{TEXT_DIM};">{r.doc_id}</span>',
                        unsafe_allow_html=True,
                    )
                    title = doc.title if doc else r.doc_id
                    cols[1].markdown(
                        f'<span style="font-size:12px;color:{TEXT};">{title[:60]}</span>',
                        unsafe_allow_html=True,
                    )
                    cols[2].markdown(
                        f'<span style="font-size:11px;color:{TEXT_DIM};">{r.reasoning[:60]}...</span>',
                        unsafe_allow_html=True,
                    )

                    new_type = cols[3].selectbox(
                        "",
                        options=_VALID_TYPES,
                        index=_VALID_TYPES.index(current_type) if current_type in _VALID_TYPES else 0,
                        key=f"sel_{tab_key}_{r.doc_id}",
                        label_visibility="collapsed",
                    )
                    if new_type != r.mbse_type:
                        st.session_state.ip_corrections[r.doc_id] = new_type
                    elif r.doc_id in st.session_state.ip_corrections and new_type == r.mbse_type:
                        del st.session_state.ip_corrections[r.doc_id]

                    conf_color = "#4e8c68" if r.confidence >= 0.75 else ("#9e7848" if r.confidence >= 0.60 else NODE_ISSUE)
                    cols[4].markdown(
                        f'<span style="font-size:12px;color:{conf_color};">{r.confidence:.0%}</span>',
                        unsafe_allow_html=True,
                    )
                st.markdown(f'<hr style="border-color:{BORDER};margin:2px 0;">', unsafe_allow_html=True)

        with tab_review:
            if not review_needed:
                st.success("검토 필요 항목 없음 — 모두 자동 확정")
            else:
                st.markdown(
                    '<span style="font-size:12px;color:{};"> ID | 제목 | 분류 근거 | 타입 수정 | 신뢰도</span>'.format(TEXT_DIM),
                    unsafe_allow_html=True,
                )
                _render_result_table(review_needed, "review")

        with tab_all:
            st.markdown(
                '<span style="font-size:12px;color:{};"> ID | 제목 | 분류 근거 | 타입 수정 | 신뢰도</span>'.format(TEXT_DIM),
                unsafe_allow_html=True,
            )
            _render_result_table(results, "all")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("분류 확정 → Step 4 진행", type="primary", key="confirm_clf"):
            from src.classification.engine import ClassificationEngine
            engine = ClassificationEngine()
            final = engine.apply_user_corrections(results, st.session_state.ip_corrections)
            st.session_state.ip_final_results = final
            st.session_state.ip_step = max(st.session_state.ip_step, 5)
            st.success(f"분류 확정 완료: {len(final)}개 (수정: {len(st.session_state.ip_corrections)}개)")

# ── STEP 4: Traceability 추론 ─────────────────────────────────────────────────

with st.expander(
    "Step 4 — Traceability 추론",
    expanded=(st.session_state.ip_step == 5),
):
    if st.session_state.ip_step < 5:
        st.warning("Step 3.5 분류 검증을 먼저 완료하세요.")
    elif not st.session_state.ip_final_results:
        st.info("확정된 분류 결과가 없습니다.")
    else:
        final_results = st.session_state.ip_final_results
        documents = st.session_state.ip_documents

        st.markdown(
            f"확정된 **{len(final_results)}개** 이슈의 MBSE 트레이서빌리티 관계를 추론합니다."
        )
        st.caption("JIRA 계층 구조(parent→child) + 분류 타입 조합으로 관계 패턴을 매칭하고, 불명확한 경우 LLM으로 추론합니다.")

        if st.button("Traceability 추론 시작", type="primary", key="run_trace"):
            log_area2 = st.empty()
            logs2: list[str] = []

            def _log2(msg: str) -> None:
                logs2.append(msg)
                log_area2.code("\n".join(logs2[-20:]), language="")

            from src.classification.engine import ClassificationResult
            from src.models.ontology import OntologyEdge, OntologyNode, RelationType

            # 분류 결과 → OntologyNode 변환
            doc_map = {d.id: d for d in documents}
            result_map = {r.doc_id: r for r in final_results}

            nodes: list[OntologyNode] = []
            for r in final_results:
                doc = doc_map.get(r.doc_id)
                if not doc:
                    continue
                nodes.append(OntologyNode(
                    id=r.doc_id,
                    type=r.mbse_type,  # type: ignore[arg-type]
                    name=doc.title,
                    description=doc.body[:300],
                    status=doc.metadata.get("status", "Open"),
                    labels=doc.labels,
                    original_jira_type=doc.jira_issue_type,
                    ai_classified=True,
                ))

            # Pass 2: 계층 구조 기반 관계 패턴 매칭
            _log2("🔗 계층 구조 기반 관계 패턴 매칭...")
            node_map = {n.id: n for n in nodes}
            structural_edges: list[OntologyEdge] = []

            _RELATION_MATRIX: dict[tuple[str, str], str] = {
                ("Requirement", "Architecture_Block"): "allocates",
                ("Requirement", "Design_Spec"):        "decomposes",
                ("Architecture_Block", "Design_Spec"): "realizes",
                ("Design_Spec", "Verification"):       "verifies",
                ("Architecture_Block", "Verification"):"verifies",
                ("Requirement", "Verification"):       "verifies",
            }

            for doc in documents:
                if not doc.parent_id or doc.id not in result_map:
                    continue
                parent_id = doc.parent_id
                if parent_id not in result_map:
                    continue
                src_type = result_map[parent_id].mbse_type
                tgt_type = result_map[doc.id].mbse_type
                relation = _RELATION_MATRIX.get((src_type, tgt_type))
                if relation:
                    structural_edges.append(OntologyEdge(
                        source_id=parent_id,
                        target_id=doc.id,
                        relation=relation,  # type: ignore[arg-type]
                        reasoning=f"JIRA 계층 구조: {parent_id}({src_type}) → {doc.id}({tgt_type})",
                        is_inferred=False,
                    ))
                    _log2(f"  [구조] {parent_id} --{relation}--> {doc.id}")

            # 명시적 링크 처리
            for doc in documents:
                if doc.id not in result_map:
                    continue
                for related_id in doc.related_ids:
                    if related_id not in result_map:
                        continue
                    src_type = result_map[doc.id].mbse_type
                    tgt_type = result_map[related_id].mbse_type
                    relation = _RELATION_MATRIX.get((src_type, tgt_type), "affects")
                    structural_edges.append(OntologyEdge(
                        source_id=doc.id,
                        target_id=related_id,
                        relation=relation,  # type: ignore[arg-type]
                        reasoning=f"JIRA 명시적 링크: {doc.id} → {related_id}",
                        is_inferred=False,
                    ))
                    _log2(f"  [링크] {doc.id} --{relation}--> {related_id}")

            _log2(f"\n✅ 구조적 엣지: {len(structural_edges)}개")

            # LLM 추론 (기존 infer_relationships 노드 재활용)
            _log2("\n🤖 LLM 관계 추론 시작...")
            import json as _json
            import os as _os

            llm_edges: list[OntologyEdge] = []
            try:
                import instructor
                from anthropic import Anthropic
                from pydantic import BaseModel as _BM, Field as _F

                class _Rel(_BM):
                    source_id: str
                    target_id: str
                    relation: str
                    reasoning: str
                    confidence: float = _F(ge=0.0, le=1.0, default=0.8)

                class _RelBatch(_BM):
                    relationships: list[_Rel]

                client = instructor.from_anthropic(Anthropic(api_key=_os.environ["ANTHROPIC_API_KEY"]))

                node_summaries = [
                    {"id": n.id, "type": n.type, "name": n.name, "description": n.description[:200]}
                    for n in nodes[:50]  # 최대 50개 (토큰 절약)
                ]
                existing = [{"src": e.source_id, "tgt": e.target_id, "rel": e.relation} for e in structural_edges]

                result_llm: _RelBatch = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system="""You are an MBSE traceability analyst.
Find NEW relationships not already in the existing list.
Relations: satisfies | implements | verifies | affects | blocks | allocates | decomposes | realizes
ALL reasoning must start with [INFERRED].
Return max 10 most important relationships.""",
                    messages=[{"role": "user", "content": f"""Nodes:
{_json.dumps(node_summaries, ensure_ascii=False, indent=2)}

Already known:
{_json.dumps(existing, ensure_ascii=False)}

Find NEW traceability relationships."""}],
                    response_model=_RelBatch,
                    max_retries=2,
                )

                valid_rels = {"satisfies", "implements", "verifies", "affects", "blocks", "allocates", "decomposes", "realizes"}
                for rel in result_llm.relationships:
                    if rel.source_id not in node_map or rel.target_id not in node_map:
                        continue
                    if rel.relation not in valid_rels:
                        continue
                    reasoning = rel.reasoning if rel.reasoning.startswith("[INFERRED]") else "[INFERRED] " + rel.reasoning
                    llm_edges.append(OntologyEdge(
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        relation=rel.relation,  # type: ignore[arg-type]
                        reasoning=reasoning,
                        is_inferred=True,
                    ))
                    _log2(f"  [LLM] {rel.source_id} --{rel.relation}--> {rel.target_id} (신뢰도: {rel.confidence:.0%})")

            except Exception as exc:
                _log2(f"⚠️ LLM 추론 실패: {exc}")

            all_edges = structural_edges + llm_edges
            st.session_state.ip_edges = all_edges
            st.session_state.ip_nodes = nodes
            st.session_state.ip_step = max(st.session_state.ip_step, 6)

            _log2(f"\n📊 엣지 합계: 구조적 {len(structural_edges)}개 + LLM 추론 {len(llm_edges)}개 = {len(all_edges)}개")
            st.success(f"Traceability 추론 완료: {len(all_edges)}개 엣지")

# ── STEP 5: 최종 리포트 + 커밋 ───────────────────────────────────────────────

with st.expander(
    "Step 5 — 최종 리포트 + Knowledge Graph 커밋",
    expanded=(st.session_state.ip_step == 6),
):
    if st.session_state.ip_step < 6:
        st.warning("Step 4 Traceability 추론을 먼저 완료하세요.")
    else:
        final_results = st.session_state.ip_final_results
        edges = st.session_state.get("ip_edges", [])
        nodes: list = st.session_state.get("ip_nodes", [])

        from collections import Counter

        type_counts = Counter(r.mbse_type for r in final_results)
        conf_high   = sum(1 for r in final_results if r.confidence >= 0.80)
        conf_mid    = sum(1 for r in final_results if 0.60 <= r.confidence < 0.80)
        conf_low    = sum(1 for r in final_results if r.confidence < 0.60)
        struct_edges = [e for e in edges if not e.is_inferred]
        inferred_edges = [e for e in edges if e.is_inferred]

        # 갭 분석
        node_ids = {r.doc_id for r in final_results}
        connected_ids: set[str] = set()
        for e in edges:
            connected_ids.add(e.source_id)
            connected_ids.add(e.target_id)
        orphans = [r for r in final_results if r.doc_id not in connected_ids]

        req_ids = {r.doc_id for r in final_results if r.mbse_type == "Requirement"}
        verified_req_ids = {e.target_id for e in edges if e.relation == "verifies"}
        unverified_reqs = req_ids - verified_req_ids

        # ── 리포트 표시 ──────────────────────────────────────────────────────
        st.markdown("### 분류 요약")
        cols = st.columns(5)
        for i, mbse_type in enumerate(_VALID_TYPES):
            cnt = type_counts.get(mbse_type, 0)
            color = _TYPE_COLOR[mbse_type]
            cols[i].markdown(
                f'<div style="background:{BG2};border-left:4px solid {color};'
                f'padding:10px 14px;border-radius:6px;">'
                f'<div style="color:{color};font-size:11px;font-weight:700;">{mbse_type.replace("_"," ")}</div>'
                f'<div style="color:{TEXT};font-size:1.5rem;font-weight:700;">{cnt}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 신뢰도 분포")
        c1, c2, c3 = st.columns(3)
        c1.metric("HIGH ≥ 80%", conf_high, help="자동 확정")
        c2.metric("MEDIUM 60~80%", conf_mid, help="검토 권장")
        c3.metric("LOW < 60%", conf_low, help="수동 분류 필요")

        st.markdown("### Traceability")
        c1, c2, c3 = st.columns(3)
        c1.metric("구조적 엣지", len(struct_edges))
        c2.metric("AI 추론 엣지", len(inferred_edges))
        c3.metric("총 엣지", len(edges))

        st.markdown("### 갭 분석")
        if orphans:
            st.warning(f"⚠️ 고아 노드 (링크 없음): {len(orphans)}개 — {', '.join(r.doc_id for r in orphans[:5])}{'...' if len(orphans) > 5 else ''}")
        else:
            st.success("고아 노드 없음")

        if unverified_reqs:
            st.warning(f"⚠️ 검증 없는 요구사항: {len(unverified_reqs)}개 — {', '.join(list(unverified_reqs)[:5])}{'...' if len(unverified_reqs) > 5 else ''}")
        else:
            st.success("모든 요구사항에 Verification 연결됨")

        # 체인 완성도
        complete_chains = 0
        for req_id in req_ids:
            has_arch = any(
                e.source_id == req_id and e.relation in ("allocates", "decomposes")
                for e in edges
            )
            has_verif = req_id in verified_req_ids
            if has_arch and has_verif:
                complete_chains += 1
        partial_chains = len(req_ids) - complete_chains
        if req_ids:
            st.markdown(
                f'<div style="background:{BG2};border:1px solid {BORDER};border-radius:8px;padding:12px;">'
                f'<span style="color:{TEXT_DIM};font-size:13px;">트레이서빌리티 체인 완성도</span><br>'
                f'<span style="color:{NODE_DESIGN};font-size:1.1rem;font-weight:700;">완성: {complete_chains}개</span>'
                f' <span style="color:{TEXT_DIM};">/ 부분: {partial_chains}개 / 요구사항 총: {len(req_ids)}개</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── KG 커밋 ──────────────────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Knowledge Graph 커밋")

        if st.session_state.ip_committed:
            st.success("이미 Knowledge Graph에 커밋되었습니다.")
        else:
            if st.button("Knowledge Graph에 커밋", type="primary", key="commit_kg"):
                from src.graph.factory import get_backend
                try:
                    backend = get_backend()
                    for node in nodes:
                        backend.merge_node(node)
                    for edge in edges:
                        backend.merge_edge(edge)
                    st.session_state.ip_committed = True
                    st.success(
                        f"커밋 완료 — 노드: {len(nodes)}개, 엣지: {len(edges)}개\n"
                        f"Graph View 페이지에서 확인하세요."
                    )
                except Exception as exc:
                    st.error(f"커밋 실패: {exc}")

        if st.button("파이프라인 초기화", key="reset_pipeline"):
            for k in list(st.session_state.keys()):
                if k.startswith("ip_"):
                    del st.session_state[k]
            st.rerun()
