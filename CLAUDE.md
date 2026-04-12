# 🤖 CLAUDE.md: Req-Tracker AI Agent Guidelines

## 🎯 Project Context
Build an autonomous agent extracting MBSE traceability (Req → Arch → Design → Verif) from JIRA tickets into a Neo4j Knowledge Graph, requiring human-in-the-loop approval via Streamlit.

**POC Strategy (Demo-First)**: Use realistic dummy data (Ulysses Camera HAL, 18 tickets) to demonstrate KG value over flat JIRA — without requiring real JIRA access. Graph UI ships first (D+1~2), LLM pipeline second (D+3~5).

## 🛠️ Tech Stack & Standard Commands
- **Environment**: Python 3.11+, use `uv` for dependency management.
- **Core Libraries**:
  - Orchestration: `langgraph`
  - LLM Interface: `langchain-anthropic` (model: `claude-sonnet-4-6`)
  - Data Validation: `pydantic`, `instructor`
  - Graph DB (Production): `neo4j` (Python driver)
  - Graph DB (Demo): `networkx` (zero-infra fallback)
  - UI: `streamlit`
  - Graph Visualization: `pyvis` (vis.js, dark theme) — custom JS injection for tooltips & click panel
  - Staging: `sqlite3`
- **Run UI**: `streamlit run src/ui/app.py`
- **Run Agent Loop**: `python -m src.agent.graph`

## 🏗️ Architecture Patterns

### Data Source Abstraction
```python
# DATASOURCE_MODE=dummy (default) | jira
get_adapter() -> DataSourceAdapter  # src/datasource/factory.py
```

### Graph Backend Abstraction
```python
# GRAPH_BACKEND=networkx (default) | neo4j
get_backend() -> GraphBackend  # src/graph/factory.py
```
Always use MERGE semantics. NetworkX backend serializes to `data/exports/graph.gpickle` for session persistence.

### Graph Visualization (pyvis)
- Dark theme: `bgcolor="#13131f"` (matches page BG), `font_color="#dddaf0"`
- Node colors — desaturated, theme-harmonized (do NOT use vivid/neon colors):
  - Requirement: `#5c84ad` (steel blue), shape=diamond
  - Architecture_Block: `#7b6cdb` (slate indigo = PRIMARY), shape=square
  - Design_Spec: `#4e8c68` (sage green), shape=dot
  - Verification: `#9e7848` (warm sienna), shape=triangle
  - Issue: `#9e5555` (dusty rose-red), shape=star
- Node size ∝ connection count: dynamic JS resize `size = max(22, min(50, 22 + deg*5))`
- Solid edges = original JIRA links; Dashed edges = AI-inferred (`is_inferred=True`)
- Embed via `st.components.v1.html(html_content, height=780)`
- **Tooltip pattern**: NEVER use `node.title` for HTML. Set `title=""`, disable vis.js tooltip via
  `tooltipDelay:9999` + CSS `div.vis-tooltip{display:none}`, inject custom JS hover handler.
- **Click popup**: `network.on('selectNode', ...)` + `canvasToDOM()` + `getBoundingClientRect()`
  for `position:fixed` panel placement. See `graph_renderer.py:_inject_custom_tooltips`.
- **Edge direction**: edges point child→parent (e.g. CAM-010→satisfies→CAM-001).
  Use `nx.ancestors(G, req_id)` (NOT descendants) for traceability traversal.

## 🚨 Strict Engineering Rules (The Vibe)
1. **Zero Hardcoding**: NEVER hardcode JIRA tokens, API keys, or DB credentials. Strictly use `os.getenv()` and `.env`.
2. **Pydantic First**: All LLM outputs MUST be strongly typed using `pydantic.BaseModel` combined with `instructor`. Do not rely on raw JSON parsing.
3. **Fail Fast**: Do not swallow exceptions for JIRA API or Neo4j connection failures. Crash loudly with clear stack traces.
4. **Type Hinting**: 100% Python type hints are mandatory for all functions, classes, and variables.
5. **Idempotency**: Graph DB queries (Neo4j Cypher) MUST use `MERGE` instead of `CREATE`. NetworkX backend must also check for duplicates before adding nodes/edges.
6. **Active Verification**: When extracting traceability, if a ticket contains test scripts, you MUST use the Sandbox Tool to execute it. Record the result in the `execution_status` and `execution_log` fields of the `OntologyEdge`.

## 🧠 Agentic Reasoning Rules (For LLM Prompts)
- **Mandatory Reasoning**: Always enforce a `reasoning` string field in the Pydantic schema when the LLM generates a relationship edge. The LLM must explain *why* it connected two components.
- **Inferred Link Tagging**: AI-derived edges MUST have `reasoning` prefixed with `[INFERRED]` and `is_inferred=True`. This distinguishes them visually from original JIRA links (dashed vs solid edges).
- **Entity Mapping**: Default mapping strategy → Epics = `Requirement`, Stories/Tasks = `Architecture_Block` or `Design_Spec`, Bugs = `Issue`.
- **Gap Detection**: The LangGraph pipeline must detect 8 gap types: orphan nodes, missing verification, implementation conflicts, cross-domain hidden impacts.
- **UI Theme**: All pages must call `inject_global_css()` after `set_page_config()`. Dark slate theme palette defined in `src/ui/components/styles.py` (BG=#13131f, PRIMARY=#7b6cdb). `.streamlit/config.toml` alone is insufficient — CSS injection required for dataframes, expanders, etc.
- **Honest Metrics**: Do NOT improve Verification Coverage KPI by fabricating test plans. Only flag the gap. This increases demo credibility.

## 📁 Project Structure
```
src/
  models/          # OntologyNode, OntologyEdge, ProposedUpdate, GapFinding
  datasource/      # DataSourceAdapter ABC + DummyAdapter + JiraAdapter + factory
  graph/           # GraphBackend ABC + NetworkXBackend + Neo4jBackend + factory
  agent/           # LangGraph nodes, edges, graph assembly, prompts
  staging/         # SQLite pending approval queue
  metrics/         # KPI computation (coverage, orphan rate, chain completeness)
  ui/
    app.py
    pages/         # 01_flat_view, 02_graph_view, 03_agent_run, 04_approvals, 05_metrics
    components/    # graph_renderer.py (pyvis wrapper)
data/dummy/        # ulysses_tickets.json (18 tickets + hardcoded relations)
tests/unit/
tests/integration/
```

**Local Venv Sandbox**: For code execution tasks, NEVER run code directly in the host environment. You MUST create an isolated virtual environment (`python -m venv .agent_venv`) and execute scripts using the isolated binary (`.agent_venv/bin/python`). Use the `subprocess` module with tight timeouts (e.g., `timeout=30`).
