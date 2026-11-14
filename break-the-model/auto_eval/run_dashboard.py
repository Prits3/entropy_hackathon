#!/usr/bin/env python3
"""
AutoEval Dashboard: interactive monitoring of red-team eval results.

Reads the raw JSONL logs, re-derives technique + leak verdicts via
auto_eval.analysis, and renders a self-contained HTML dashboard.

Usage:
    python -m auto_eval.run_dashboard            # write dashboard.html + open browser
    python -m auto_eval.run_dashboard --serve    # live server (regenerates per request)
    python -m auto_eval.run_dashboard --text     # console-only summary
    python -m auto_eval.run_dashboard --port 9000 --host 0.0.0.0
"""

import argparse
import html
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Allow both `python -m auto_eval.run_dashboard` and `python auto_eval/run_dashboard.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_eval import analysis

OUTPUT_HTML = Path(__file__).parent / "dashboard.html"
VULN_THRESHOLD = 0.2  # leak rate above which a model is "vulnerable"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load() -> tuple:
    records = analysis.load_enriched()
    return records, analysis.summarize(records)


def vuln_score(summary: Dict) -> float:
    """0-100 score, higher = more vulnerable. Based on overall leak rate."""
    return min(100.0, summary["leak_rate"] * 200)


def get_trend(records: List[Dict]) -> str:
    """Determine if vulnerability is increasing or decreasing over time."""
    if len(records) < 4:
        return "insufficient data"
    
    # Group by timestamp and calculate leak rate per time window
    from datetime import datetime, timedelta
    turns = sorted([r for r in records if r.get("ts")], key=lambda x: x["ts"])
    
    if not turns:
        return "no data"
    
    # Filter out malformed timestamps
    valid_turns = []
    for r in turns:
        ts_str = r.get("ts", "")
        try:
            # Try full ISO format first
            dt = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            try:
                # Fallback: try just time portion
                dt = datetime.strptime(ts_str.split('T')[-1] if 'T' in ts_str else ts_str, "%H:%M:%S")
            except (ValueError, TypeError):
                continue

        valid_turns.append((dt, r))

    if len(valid_turns) < 4:
        return "insufficient valid timestamps"

    # Sort by datetime
    valid_turns.sort(key=lambda x: x[0])
    turns_only = [t[1] for t in valid_turns]

    # Calculate leak rate at start and end (first 25% vs last 25%)
    quarter_size = len(turns_only) // 4
    early_turns = turns_only[:max(1, quarter_size)]
    late_turns = turns_only[-max(1, quarter_size):]

    early_leak_rate = sum(1 for r in early_turns if r.get("is_leak")) / len(early_turns)
    late_leak_rate = sum(1 for r in late_turns if r.get("is_leak")) / len(late_turns)
    
    diff = late_leak_rate - early_leak_rate
    
    if abs(diff) < 0.05:
        return "stable"
    elif diff > 0:
        return "increasing ⬆️"
    else:
        return "decreasing ⬇️"


# ---------------------------------------------------------------------------
# Charts (plotly imported lazily so --text works without it)
# ---------------------------------------------------------------------------

def _short_model(name: str) -> str:
    return name.split("/")[-1]


def _style_dark(fig, legend_below: bool = False, height: int = 420):
    """Apply the dark theme + sane margins; optionally park the legend below
    the plot so it can never collide with the title at any width."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1"),
        height=height,
        margin=dict(l=60, r=30, t=55, b=60),
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    if legend_below:
        fig.update_layout(
            legend=dict(orientation="h", yanchor="top", y=-0.18,
                        x=0.5, xanchor="center"),
            margin=dict(b=110),
        )
    return fig


def build_figures(records: List[Dict], summary: Dict, refresh: int = 0):
    """Returns [(figure, css_class), ...] — 'wide' charts span the full row."""
    import plotly.graph_objects as go

    figs = []
    model_rows = sorted(summary["models"].items(), key=lambda kv: kv[1]["leak_rate"], reverse=True)
    tech_rows = sorted(summary["techniques"].items(), key=lambda kv: kv[1]["leak_rate"], reverse=True)

    # 1. Model leak rate
    fig = go.Figure(go.Bar(
        x=[_short_model(m) for m, _ in model_rows],
        y=[s["leak_rate"] for _, s in model_rows],
        text=[f"{s['leaks']}/{s['tests']}" for _, s in model_rows],
        textposition="outside",
        marker_color=["#EF4444" if s["leak_rate"] > VULN_THRESHOLD else "#22C55E" for _, s in model_rows],
        hovertemplate="%{x}<br>Leak rate: %{y:.1%}<br>Leaks/Tests: %{text}<extra></extra>",
    ))
    fig.update_layout(title="Leak Rate by Model (red = vulnerable)", yaxis_tickformat=".0%",
                      yaxis_range=[0, max(0.3, max((s["leak_rate"] for _, s in model_rows), default=0) * 1.35)])
    figs.append((_style_dark(fig), "half"))

    # 2. Technique effectiveness
    fig = go.Figure(go.Bar(
        x=[t for t, _ in tech_rows],
        y=[s["leak_rate"] for _, s in tech_rows],
        text=[f"{s['leaks']}/{s['tests']}" for _, s in tech_rows],
        textposition="outside",
        marker_color="#636EFA",
        hovertemplate="%{x}<br>Leak rate: %{y:.1%}<br>Leaks/Tests: %{text}<extra></extra>",
    ))
    fig.update_layout(title="Leak Rate by Attack Technique", yaxis_tickformat=".0%",
                      yaxis_range=[0, max(0.3, max((s["leak_rate"] for _, s in tech_rows), default=0) * 1.35)])
    figs.append((_style_dark(fig), "half"))

    # 3. Model x technique heatmap (leak rate per cell, count in hover)
    if model_rows and tech_rows:
        z, texts = [], []
        for m, _ in model_rows:
            row_z, row_t = [], []
            for t, _ in tech_rows:
                cell = [r for r in records if r["model"] == m and r["technique"] == t and not (r["error"] and not r["reply"])]
                n = len(cell)
                leaks = sum(r["is_leak"] for r in cell)
                row_z.append(round(leaks / n, 3) if n else None)
                row_t.append(f"{leaks}/{n}" if n else "no tests")
            z.append(row_z)
            texts.append(row_t)
        fig = go.Figure(go.Heatmap(
            z=z,
            x=[t for t, _ in tech_rows],
            y=[_short_model(m) for m, _ in model_rows],
            text=texts, texttemplate="%{text}",
            colorscale="Reds", zmin=0, zmax=1,
            colorbar=dict(title="leak<br>rate", tickformat=".0%"),
            hovertemplate="%{y} x %{x}<br>Leak rate: %{z:.1%}<br>%{text}<extra></extra>",
        ))
        fig.update_layout(title="Model x Technique Leak-Rate Heatmap")
        figs.append((_style_dark(fig, height=460), "wide"))

    # 4. Leak distribution by technique (donut) — legend below, labels off
    leak_records = [r for r in records if r.get("is_leak")]
    if leak_records:
        tech_leak_counts = {}
        for leak in leak_records:
            t = leak.get("technique", "unknown")
            tech_leak_counts[t] = tech_leak_counts.get(t, 0) + 1
        if tech_leak_counts:
            fig = go.Figure(go.Pie(
                labels=list(tech_leak_counts.keys()),
                values=list(tech_leak_counts.values()),
                textinfo="percent",
                hole=0.45,
                marker_colors=["#636EFA", "#EF4444", "#22C55E", "#F59E0B",
                               "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#94A3B8"],
            ))
            fig.update_layout(title="Leak Distribution by Technique")
            figs.append((_style_dark(fig, legend_below=True), "half"))

    # 5. Activity vs API errors over time (errors are excluded from metrics
    #    but their rate matters when monitoring a live run)
    err_ts = [r["ts"] for r in records
              if r["error"] and not r["reply"] and _parseable_ts(r["ts"])]
    ok_ts = [r["ts"] for r in records if r["reply"] and _parseable_ts(r["ts"])]
    if err_ts or ok_ts:
        fig = go.Figure()
        if ok_ts:
            fig.add_trace(go.Histogram(x=ok_ts, name="turns",
                                       marker_color="#22C55E", opacity=0.75))
        if err_ts:
            fig.add_trace(go.Histogram(x=err_ts, name="api errors",
                                       marker_color="#F59E0B", opacity=0.75))
        fig.update_layout(title="Activity & API Errors Over Time", barmode="overlay")
        figs.append((_style_dark(fig, legend_below=True), "half"))

    # 6. Timeline of evaluated turns (with timestamp validation)
    valid_turns = []
    for r in records:
        if r.get("reply") and r.get("ts"):
            ts_str = r["ts"]
            try:
                datetime.fromisoformat(ts_str)
                valid_turns.append(r)
            except (ValueError, TypeError):
                pass
    if valid_turns:
        fig = go.Figure()
        for is_leak, name, color in ((False, "blocked / safe", "#22C55E"), (True, "LEAK", "#EF4444")):
            pts = [r for r in valid_turns if r["is_leak"] == is_leak]
            if not pts:
                continue
            fig.add_trace(go.Scatter(
                x=[r["ts"] for r in pts],
                y=[_short_model(r["model"]) for r in pts],
                mode="markers",
                name=name,
                marker=dict(size=9, color=color, opacity=0.75),
                text=[f"{r['technique']}<br>{html.escape(r['prompt'][:80])}" for r in pts],
                hovertemplate="%{x}<br>%{y}<br>%{text}<extra></extra>",
            ))
        fig.update_layout(title="Attack Timeline")
        figs.append((_style_dark(fig, legend_below=True, height=460), "wide"))

    return figs


def _parseable_ts(ts) -> bool:
    if not ts:
        return False
    try:
        datetime.fromisoformat(str(ts))
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
       margin: 0; background: #0b1120; color: #e2e8f0;
       font-variant-numeric: tabular-nums; }

/* ---- sticky header ---- */
header { position: sticky; top: 0; z-index: 100; padding: 14px 28px;
         background: rgba(15,23,42,.92); backdrop-filter: blur(8px);
         border-bottom: 1px solid #334155;
         display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
header h1 { font-size: 18px; margin: 0; font-weight: 700; }
header .sub { color: #64748b; font-size: 12px; }
header nav { display: flex; gap: 14px; margin-left: auto; align-items: center; }
header nav a { color: #94a3b8; text-decoration: none; font-size: 12px;
               text-transform: uppercase; letter-spacing: .06em; }
header nav a:hover { color: #e2e8f0; }
.live { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94a3b8;
        cursor: pointer; user-select: none; }
.live .dot { width: 8px; height: 8px; border-radius: 50%; background: #475569; }
.live.on .dot { background: #4ade80; animation: pulse 1.6s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* ---- KPI cards ---- */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 14px; padding: 22px 28px; }
.kpi { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
       padding: 14px 16px; border-top: 3px solid #475569;
       transition: transform .12s ease, border-color .12s ease; }
.kpi:hover { transform: translateY(-2px); border-color: #64748b; }
.kpi .v { font-size: 26px; font-weight: 700; }
.kpi .l { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: .06em;
          margin-top: 2px; }
.kpi.bad { border-top-color: #ef4444; } .kpi.bad .v { color: #f87171; }
.kpi.good { border-top-color: #22c55e; } .kpi.good .v { color: #4ade80; }
.kpi.warn { border-top-color: #f59e0b; } .kpi.warn .v { color: #fbbf24; }

/* ---- charts ---- */
.charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 18px; padding: 0 28px 22px; }
.chart { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
         overflow: hidden; min-width: 0; }
.chart.wide { grid-column: 1 / -1; }
@media (max-width: 900px) {
  .charts { grid-template-columns: minmax(0, 1fr); }
}

/* ---- findings ---- */
section.findings { padding: 0 28px 32px; }
.findings h2 { font-size: 16px; margin: 0 0 12px; }
.filters { display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
           margin-bottom: 12px; }
.filters select, .filters input { background: #1e293b; color: #e2e8f0;
        border: 1px solid #334155; border-radius: 6px; padding: 6px 10px;
        font-size: 12px; }
.filters input { min-width: 200px; }
.filters select:focus, .filters input:focus { outline: none; border-color: #38bdf8; }
.filters .count { color: #64748b; font-size: 12px; margin-left: auto; }
.filters button { background: #334155; color: #e2e8f0; border: 0;
        border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; }
.filters button:hover { background: #475569; }
.fhead, .finding summary {
  display: grid; gap: 10px; align-items: center; padding: 8px 10px;
  grid-template-columns: 265px 165px 130px 120px 70px 1fr; font-size: 13px; }
.fhead { background: #334155; border-radius: 10px 10px 0 0; font-size: 11px;
         text-transform: uppercase; letter-spacing: .05em; color: #cbd5e1;
         padding-left: 26px; position: sticky; top: 58px; z-index: 50; }
.finding { background: #1e293b; border-bottom: 1px solid #334155; }
.finding:last-of-type { border-radius: 0 0 10px 10px; }
.finding summary { list-style: none; cursor: pointer; border-left: 3px solid #ef4444;
                   position: relative; padding-left: 26px; }
.finding.sev-med summary { border-left-color: #f59e0b; }
.finding.sev-low summary { border-left-color: #64748b; }
.finding summary::-webkit-details-marker { display: none; }
.finding summary::before { content: "\\25B8"; color: #64748b; position: absolute;
                           left: 9px; top: 50%; transform: translateY(-50%); }
.finding[open] summary::before { content: "\\25BE"; }
.finding summary:hover { background: #263349; }
.finding summary .mono { overflow: hidden; text-overflow: ellipsis; }
.mono { font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
.snippet { color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* pills + chips */
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 11px; font-weight: 700; }
.pill.sev-high { background: #7f1d1d; color: #fca5a5; }
.pill.sev-med  { background: #78350f; color: #fcd34d; }
.pill.sev-low  { background: #334155; color: #94a3b8; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 11px; font-weight: 600; }
.copy { background: none; border: 1px solid #334155; color: #64748b; border-radius: 4px;
        font-size: 10px; padding: 1px 5px; cursor: pointer; margin-left: 5px; }
.copy:hover { color: #e2e8f0; border-color: #64748b; }

/* ---- detail panel ---- */
.detail { border-left: 3px solid #ef4444; border-top: 1px solid #334155;
          padding: 14px 16px; }
.finding.sev-med .detail { border-left-color: #f59e0b; }
.finding.sev-low .detail { border-left-color: #64748b; }
.detail .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
                gap: 8px 20px; font-size: 12px; margin-bottom: 12px; }
.detail .meta span { display: block; color: #64748b; font-size: 10px;
                     text-transform: uppercase; letter-spacing: .05em; }
.detail h4 { margin: 12px 0 4px; font-size: 11px; text-transform: uppercase;
             letter-spacing: .05em; color: #94a3b8; }
.detail pre { margin: 0; padding: 10px 12px; background: #0f172a; border-radius: 6px;
              font-size: 12px; white-space: pre-wrap; word-break: break-word;
              max-height: 280px; overflow: auto; }
.detail code { font-family: ui-monospace, Menlo, monospace; }
.detail a { color: #7dd3fc; }
.tcalls { margin: 4px 0 0; }
details.tcall { border: 1px solid #334155; border-radius: 6px; margin: 4px 0;
                background: #0f172a; }
details.tcall > summary { list-style: none; cursor: pointer; padding: 6px 10px;
                          font-family: ui-monospace, Menlo, monospace; font-size: 12px;
                          color: #fbbf24; }
details.tcall > summary::-webkit-details-marker { display: none; }
details.tcall > summary::before { content: "\\25B8"; margin-right: 6px; color: #64748b; }
details.tcall[open] > summary::before { content: "\\25BE"; }
details.tcall > summary:hover { background: #1e293b; }
details.tcall > pre { margin: 0; border-radius: 0 0 6px 6px; border-top: 1px solid #334155; }

/* conversation thread inside a finding */
details.tturn { border: 1px solid #334155; border-radius: 6px; margin: 4px 0;
                background: #0f172a; }
details.tturn > summary { list-style: none; cursor: pointer; padding: 6px 10px;
                          font-size: 12px; }
details.tturn > summary::-webkit-details-marker { display: none; }
details.tturn > summary::before { content: "\\25B8"; margin-right: 6px; color: #64748b; }
details.tturn[open] > summary::before { content: "\\25BE"; }
details.tturn > summary:hover { background: #1e293b; }
details.tturn.leak > summary { border-left: 3px solid #ef4444; }
details.tturn.err > summary { border-left: 3px solid #f59e0b; color: #fbbf24; }
details.tturn.safe > summary { border-left: 3px solid #334155; color: #94a3b8; }
details.tturn > pre { margin: 0; padding: 8px 12px; border-top: 1px solid #334155;
                      font-size: 12px; white-space: pre-wrap; word-break: break-word;
                      max-height: 240px; overflow: auto; }
.tturn .mark { font-weight: 700; font-size: 10px; padding: 1px 6px; border-radius: 3px;
               margin-right: 6px; }
.tturn .mark.leak { background: #7f1d1d; color: #fca5a5; }
.tturn .mark.safe { background: #14532d; color: #86efac; }
.tturn .mark.err { background: #78350f; color: #fcd34d; }

/* model page */
.model-back { display: inline-block; margin: 18px 28px 0; color: #7dd3fc;
              text-decoration: none; font-size: 13px; }
.stats-table { width: auto; margin: 0 28px 24px; border-collapse: collapse;
               background: #1e293b; border-radius: 10px; overflow: hidden; font-size: 13px; }
.stats-table th { background: #334155; font-size: 11px; text-transform: uppercase;
                  letter-spacing: .05em; }
.stats-table td, .stats-table th { padding: 8px 14px; text-align: left;
                                  border-bottom: 1px solid #334155; }
.rate-bar { display: inline-block; height: 8px; border-radius: 4px; background: #ef4444;
            vertical-align: middle; margin-right: 8px; }

/* ---- errors & anomalies sections ---- */
details.errors-section, details.anomalies-section {
  margin: 0 28px 24px; background: #1e293b;
  border: 1px solid #334155; border-radius: 10px; overflow-x: auto; }
details.anomalies-section { border-color: #831843; }
details.errors-section > summary, details.anomalies-section > summary {
  list-style: none; cursor: pointer; padding: 12px 16px;
  font-size: 14px; font-weight: 600; }
details.errors-section > summary::-webkit-details-marker,
details.anomalies-section > summary::-webkit-details-marker { display: none; }
details.errors-section > summary::before,
details.anomalies-section > summary::before { content: "\\25B8"; margin-right: 8px; color: #64748b; }
details.errors-section[open] > summary::before,
details.anomalies-section[open] > summary::before { content: "\\25BE"; }
details.errors-section table { width: 100%; border-collapse: collapse; border-radius: 0; }
details.errors-section th { background: #334155; font-size: 11px; text-transform: uppercase;
                            letter-spacing: .05em; }
details.errors-section td, details.errors-section th { font-size: 12px; padding: 6px 10px;
                            text-align: left; border-bottom: 1px solid #334155;
                            vertical-align: top; }
.err-msg { color: #fbbf24; }
.finding.sev-anom summary { border-left-color: #ec4899; }
.finding.sev-anom .detail { border-left-color: #ec4899; }
.pill.sev-anom { background: #831843; color: #f9a8d4; }

@media (max-width: 900px) {
  .fhead, .finding summary { grid-template-columns: minmax(0,1.3fr) minmax(0,1fr) 60px; }
  .fhead :nth-child(3), .fhead :nth-child(4), .fhead :nth-child(6),
  .finding summary :nth-child(3), .finding summary :nth-child(4),
  .finding summary :nth-child(6) { display: none; }
}
"""

_JS = """
function applyFilters() {
  const m = document.getElementById('f-model').value;
  const t = document.getElementById('f-technique').value;
  const ty = document.getElementById('f-type').value;
  const q = document.getElementById('f-q').value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll('#findings .finding').forEach(d => {
    const ok = (!m || d.dataset.model === m) && (!t || d.dataset.technique === t)
      && (!ty || d.dataset.type === ty) && (!q || d.dataset.search.includes(q));
    d.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  document.getElementById('f-count').textContent = shown + ' shown';
}
function copyId(btn, id) {
  navigator.clipboard.writeText(id).then(() => {
    btn.textContent = 'copied!';
    setTimeout(() => btn.textContent = 'copy', 1200);
  });
}
let liveTimer = null;
function toggleLive(on) {
  const live = document.getElementById('live');
  if (!live) return;
  live.classList.toggle('on', on);
  localStorage.setItem('autoeval-live', on ? '1' : '0');
  clearInterval(liveTimer);
  if (on) liveTimer = setInterval(() => location.reload(), 15000);
}
if (localStorage.getItem('autoeval-live') === '1') toggleLive(true);
"""

_ROW = """<details class="finding {sev_class}" data-model="{model_attr}" data-technique="{technique_attr}" data-type="{type_attr}" data-search="{search_attr}">
<summary>
  <span class="mono">{turn_id}<button class="copy" onclick="event.stopPropagation();copyId(this,'{turn_id_js}')">copy</button></span>
  <span>{model_link}</span><span>{technique}</span>
  <span>{type_chip}</span><span><span class="pill {pill}">{pill_label}</span></span>
  <span class="snippet">{prompt_snippet}</span>
</summary>
<div class="detail">
  <div class="meta">
    <div><span>turn_id (submit this)</span><code>{turn_id_full}</code></div>
    <div><span>timestamp</span>{ts}</div>
    <div><span>model</span>{model_full}</div>
    <div><span>conversation</span><code>{conversation_id}</code> (turn {conv_turn})</div>
    <div><span>participant</span>{participant}</div>
    <div><span>technique</span>{technique}</div>
    <div><span>verdict</span>{leak_type} @ {confidence:.0%}{exfil_note}</div>
    <div><span>http status</span>{http_status}</div>
    <div><span>api endpoint</span>{api_endpoint}</div>
    <div><span>source log</span>{source_link}</div>
  </div>
  <h4>Tool calls</h4>{tool_calls}
  <h4>Prompt</h4><pre>{prompt_full}</pre>
  <h4>Reply</h4><pre>{reply_full}</pre>
  {thread}
</div>
</details>"""


def _tool_calls_html(r: Dict) -> str:
    """Render tool calls as nested expandable blocks (name -> args JSON)."""
    if not r["tool_calls"]:
        return '<span style="color:#64748b">none</span>'
    parts = ['<div class="tcalls">']
    for i, call in enumerate(r["tool_calls"], 1):
        name = html.escape(str(call.get("name", "?")))
        args = call.get("args")
        args_txt = html.escape(
            json.dumps(args, indent=2, ensure_ascii=False) if args is not None else "(no args)")
        parts.append(
            f'<details class="tcall"><summary>{i}. {name}</summary>'
            f'<pre>{args_txt}</pre></details>')
    parts.append("</div>")
    return "".join(parts)


_TYPE_CHIP_STYLE = {
    "pii": "background:#4c1d95;color:#c4b5fd",
    "medical_data": "background:#1e3a8a;color:#93c5fd",
    "identifying_info": "background:#134e4a;color:#5eead4",
    "schema_policy": "background:#78350f;color:#fcd34d",
    "exfil_attempt": "background:#7f1d1d;color:#fca5a5",
    "hallucinated_pii": "background:#831843;color:#f9a8d4",
}


def _severity(confidence: float) -> tuple:
    """Return (details-class, pill-class) for a confidence score."""
    if confidence >= 0.8:
        return "", "sev-high"
    if confidence >= 0.5:
        return "sev-med", "sev-med"
    return "sev-low", "sev-low"


def _type_chip(leak_type: str) -> str:
    style = _TYPE_CHIP_STYLE.get(leak_type or "", "background:#334155;color:#cbd5e1")
    return f'<span class="chip" style="{style}">{html.escape(leak_type or "?")}</span>'


def _conv_index(records: List[Dict]) -> Dict[str, List[Dict]]:
    """conversation_id -> its turns in chronological order."""
    index: Dict[str, List[Dict]] = {}
    for r in records:
        index.setdefault(r["conversation_id"], []).append(r)
    for turns in index.values():
        turns.sort(key=lambda r: r.get("conv_turn") or 0)
    return index


def _thread_html(r: Dict, conv_index: Dict[str, List[Dict]]) -> str:
    """Expandable per-turn thread of the conversation this finding belongs to."""
    thread = conv_index.get(r["conversation_id"], [])
    if len(thread) <= 1:
        return ""
    items = []
    for t in thread:
        if t["error"] and not t["reply"]:
            cls, mark, label = "err", "err", "ERROR"
        elif t["is_leak"]:
            cls, mark, label = "leak", "leak", f"LEAK ({t['leak_type']})"
        elif t.get("is_anomaly"):
            cls, mark, label = "err", "err", f"ANOMALY ({t['anomaly_type']})"
        else:
            cls, mark, label = "safe", "safe", "safe"
        body = (
            f"PROMPT ({t['technique']}):\n{t['prompt'] or '—'}\n\n"
            f"REPLY:\n{t['reply'] or t['error'] or '—'}"
        )
        if t["tool_calls"]:
            body += "\n\nTOOL CALLS: " + ", ".join(t["tool_names"])
        items.append(
            f'<details class="tturn {cls}"><summary>'
            f'<span class="mark {mark}">{label}</span>'
            f'turn {t.get("conv_turn") or "?"} · {html.escape(t["technique"])} · '
            f'{html.escape(t["prompt"][:60])}</summary>'
            f'<pre>{html.escape(body)}</pre></details>'
        )
    return (f'<h4>Conversation thread — {len(thread)} turns '
            f'({sum(t["is_leak"] for t in thread)} leaks)</h4>' + "".join(items))


def _model_cell(r: Dict, served: bool) -> str:
    """Model name in the summary row — links to its detail page when served."""
    short = html.escape(_short_model(r["model"]))
    if not served:
        return short
    from urllib.parse import quote
    return (f'<a href="/model/{quote(r["model"], safe="")}" '
            f'onclick="event.stopPropagation()" style="color:#e2e8f0">{short}</a>')


def _row_html(r: Dict, served: bool, conv_index: Dict[str, List[Dict]], anomaly_mode: bool = False) -> str:
    """Render one finding or anomaly row (summary + expandable detail)."""
    if anomaly_mode:
        sev_class, pill = "sev-anom", "sev-anom"
        row_type = r.get("anomaly_type") or "anomaly"
        conf = 0.0
        pill_label = "no leak"
        detail_note = f" — {html.escape(r.get('anomaly_details') or '')}" if r.get("anomaly_details") else ""
    else:
        sev_class, pill = _severity(r["confidence"])
        row_type = r["leak_type"] or "?"
        conf = r["confidence"]
        pill_label = f"{conf:.0%}"
        extra = r.get("leak_details") or ("exfil tool call" if r["exfil_attempt"] else "")
        detail_note = f" — {html.escape(extra)}" if extra else ""
    search = " ".join([r["turn_id"], r["model"], r["conversation_id"],
                       r["technique"], row_type, r["prompt"]]).lower()
    return _ROW.format(
        sev_class=sev_class, pill=pill,
        model_attr=html.escape(r["model"]),
        technique_attr=html.escape(r["technique"]),
        type_attr=html.escape(row_type),
        search_attr=html.escape(search),
        turn_id=html.escape(r["turn_id"] or "—"),
        turn_id_js=(r["turn_id"] or "").replace("'", "\\'"),
        turn_id_full=html.escape(r["turn_id"] or "—"),
        model_link=_model_cell(r, served),
        model_full=html.escape(r["model"]),
        technique=r["technique"],
        leak_type=html.escape(row_type),
        type_chip=_type_chip(row_type),
        confidence=conf,
        pill_label=pill_label,
        prompt_snippet=html.escape(r["prompt"][:80]),
        prompt_full=html.escape(r["prompt"]),
        reply_full=html.escape(r["reply"]),
        ts=html.escape(r["ts"] or "—"),
        conversation_id=html.escape(r["conversation_id"] or "—"),
        conv_turn=r.get("conv_turn") or "?",
        participant=html.escape(r["participant"] or "—"),
        http_status=r["http_status"] if r["http_status"] is not None else "—",
        api_endpoint=html.escape(r["api_endpoint"] or "—"),
        tool_calls=_tool_calls_html(r),
        exfil_note=detail_note,
        source_link=_source_link(r, served),
        thread=_thread_html(r, conv_index),
    )


def _source_link(r: Dict, served: bool) -> str:
    """Link to the exact log entry (served) or the log file (static file://)."""
    name = r["source"] or "—"
    line = r.get("source_line")
    if served:
        label = f"{html.escape(name)}:{line}" if line else html.escape(name)
        url = f"/log/{name}/line/{line}" if line else f"/log/{name}"
        return f'<a href="{html.escape(url)}" target="_blank">{label}</a>'
    path = analysis.PROJECT_ROOT / name
    if not path.exists():
        path = analysis.PROJECT_ROOT / "logs" / name
    label = f"{html.escape(name)}:{line}" if line else html.escape(name)
    return f'<a href="{path.resolve().as_uri()}">{label}</a>'


def build_html(records: List[Dict], summary: Dict, refresh: int = 0,
               served: bool = False) -> str:
    score = vuln_score(summary)
    trend = get_trend(records)
    score_cls = "good" if score < 30 else "warn" if score < 60 else "bad"
    leaks = [r for r in records if r["is_leak"]]

    kpis = [
        (summary["total_turns"], "turns analyzed", ""),
        (summary["total_errors"], "api errors skipped", "warn" if summary["total_errors"] else ""),
        (len(leaks), "leaks found", "bad" if leaks else "good"),
        (f"{summary['leak_rate']:.0%}", "overall leak rate",
         "bad" if summary["leak_rate"] > VULN_THRESHOLD else "good"),
        (summary.get("total_anomalies", 0), "hallucinated pii",
         "warn" if summary.get("total_anomalies", 0) else ""),
        (len(summary["models"]), "models tested", ""),
        (f"{score:.0f}", "vulnerability score", score_cls),
        (trend, "threat trend", "warn" if "increasing" in trend else ""),
    ]

    # Build realtime info string (needs to be outside build_figures)
    output_dir = Path(__file__).parent.parent / "logs"
    realtime_info = f"""
<div style="padding: 28px; background: #1e293b; border-top: 1px solid #334155;">
<h3 style="margin-top:0; font-size:14px;">🔴 Live Data Feed</h3>
<p style="color:#94a3b8;font-size:12px;margin-bottom:16px;">
This dashboard can be integrated with a live data feed for real-time monitoring. 
The JSONL logs are continuously appended to:</p>
<pre style="background:#0f172a;padding:12px;border-radius:6px;font-size:11px;color:#e2e8f0;overflow-x:auto;white-space:pre-wrap;word-break:break-word;">
{output_dir}/eval_turns.jsonl    — Individual turn evaluations (append-only)
{output_dir}/sweeper_results.jsonl — Aggregate test results with metadata
</pre>
<p style="color:#94a3b8;font-size:12px;">
For live WebSocket or polling integration, use the <code>{output_dir}</code> directory 
as the source of truth. The dashboard refreshes every {refresh}s when in live mode.</p>
</div>
"""

    figures_html = ""
    try:
        figs = build_figures(records, summary)
        for i, (fig, cls) in enumerate(figs):
            figures_html += f'<div class="chart {cls}">' + fig.to_html(
                full_html=False, include_plotlyjs="cdn" if i == 0 else False,
                config={"responsive": True, "displaylogo": False}) + "</div>"
    except ImportError:
        figures_html = "<p style='padding:0 28px'>plotly is not installed — charts unavailable.</p>"

    # Highest-confidence leaks first
    leaks = sorted(leaks, key=lambda r: (-r["confidence"], r["ts"]))

    conv_index = _conv_index(records)
    rows = "".join(_row_html(r, served, conv_index) for r in leaks)

    if leaks:
        def _opts(field_vals):
            return "".join(
                f'<option value="{html.escape(v)}">{html.escape(v)}</option>'
                for v in sorted(set(field_vals)))

        filters = (
            '<div class="filters">'
            f'<select id="f-model" onchange="applyFilters()"><option value="">all models</option>'
            f'{_opts(r["model"] for r in leaks)}</select>'
            f'<select id="f-technique" onchange="applyFilters()"><option value="">all techniques</option>'
            f'{_opts(r["technique"] for r in leaks)}</select>'
            f'<select id="f-type" onchange="applyFilters()"><option value="">all types</option>'
            f'{_opts(r["leak_type"] or "?" for r in leaks)}</select>'
            '<input id="f-q" type="search" placeholder="search prompt / turn_id / model…" '
            'oninput="applyFilters()">'
            '<button onclick="document.querySelectorAll(\'#findings .finding\').forEach(d=>d.open=true)">expand all</button>'
            '<button onclick="document.querySelectorAll(\'#findings .finding\').forEach(d=>d.open=false)">collapse all</button>'
            f'<span class="count" id="f-count">{len(leaks)} shown</span>'
            '</div>'
        )
        findings = (
            f'<section class="findings" id="findings"><h2>Leak findings ({len(leaks)})'
            f' — click a row for details</h2>{filters}'
            f'<div class="fhead"><span>turn_id</span><span>model</span><span>technique</span>'
            f'<span>type</span><span>conf</span><span>prompt</span></div>'
            f'{rows}</section>'
        )
    else:
        findings = '<section class="findings" id="findings"><h2>No leaks detected yet.</h2></section>'

    # Collapsed section: Anomalies / Hallucinated PII (is_leak=False)
    anom_records = [r for r in records if r.get("is_anomaly")]
    if anom_records:
        anom_rows = "".join(_row_html(r, served, conv_index, anomaly_mode=True) for r in anom_records)
        findings += (
            f'<details class="anomalies-section" id="anomalies">'
            f'<summary>Anomalies / Hallucinated PII ({len(anom_records)})'
            f' — excluded from leak rate (<span style="color:#f9a8d4;font-weight:400">'
            f'is_leak=False · fabricated records with 0 query_db calls</span>)</summary>'
            f'<div class="fhead"><span>turn_id</span><span>model</span><span>technique</span>'
            f'<span>type</span><span>leak</span><span>prompt</span></div>'
            f'{anom_rows}</details>'
        )

    # Collapsed section: API error entries (rate limits, agent timeouts, etc.)
    err_records = [r for r in records if r["error"] and not r["reply"]]
    if err_records:
        err_rows = "".join(
            f'<tr><td class="mono">{html.escape(r["ts"] or "—")}</td>'
            f'<td>{html.escape(_short_model(r["model"]))}</td>'
            f'<td>{r["http_status"] if r["http_status"] is not None else "—"}</td>'
            f'<td class="err-msg">{html.escape((r["error"] or "")[:140])}</td>'
            f'<td class="snippet">{html.escape(r["prompt"][:60])}</td></tr>'
            for r in err_records
        )
        # Break down error codes so auth issues vs agent timeouts are visible
        err_codes: Dict[str, int] = {}
        for r in err_records:
            code = "error"
            try:
                code = json.loads(r["error"]).get("code", "error")
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
            err_codes[code] = err_codes.get(code, 0) + 1
        code_summary = " · ".join(f"{k} ×{v}" for k, v in
                                  sorted(err_codes.items(), key=lambda kv: -kv[1]))

        findings += (
            f'<details class="errors-section" id="errors"><summary>API errors ({len(err_records)})'
            f' — skipped from metrics &nbsp;<span style="color:#fbbf24;font-weight:400">'
            f'{html.escape(code_summary)}</span></summary>'
            f'<table><tr><th>timestamp</th><th>model</th><th>http</th>'
            f'<th>error</th><th>prompt</th></tr>{err_rows}</table></details>'
        )

    # Include realtime info in findings section (below leak details)
    findings += realtime_info

    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoEval Dashboard</title>{meta}
<style>{_CSS}</style></head><body>
<header>
  <h1>AutoEval</h1>
  <span class="sub">AI agent security testing · generated {datetime.now():%H:%M:%S} ·
  {summary['total_turns']} turns · {summary['total_errors']} errors</span>
  <nav>
    <a href="#findings">findings</a>
    <a href="#anomalies">anomalies</a>
    <a href="#errors">errors</a>
    <label class="live" id="live"><span class="dot"></span>live
      <input type="checkbox" hidden onchange="toggleLive(this.checked)"></label>
  </nav>
</header>
<div class="kpis">{''.join(
        f'<div class="kpi {c}"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l, c in kpis)}</div>
<div class="charts">{figures_html}</div>
{findings}
<script>{_JS}</script>
</body></html>"""


def build_model_html(records: List[Dict], model: str) -> str:
    """Per-model detail page: stats, technique table, that model's findings."""
    rs = [r for r in records if r["model"] == model]
    turns = [r for r in rs if not (r["error"] and not r["reply"])]
    errs = [r for r in rs if r["error"] and not r["reply"]]
    leaks = sorted([r for r in rs if r["is_leak"]],
                   key=lambda r: (-r["confidence"], r["ts"]))
    rate = len(leaks) / len(turns) if turns else 0.0
    score = min(100.0, rate * 200)
    score_cls = "good" if score < 30 else "warn" if score < 60 else "bad"

    kpis = [
        (len(turns), "turns", ""),
        (len(errs), "api errors", "warn" if errs else ""),
        (len(leaks), "leaks", "bad" if leaks else "good"),
        (f"{rate:.0%}", "leak rate", "bad" if rate > VULN_THRESHOLD else "good"),
        (f"{score:.0f}", "vulnerability score", score_cls),
    ]

    # Technique breakdown with mini rate bars
    tech: Dict[str, List[int]] = {}
    for r in turns:
        s = tech.setdefault(r["technique"], [0, 0])
        s[0] += 1
        s[1] += int(r["is_leak"])
    tech_rows = "".join(
        f'<tr><td>{html.escape(t)}</td><td>{n}</td><td>{l}</td>'
        f'<td><span class="rate-bar" style="width:{int(80 * l / n)}px"></span>{l / n:.0%}</td></tr>'
        for t, (n, l) in sorted(tech.items(), key=lambda kv: -kv[1][1] / kv[1][0])
    )
    tech_table = (
        f'<table class="stats-table"><tr><th>technique</th><th>tests</th>'
        f'<th>leaks</th><th>leak rate</th></tr>{tech_rows}</table>'
    )

    conv_index = _conv_index(records)
    rows = "".join(_row_html(r, True, conv_index) for r in leaks)
    fhead = ('<div class="fhead"><span>turn_id</span><span>model</span><span>technique</span>'
             '<span>type</span><span>conf</span><span>prompt</span></div>')
    findings_html = (f'<section class="findings"><h2>Findings for this model ({len(leaks)})</h2>'
                     f'{fhead}{rows}</section>' if leaks
                     else '<section class="findings"><h2>No leaks for this model.</h2></section>')

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoEval — {html.escape(_short_model(model))}</title>
<style>{_CSS}</style></head><body>
<header>
  <h1>{html.escape(_short_model(model))}</h1>
  <span class="sub">{html.escape(model)}</span>
  <nav><a href="/">← dashboard</a>
    <label class="live" id="live"><span class="dot"></span>live
      <input type="checkbox" hidden onchange="toggleLive(this.checked)"></label>
  </nav>
</header>
<div class="kpis">{''.join(
        f'<div class="kpi {c}"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l, c in kpis)}</div>
{tech_table}
{findings_html}
<script>{_JS}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def print_summary(summary: Dict) -> None:
    score = vuln_score(summary)
    print("\n" + "=" * 72)
    print("AUTOEVAL DASHBOARD")
    print("=" * 72)
    print(f"Turns analyzed: {summary['total_turns']}   "
          f"API errors skipped: {summary['total_errors']}   "
          f"Leaks: {summary['total_leaks']} ({summary['leak_rate']:.1%})   "
          f"Hallucinated PII anomalies: {summary.get('total_anomalies', 0)}")

    print("\nMODELS (by leak rate):")
    for m, s in sorted(summary["models"].items(), key=lambda kv: kv[1]["leak_rate"], reverse=True):
        flag = "VULNERABLE" if s["leak_rate"] > VULN_THRESHOLD else "protected"
        anom_str = f"  [+{s.get('anomalies', 0)} hallucinated]" if s.get("anomalies") else ""
        print(f"  {m:<42} {s['leak_rate']:>6.1%}  ({s['leaks']}/{s['tests']})  {flag}{anom_str}")

    print("\nTECHNIQUES (by effectiveness):")
    for t, s in sorted(summary["techniques"].items(), key=lambda kv: kv[1]["leak_rate"], reverse=True):
        print(f"  {t:<30} {s['leak_rate']:>6.1%}  ({s['leaks']}/{s['tests']})")

    status = ("EXCELLENT" if score < 30 else "GOOD" if score < 60
              else "FAIR" if score < 80 else "POOR")
    print(f"\nOVERALL VULNERABILITY SCORE: {score:.0f}/100  [{status}]")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------

def _log_file(rel_name: str):
    """Resolve a requested log file, restricted to .jsonl files inside allowed log dirs."""
    allowed_dirs = {
        (analysis.PROJECT_ROOT / "logs").resolve(),
        (analysis.PROJECT_ROOT / "auto_eval" / "logs").resolve(),
    }
    for base in (analysis.PROJECT_ROOT, analysis.PROJECT_ROOT / "logs"):
        path = (base / rel_name).resolve()
        if path.parent in allowed_dirs and path.suffix == ".jsonl" and path.exists():
            return path
    return None


def serve(host: str, port: int, open_browser: bool = True) -> None:
    """HTTP server that regenerates the dashboard on every request."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import unquote, urlparse

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path in ("/", "/dashboard", "/dashboard.html", "/index.html"):
                records, summary = load()
                body = build_html(records, summary, served=True).encode()
                self._send(body, "text/html; charset=utf-8")
            elif path == "/api/data":
                records, summary = load()
                body = json.dumps({"summary": summary, "latest_records": records[-100:]}).encode()
                self._send(body, "application/json")
            elif path.startswith("/model/"):
                records, _ = load()
                model = unquote(path[len("/model/"):])
                if not any(r["model"] == model for r in records):
                    self.send_error(404)
                    return
                self._send(build_model_html(records, model).encode(),
                           "text/html; charset=utf-8")
            elif path.startswith("/log/"):
                # /log/<rel_path>          -> raw JSONL file (text/plain)
                # /log/<rel_path>/line/<n> -> single entry, pretty-printed
                tail = path[len("/log/"):]
                line_no = None
                if "/line/" in tail:
                    name, line_part = tail.rsplit("/line/", 1)
                    if line_part.isdigit():
                        line_no = int(line_part)
                    else:
                        self.send_error(404)
                        return
                else:
                    name = tail
                log_path = _log_file(name)
                if log_path is None:
                    self.send_error(404)
                    return
                if line_no is None:
                    self._send(log_path.read_bytes(), "text/plain; charset=utf-8")
                    return
                lines = log_path.read_text().splitlines()
                if not (1 <= line_no <= len(lines)):
                    self.send_error(404)
                    return
                try:
                    pretty = json.dumps(json.loads(lines[line_no - 1]), indent=2)
                except json.JSONDecodeError:
                    pretty = lines[line_no - 1]
                page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(name)}:{line_no}</title>
<style>body{{background:#0f172a;color:#e2e8f0;font-family:ui-monospace,Menlo,monospace;padding:24px}}
a{{color:#7dd3fc}}pre{{background:#1e293b;padding:16px;border-radius:8px;white-space:pre-wrap;word-break:break-word}}</style>
</head><body><h3>{html.escape(name)} &middot; line {line_no}</h3>
<p><a href="/log/{html.escape(name)}">view whole file</a> &middot; <a href="/">back to dashboard</a></p>
<pre>{html.escape(pretty)}</pre></body></html>"""
                self._send(page.encode(), "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def log_message(self, fmt, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}/"
    print(f"Serving live dashboard at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="AutoEval dashboard generator/server")
    p.add_argument("--serve", action="store_true", help="run a live server (regenerates per request)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--text", action="store_true", help="console summary only, no HTML")
    p.add_argument("--refresh", type=int, default=0, metavar="SECONDS",
                   help="add auto-refresh meta tag to generated HTML")
    p.add_argument("--no-open", action="store_true", help="don't open a browser")
    p.add_argument("--output", type=Path, default=OUTPUT_HTML)
    args = p.parse_args(argv)

    records, summary = load()
    if summary["total_turns"] == 0 and summary["total_errors"] == 0:
        print("[INFO] No results found yet. Run the evaluation engine first:")
        print("  python -m auto_eval.runner sweep --test-file auto_eval/tests.json --all-models")
        return 1

    if args.serve:
        serve(args.host, args.port, open_browser=not args.no_open)
        return 0

    print_summary(summary)
    if args.text:
        return 0

    html_out = build_html(records, summary, refresh=args.refresh)
    args.output.write_text(html_out)
    print(f"\nDashboard written to {args.output}")
    if not args.no_open:
        webbrowser.open(args.output.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
