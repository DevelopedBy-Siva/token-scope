import json
import os
import webbrowser
import tempfile
from datetime import datetime


def generate_report(session, open_browser: bool = True) -> str:
    calls_data = []
    for call in session.calls:
        top = call.parsed.top_contributors
        leaks_data = [
            {
                "rule_id": l.rule_id.value,
                "severity": l.severity.value,
                "path": l.path,
                "description": l.description,
                "estimated_savings": l.estimated_savings,
            }
            for l in call.leaks
        ]
        fields_data = [
            {
                "path": f.path,
                "attributed_tokens": f.attributed_tokens,
                "pct_of_total": f.pct_of_total,
                "depth": f.depth,
                "field_type": f.field_type.value,
                "is_leaf": f.is_leaf,
            }
            for f in sorted(call.parsed.fields, key=lambda x: x.attributed_tokens, reverse=True)[:20]
        ]
        calls_data.append({
            "index": call.index,
            "model": call.model,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "total_tokens": call.input_tokens + call.output_tokens,
            "input_cost_usd": call.input_cost_usd,
            "output_cost_usd": call.output_cost_usd,
            "total_cost_usd": call.total_cost_usd,
            "tokens_saved": call.optimization.tokens_saved,
            "pct_saved": call.optimization.pct_saved,
            "duration_ms": round(call.duration_ms, 1),
            "leaks": leaks_data,
            "fields": fields_data,
            "leak_count": len(call.leaks),
        })

    summary = {
        "total_calls": len(session.calls),
        "total_input_tokens": session.total_input_tokens,
        "total_output_tokens": session.total_output_tokens,
        "total_cost_usd": round(session.total_cost_usd, 6),
        "total_tokens_saved": session.total_tokens_saved,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    html = _build_html(summary, calls_data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tokenscope_report_{timestamp}.html"
    output_path = os.path.join(os.getcwd(), filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n📊 TokenScope Report → {output_path}")
    print(f"   {summary['total_calls']} calls · {summary['total_input_tokens']:,} input tokens · ${summary['total_cost_usd']:.4f} total cost")
    if summary["total_tokens_saved"] > 0:
        print(f"   💡 {summary['total_tokens_saved']:,} tokens could be saved with optimization")

    if open_browser:
        webbrowser.open(f"file://{output_path}")

    return output_path


def _severity_color(severity: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#6b7280"}.get(severity, "#6b7280")


def _build_html(summary: dict, calls: list) -> str:
    calls_json = json.dumps(calls)
    summary_json = json.dumps(summary)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TokenScope Report — {summary['generated_at']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; }}
  .header {{ background: #0f172a; color: white; padding: 24px 32px; display: flex; align-items: center; gap: 12px; }}
  .header h1 {{ font-size: 20px; font-weight: 700; }}
  .header .sub {{ font-size: 13px; color: #94a3b8; margin-top: 2px; }}
  .logo {{ font-size: 24px; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; padding: 24px 32px; background: white; border-bottom: 1px solid #e2e8f0; }}
  .metric {{ }}
  .metric-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
  .metric-value {{ font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 4px; }}
  .metric-value.green {{ color: #16a34a; }}
  .metric-value.orange {{ color: #d97706; }}
  .calls {{ padding: 24px 32px; }}
  .calls h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #0f172a; }}
  .call-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }}
  .call-header {{ padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none; }}
  .call-header:hover {{ background: #f8fafc; }}
  .call-title {{ display: flex; align-items: center; gap: 12px; }}
  .call-num {{ width: 28px; height: 28px; background: #0f172a; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; }}
  .call-model {{ font-size: 13px; font-weight: 600; }}
  .call-meta {{ font-size: 12px; color: #64748b; margin-top: 2px; }}
  .call-stats {{ display: flex; gap: 20px; align-items: center; }}
  .stat {{ text-align: right; }}
  .stat-val {{ font-size: 14px; font-weight: 600; }}
  .stat-lbl {{ font-size: 11px; color: #64748b; }}
  .saved {{ color: #16a34a; }}
  .call-body {{ border-top: 1px solid #e2e8f0; padding: 20px; display: none; }}
  .call-body.open {{ display: block; }}
  .section-title {{ font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 10px; }}
  .fields-table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px; }}
  .fields-table th {{ text-align: left; padding: 6px 10px; background: #f1f5f9; font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; }}
  .fields-table td {{ padding: 6px 10px; border-bottom: 1px solid #f1f5f9; }}
  .bar-wrap {{ background: #f1f5f9; border-radius: 3px; height: 6px; width: 100px; display: inline-block; vertical-align: middle; margin-left: 8px; }}
  .bar {{ background: #3b82f6; border-radius: 3px; height: 6px; }}
  .bar.red {{ background: #ef4444; }}
  .bar.yellow {{ background: #f59e0b; }}
  .leaks-list {{ margin-bottom: 20px; }}
  .leak-item {{ display: flex; gap: 10px; align-items: flex-start; padding: 10px; background: #fafafa; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 8px; }}
  .severity-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }}
  .leak-desc {{ font-size: 13px; color: #374151; line-height: 1.5; }}
  .leak-savings {{ font-size: 12px; color: #16a34a; font-weight: 600; margin-top: 2px; }}
  .no-leaks {{ font-size: 13px; color: #16a34a; padding: 10px; }}
  .chevron {{ font-size: 12px; color: #94a3b8; transition: transform 0.2s; }}
  .chevron.open {{ transform: rotate(180deg); }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 700px) {{ .two-col {{ grid-template-columns: 1fr; }} .call-stats {{ display: none; }} }}
</style>
</head>
<body>
<div class="header">
  <div class="logo">🔬</div>
  <div>
    <h1>TokenScope Report</h1>
    <div class="sub">Generated {summary['generated_at']}</div>
  </div>
</div>

<div class="summary">
  <div class="metric">
    <div class="metric-label">Total Calls</div>
    <div class="metric-value">{summary['total_calls']}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Input Tokens</div>
    <div class="metric-value">{summary['total_input_tokens']:,}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Output Tokens</div>
    <div class="metric-value">{summary['total_output_tokens']:,}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Total Cost</div>
    <div class="metric-value orange">${summary['total_cost_usd']:.4f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Tokens Saveable</div>
    <div class="metric-value green">{summary['total_tokens_saved']:,}</div>
  </div>
</div>

<div class="calls">
  <h2>API Calls ({summary['total_calls']})</h2>
  <div id="calls-container"></div>
</div>

<script>
const calls = {calls_json};

function barColor(pct) {{
  if (pct >= 20) return 'red';
  if (pct >= 10) return 'yellow';
  return '';
}}

function severityColor(s) {{
  if (s === 'high') return '#ef4444';
  if (s === 'medium') return '#f59e0b';
  return '#6b7280';
}}

function renderCalls() {{
  const container = document.getElementById('calls-container');
  calls.forEach((call, i) => {{
    const card = document.createElement('div');
    card.className = 'call-card';

    const leaksHtml = call.leaks.length === 0
      ? '<div class="no-leaks">✅ No cost leaks detected</div>'
      : call.leaks.map(l => `
          <div class="leak-item">
            <div class="severity-dot" style="background:${{severityColor(l.severity)}}"></div>
            <div>
              <div class="leak-desc">${{l.description}}</div>
              <div class="leak-savings">~${{l.estimated_savings}} tokens saveable</div>
            </div>
          </div>`).join('');

    const fieldsHtml = call.fields.slice(0, 8).map(f => {{
      const color = barColor(f.pct_of_total);
      return `<tr>
        <td><code style="font-size:12px">${{f.path}}</code></td>
        <td>${{f.field_type}}</td>
        <td>${{f.attributed_tokens}}
          <span class="bar-wrap"><span class="bar ${{color}}" style="width:${{Math.min(f.pct_of_total, 100)}}%"></span></span>
        </td>
        <td>${{f.pct_of_total.toFixed(1)}}%</td>
      </tr>`;
    }}).join('');

    card.innerHTML = `
      <div class="call-header" onclick="toggle(${{i}})">
        <div class="call-title">
          <div class="call-num">${{call.index}}</div>
          <div>
            <div class="call-model">${{call.model}}</div>
            <div class="call-meta">${{call.input_tokens.toLocaleString()}} input · ${{call.output_tokens.toLocaleString()}} output · ${{call.duration_ms}}ms</div>
          </div>
        </div>
        <div class="call-stats">
          <div class="stat">
            <div class="stat-val">$${{call.total_cost_usd.toFixed(5)}}</div>
            <div class="stat-lbl">cost</div>
          </div>
          <div class="stat">
            <div class="stat-val">${{call.leak_count}}</div>
            <div class="stat-lbl">leaks</div>
          </div>
          ${{call.tokens_saved > 0 ? `<div class="stat"><div class="stat-val saved">-${{call.tokens_saved}}</div><div class="stat-lbl">saveable</div></div>` : ''}}
          <div class="chevron" id="chevron-${{i}}">▼</div>
        </div>
      </div>
      <div class="call-body" id="body-${{i}}">
        <div class="two-col">
          <div>
            <div class="section-title">Top Cost Fields</div>
            <table class="fields-table">
              <thead><tr><th>Path</th><th>Type</th><th>Tokens</th><th>%</th></tr></thead>
              <tbody>${{fieldsHtml}}</tbody>
            </table>
          </div>
          <div>
            <div class="section-title">Cost Leaks (${{call.leaks.length}})</div>
            <div class="leaks-list">${{leaksHtml}}</div>
          </div>
        </div>
      </div>`;

    container.appendChild(card);
  }});
}}

function toggle(i) {{
  const body = document.getElementById('body-' + i);
  const chevron = document.getElementById('chevron-' + i);
  body.classList.toggle('open');
  chevron.classList.toggle('open');
}}

renderCalls();
</script>
</body>
</html>"""