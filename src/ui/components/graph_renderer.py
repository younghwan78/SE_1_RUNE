"""pyvis-based Knowledge Graph renderer for Streamlit."""
import html
import json
import tempfile
from pathlib import Path
from typing import Optional

from pyvis.network import Network

from src.models.ontology import OntologyEdge, OntologyNode, SubGraph

# ── Node colours — desaturated, harmonised with dark-slate (#13131f) theme ──
# Saturation kept low so nodes feel embedded in the background, not glowing neon.
# Each hue still clearly distinct when viewed together.
NODE_COLORS: dict[str, str] = {
    "Requirement":       "#5c84ad",   # steel blue     — top-level customer demand
    "Architecture_Block":"#7b6cdb",   # slate indigo   — matches theme primary, structural
    "Design_Spec":       "#4e8c68",   # sage green     — implementation specification
    "Verification":      "#9e7848",   # warm sienna    — test / evidence
    "Issue":             "#9e5555",   # dusty rose-red — bug / risk
}

NODE_SHAPES: dict[str, str] = {
    "Requirement":       "diamond",   # ◆ sharp edges = customer-facing constraint
    "Architecture_Block":"square",    # ■ solid block  = structural decision
    "Design_Spec":       "dot",       # ● round/fluid  = implementation detail
    "Verification":      "triangle",  # ▲ upward arrow = proof / validation
    "Issue":             "star",      # ★ attention    = bug / risk / blocker
}

RELATION_COLORS: dict[str, str] = {
    "satisfies":  "#5c84ad",   # blue  — arch satisfies requirement
    "implements": "#4e8c68",   # green — design implements arch
    "verifies":   "#9e7848",   # amber — test verifies node
    "affects":    "#9e5555",   # red   — issue affects node
    "blocks":     "#8c7a3a",   # gold  — blocker relationship
}

# Graph canvas background — matches page BG
_GRAPH_BG = "#13131f"


def _rgba(hex_color: str, alpha: float) -> str:
    """Convert #rrggbb to rgba(r,g,b,a)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _lighten(hex_color: str, factor: float = 0.25) -> str:
    """Mix hex color toward white by factor (0=original, 1=white)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_pyvis_html(
    subgraph: SubGraph,
    height: int = 750,
    filter_types: Optional[set[str]] = None,
    highlight_orphans: bool = False,
    orphan_ids: Optional[set[str]] = None,
    selected_node_id: Optional[str] = None,
) -> str:
    """Build pyvis HTML string from a SubGraph with custom dark tooltips."""
    net = Network(
        height=f"{height}px",
        width="100%",
        bgcolor=_GRAPH_BG,
        font_color="#dddaf0",
        directed=True,
    )
    net.set_options(_physics_options())

    # tooltip_data: node_id → HTML string (injected via JS, bypasses pyvis escaping)
    tooltip_data: dict[str, str] = {}

    visible_ids: set[str] = set()
    for node in subgraph.nodes:
        if filter_types and node.type not in filter_types:
            continue
        visible_ids.add(node.id)
        tooltip_data[node.id] = _node_tooltip_html(node)
        _add_node(net, node, highlight_orphans, orphan_ids or set(), selected_node_id)

    edge_tooltip_data: dict[str, str] = {}
    for i, edge in enumerate(subgraph.edges):
        if edge.source_id not in visible_ids or edge.target_id not in visible_ids:
            continue
        edge_key = f"{edge.source_id}__{edge.relation}__{edge.target_id}"
        edge_tooltip_data[edge_key] = _edge_tooltip_html(edge)
        _add_edge(net, edge, edge_key)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        tmp_path = Path(f.name)

    net.save_graph(str(tmp_path))
    raw_html = tmp_path.read_text(encoding="utf-8")
    tmp_path.unlink(missing_ok=True)

    # Patch: inject custom tooltip system + dark theme CSS
    raw_html = _inject_custom_tooltips(raw_html, tooltip_data, edge_tooltip_data)
    return raw_html


def _add_node(
    net: Network,
    node: OntologyNode,
    highlight_orphans: bool,
    orphan_ids: set[str],
    selected_node_id: Optional[str],
) -> None:
    color      = NODE_COLORS.get(node.type, "#888888")
    color_lite = _lighten(color, 0.22)   # brighter background on hover/select
    color_rim  = _lighten(color, 0.35)   # border — noticeably brighter than fill
    glow_base  = _rgba(color, 0.40)      # default glow

    border_width = 2
    border_color = color_rim

    if highlight_orphans and node.id in orphan_ids:
        border_color = "#dd3333"
        border_width = 3
    if selected_node_id and node.id == selected_node_id:
        border_color = "#ffffff"
        border_width = 3

    short_name = node.name[:22] + "…" if len(node.name) > 22 else node.name
    label = f"{node.id}\n{short_name}"

    net.add_node(
        node.id,
        label=label,
        title="",
        color={
            "background":  color,
            "border":      border_color,
            "highlight":   {"background": color_lite, "border": "#ffffff"},
            "hover":       {"background": color_lite, "border": color_rim},
        },
        size=26,
        borderWidth=border_width,
        borderWidthSelected=4,
        shape=NODE_SHAPES.get(node.type, "dot"),
        font={
            "color":       "#ffffff",
            "size":        13,
            "face":        "Segoe UI, -apple-system, sans-serif",
            "strokeWidth": 3,
            "strokeColor": "rgba(0,0,0,0.7)",
        },
        # Base shadow — JS will upgrade it with color-matched glow per connection count
        shadow={"enabled": True, "color": glow_base, "size": 18, "x": 0, "y": 2},
    )


def _add_edge(net: Network, edge: OntologyEdge, edge_key: str) -> None:
    color      = RELATION_COLORS.get(edge.relation, "#888888")
    color_faint= _rgba(color, 0.65)
    dashes     = edge.is_inferred
    line_width = 2.0 if not edge.is_inferred else 1.4

    net.add_edge(
        edge.source_id,
        edge.target_id,
        title="",
        label=edge.relation,
        color={"color": color_faint, "hover": color, "highlight": color},
        dashes=dashes,
        arrows={"to": {"enabled": True, "scaleFactor": 0.8, "type": "arrow"}},
        font={
            "color":       color,
            "size":        14,          # was 10 — noticeably larger
            "face":        "Segoe UI, -apple-system, sans-serif",
            "align":       "middle",
            "strokeWidth": 4,
            "strokeColor": "#13131f",   # matches page bg — sharp text cutout
            "background":  "#1c1c2e",   # pill background — key for readability
            "vadjust":     -4,          # nudge label slightly above the line
        },
        smooth={"type": "curvedCW", "roundness": 0.15},
        width=line_width,
        selectionWidth=2.5,
        hoverWidth=2.0,
    )


# ------------------------------------------------------------------ tooltip HTML builders

def _node_tooltip_html(node: OntologyNode) -> str:
    color = NODE_COLORS.get(node.type, "#888888")
    node_id   = html.escape(node.id)
    node_type = html.escape(node.type.replace("_", " "))
    status    = html.escape(node.status)
    labels    = html.escape(", ".join(node.labels[:5])) if node.labels else "—"

    raw_desc = node.description[:220]
    if len(node.description) > 220:
        raw_desc += "…"
    desc = html.escape(raw_desc)

    return (
        f"<div style='min-width:220px;max-width:300px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
        f"  <span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};flex-shrink:0;'></span>"
        f"  <b style='font-size:13px;color:#fff;'>{node_id}</b>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;font-size:11px;'>"
        f"  <tr><td style='color:#888;padding:1px 6px 1px 0;'>Type</td>"
        f"      <td style='color:{color};font-weight:600;'>{node_type}</td></tr>"
        f"  <tr><td style='color:#888;padding:1px 6px 1px 0;'>Status</td>"
        f"      <td style='color:#ddd;'>{status}</td></tr>"
        f"  <tr><td style='color:#888;padding:1px 6px 1px 0;'>Labels</td>"
        f"      <td style='color:#aaa;font-size:10px;'>{labels}</td></tr>"
        f"</table>"
        f"<div style='margin-top:6px;padding-top:6px;border-top:1px solid #333;"
        f"color:#ccc;font-size:11px;line-height:1.4;'>{desc}</div>"
        f"</div>"
    )


def _edge_tooltip_html(edge: OntologyEdge) -> str:
    color = RELATION_COLORS.get(edge.relation, "#888888")
    src      = html.escape(edge.source_id)
    tgt      = html.escape(edge.target_id)
    relation = html.escape(edge.relation)
    raw_r    = edge.reasoning[:180]
    if len(edge.reasoning) > 180:
        raw_r += "…"
    reasoning = html.escape(raw_r)
    tag = "🤖 AI Inferred" if edge.is_inferred else "🔗 Explicit Link"
    tag_color = "#a855f7" if edge.is_inferred else "#4e9af1"

    return (
        f"<div style='min-width:200px;max-width:300px;'>"
        f"<div style='font-size:12px;margin-bottom:6px;'>"
        f"  <b style='color:#fff;'>{src}</b>"
        f"  <span style='color:{color};margin:0 5px;'>→ {relation} →</span>"
        f"  <b style='color:#fff;'>{tgt}</b>"
        f"</div>"
        f"<div style='margin-bottom:4px;'>"
        f"  <span style='background:{tag_color}22;color:{tag_color};font-size:10px;"
        f"border:1px solid {tag_color}44;border-radius:3px;padding:1px 5px;'>{tag}</span>"
        f"</div>"
        f"<div style='color:#ccc;font-size:11px;line-height:1.4;'>{reasoning}</div>"
        f"</div>"
    )


# ------------------------------------------------------------------ JS/CSS injection

def _inject_custom_tooltips(
    raw_html: str,
    node_tooltips: dict[str, str],
    edge_tooltips: dict[str, str],
) -> str:
    """Replace vis.js default tooltip with a fully custom dark-theme floating div."""

    node_tooltips_json = json.dumps(node_tooltips, ensure_ascii=False)
    edge_tooltips_json = json.dumps(edge_tooltips, ensure_ascii=False)

    custom_css = """
<style>
body { background: #0e1117 !important; margin: 0; }

/* Hover tooltip */
#kg-tooltip {
    position: fixed;
    z-index: 99999;
    display: none;
    background: #1c1c2e;
    border: 1px solid #2e2e4a;
    border-radius: 8px;
    padding: 10px 12px;
    color: #dddaf0;
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 12px;
    line-height: 1.5;
    box-shadow: 0 8px 24px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.05);
    pointer-events: none;
    max-width: 320px;
    word-wrap: break-word;
    backdrop-filter: blur(8px);
    transition: opacity 0.1s ease;
}

/* Click popup panel */
#kg-panel {
    position: fixed;
    z-index: 99998;
    display: none;
    background: #1c1c2e;
    border: 1px solid #2e2e4a;
    border-radius: 10px;
    padding: 14px 16px 12px;
    color: #dddaf0;
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 12px;
    line-height: 1.6;
    box-shadow: 0 12px 40px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.06);
    width: 300px;
    word-wrap: break-word;
    backdrop-filter: blur(12px);
}
#kg-panel-close {
    position: absolute;
    top: 8px;
    right: 10px;
    cursor: pointer;
    color: #666;
    font-size: 16px;
    line-height: 1;
    padding: 2px 5px;
    border-radius: 4px;
    transition: color 0.15s, background 0.15s;
}
#kg-panel-close:hover { color: #fff; background: rgba(255,255,255,0.1); }

/* Override vis.js built-in tooltip */
div.vis-tooltip { display: none !important; }

/* Canvas container */
#mynetwork {
    border-radius: 10px;
    border: 1px solid #2e2e4a !important;
    box-shadow: inset 0 0 40px rgba(0,0,0,0.3);
}
</style>
"""

    custom_js = f"""
<script type="text/javascript">
(function() {{
    var nodeTooltips = {node_tooltips_json};
    var edgeTooltips = {edge_tooltips_json};

    // ── Hover tooltip ──────────────────────────────────────────────
    var tip = document.createElement('div');
    tip.id = 'kg-tooltip';
    document.body.appendChild(tip);

    var hideTimer = null;

    function showTip(htmlContent, x, y) {{
        clearTimeout(hideTimer);
        tip.innerHTML = htmlContent;
        tip.style.display = 'block';
        positionTip(x, y);
    }}

    function hideTip() {{
        hideTimer = setTimeout(function() {{
            tip.style.display = 'none';
        }}, 120);
    }}

    function positionTip(x, y) {{
        var tw = tip.offsetWidth  || 300;
        var th = tip.offsetHeight || 100;
        var wx = window.innerWidth;
        var wy = window.innerHeight;
        var lx = x + 16;
        var ly = y - 10;
        if (lx + tw > wx - 10) lx = x - tw - 16;
        if (ly + th > wy - 10) ly = wy - th - 10;
        if (ly < 10) ly = 10;
        tip.style.left = lx + 'px';
        tip.style.top  = ly + 'px';
    }}

    document.addEventListener('mousemove', function(e) {{
        if (tip.style.display === 'block') {{
            positionTip(e.clientX, e.clientY);
        }}
    }});

    // ── Click panel ────────────────────────────────────────────────
    var container = document.getElementById('mynetwork');
    var panel = document.createElement('div');
    panel.id = 'kg-panel';
    panel.innerHTML = '<span id="kg-panel-close">✕</span><div id="kg-panel-body"></div>';
    // Insert into the network container so it sits inside the graph area
    document.body.appendChild(panel);

    document.getElementById('kg-panel-close').addEventListener('click', function() {{
        panel.style.display = 'none';
        if (typeof network !== 'undefined') network.unselectAll();
    }});

    function showPanel(htmlContent, domX, domY) {{
        document.getElementById('kg-panel-body').innerHTML = htmlContent;
        panel.style.display = 'block';
        var pw = 320;
        var ph = panel.offsetHeight || 220;
        var wx = window.innerWidth;
        var wy = window.innerHeight;
        var lx = domX + 20;
        var ly = domY - Math.floor(ph / 2);
        if (lx + pw > wx - 10) lx = domX - pw - 20;
        if (ly + ph > wy - 10) ly = wy - ph - 10;
        if (ly < 10) ly = 10;
        panel.style.left = lx + 'px';
        panel.style.top  = ly + 'px';
    }}

    // ── Hook into vis.js network ───────────────────────────────────
    function hookNetwork() {{
        if (typeof network === 'undefined') {{
            setTimeout(hookNetwork, 200);
            return;
        }}

        // Hover events
        network.on('hoverNode', function(p) {{
            var h = nodeTooltips[p.node];
            if (h) showTip(h, p.event.clientX, p.event.clientY);
        }});
        network.on('blurNode', function() {{ hideTip(); }});

        network.on('hoverEdge', function(p) {{
            var edge = edges.get(p.edge);
            if (edge) {{
                var key = edge.from + '__' + edge.label + '__' + edge.to;
                var h = edgeTooltips[key];
                if (h) showTip(h, p.event.clientX, p.event.clientY);
            }}
        }});
        network.on('blurEdge', function() {{ hideTip(); }});

        // Convert canvas-relative coords to viewport (fixed) coords
        function canvasToViewport(canvasPos) {{
            var rel = network.canvasToDOM(canvasPos);
            var rect = container.getBoundingClientRect();
            return {{ x: rect.left + rel.x, y: rect.top + rel.y }};
        }}

        // Click events → pinned panel
        network.on('selectNode', function(p) {{
            if (!p.nodes || p.nodes.length === 0) return;
            var nid = p.nodes[0];
            var h = nodeTooltips[nid];
            if (!h) return;
            tip.style.display = 'none';
            var vp = canvasToViewport(network.getPosition(nid));
            showPanel(h, vp.x, vp.y);
        }});

        network.on('selectEdge', function(p) {{
            if (!p.edges || p.edges.length === 0) return;
            var edge = edges.get(p.edges[0]);
            if (!edge) return;
            var key = edge.from + '__' + edge.label + '__' + edge.to;
            var h = edgeTooltips[key];
            if (!h) return;
            tip.style.display = 'none';
            var posA = network.getPosition(edge.from);
            var posB = network.getPosition(edge.to);
            var mid = {{ x: (posA.x + posB.x) / 2, y: (posA.y + posB.y) / 2 }};
            var vp = canvasToViewport(mid);
            showPanel(h, vp.x, vp.y);
        }});

        network.on('deselectNode', function() {{
            panel.style.display = 'none';
        }});
        network.on('deselectEdge', function() {{
            panel.style.display = 'none';
        }});

        // Resize nodes + apply color-matched glow based on connection count
        var allNodeIds = nodes.getIds();
        var updates = [];
        allNodeIds.forEach(function(nid) {{
            var nodeData = nodes.get(nid);
            var deg = network.getConnectedEdges(nid).length;
            var sz     = Math.max(22, Math.min(50, 22 + deg * 5));
            var glowSz = Math.max(14, Math.min(30, 12 + deg * 3));
            var bg = (nodeData.color && nodeData.color.background) || '#888888';
            var r = parseInt(bg.slice(1,3), 16);
            var g = parseInt(bg.slice(3,5), 16);
            var b = parseInt(bg.slice(5,7), 16);
            var glowColor = 'rgba(' + r + ',' + g + ',' + b + ',0.45)';
            updates.push({{
                id: nid,
                size: sz,
                shadow: {{ enabled: true, color: glowColor, size: glowSz, x: 0, y: 2 }}
            }});
        }});
        nodes.update(updates);
    }}

    window.addEventListener('load', function() {{
        setTimeout(hookNetwork, 400);
    }});
}})();
</script>
"""

    # Insert CSS before </head>
    raw_html = raw_html.replace("</head>", custom_css + "\n</head>")
    # Insert JS before </body>
    raw_html = raw_html.replace("</body>", custom_js + "\n</body>")
    return raw_html


def _physics_options() -> str:
    return """
    {
      "physics": {
        "enabled": true,
        "forceAtlas2Based": {
          "gravitationalConstant": -90,
          "centralGravity": 0.008,
          "springLength": 150,
          "springConstant": 0.06,
          "damping": 0.45,
          "avoidOverlap": 1.0
        },
        "solver": "forceAtlas2Based",
        "stabilization": { "enabled": true, "iterations": 180 }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 9999,
        "hideEdgesOnDrag": false,
        "navigationButtons": true,
        "keyboard": true,
        "zoomView": true
      },
      "edges": {
        "smooth": { "type": "curvedCW", "roundness": 0.15 }
      }
    }
    """
