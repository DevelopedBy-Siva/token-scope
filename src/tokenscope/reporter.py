import json
import os
from datetime import datetime


def generate_report(session) -> str:
    calls_data = _serialize_calls(session)
    summary    = _serialize_summary(session)
    html       = _build_html(summary, calls_data)

    reports_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(reports_dir, f"tokenscope_{timestamp}.html")

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path


def _get_display_name(call) -> str:
    """Extract display name from a CapturedCall to check if pricing is estimated."""
    from tokenscope.core.calculator import Calculator, resolve_model_id
    calc = Calculator()
    model_id = resolve_model_id(call.model)
    cost = calc.request_cost(1, model_id)
    return cost.display_name


def _serialize_calls(session) -> list[dict]:
    out = []
    for call in session.calls:
        top_fields = sorted(
            [f for f in call.parsed.fields if f.is_leaf],
            key=lambda f: f.attributed_tokens,
            reverse=True,
        )[:20]

        out.append({
            "index":             call.index,
            "model":             call.model,
            "input_tokens":      call.input_tokens,
            "output_tokens":     call.output_tokens,
            "analyzed_tokens":   call.analyzed_tokens,
            "input_cost_usd":    call.input_cost_usd,
            "output_cost_usd":   call.output_cost_usd,
            "total_cost_usd":    call.total_cost_usd,
            "tokens_saveable":   call.optimization.tokens_saved,
            "pct_saveable":      call.optimization.pct_saved,
            "duration_ms":       round(call.duration_ms, 1),
            "is_estimated_cost": "≈" in _get_display_name(call),
            "fields": [
                {
                    "path":              f.path,
                    "attributed_tokens": f.attributed_tokens,
                    "pct_of_total":      f.pct_of_total,
                    "field_type":        f.field_type.value,
                }
                for f in top_fields
            ],
            "leaks": [
                {
                    "rule_id":           l.rule_id.value,
                    "severity":          l.severity.value,
                    "path":              l.path,
                    "description":       l.description,
                    "estimated_savings": l.estimated_savings,
                }
                for l in call.leaks
            ],
        })
    return out


def _serialize_summary(session) -> dict:
    return {
        "total_calls":           len(session.calls),
        "total_input_tokens":    session.total_input_tokens,
        "total_output_tokens":   session.total_output_tokens,
        "total_analyzed_tokens": session.total_analyzed_tokens,
        "total_cost_usd":        round(session.total_cost_usd, 6),
        "total_tokens_saveable": session.total_tokens_saveable,
        "generated_at":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _build_html(summary: dict, calls: list) -> str:
    calls_json = json.dumps(calls, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TokenScope — {summary['generated_at']}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600;700&family=Google+Sans+Mono&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:        #000000;
    --surface:   #111111;
    --surface2:  #1a1a1a;
    --border:    #2a2a2a;
    --border2:   #333333;
    --text:      #ffffff;
    --text2:     #cccccc;
    --muted:     #888888;
    --faint:     #2a2a2a;
    --green:     #34d399;
    --green-dim: #052e1c;
    --amber:     #fbbf24;
    --amber-dim: #2d1f00;
    --red:       #f87171;
    --red-dim:   #2d0a0a;
    --blue:      #60a5fa;
    --blue-dim:  #0f2340;
    --purple:    #a78bfa;
    --mono:      'Google Sans Mono', 'SF Mono', 'Fira Code', monospace;
  }}

  body {{
    font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.5;
    overscroll-behavior: none;
  }}

  .summary {{
    display: flex;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }}
  .metric {{
    padding: 14px 24px;
    border-right: 1px solid var(--border);
    flex-shrink: 0;
  }}
  .metric:last-child {{ border-right: none; }}
  .metric-label {{ font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }}
  .metric-value {{ font-size: 20px; font-weight: 700; color: var(--text); margin-top: 3px; letter-spacing: -0.5px; }}
  .metric-value.green {{ color: var(--green); }}
  .metric-value.amber {{ color: var(--amber); }}

  .main {{ padding: 20px 28px; }}

  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 8px; overflow: hidden; transition: border-color 0.15s; }}
  .card:hover {{ border-color: var(--border2); }}

  .card-header {{ display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; cursor: pointer; user-select: none; gap: 12px; }}
  .card-header:hover {{ background: var(--surface2); }}

  .call-left {{ display: flex; align-items: center; gap: 10px; }}
  .call-num {{ width: 22px; height: 22px; border-radius: 50%; background: #3a3a3a; color: #aaaaaa; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
  .call-model {{ font-size: 13px; font-weight: 600; color: var(--text); }}
  .call-sub {{ font-size: 10px; color: var(--muted); margin-top: 1px; }}

  .call-right {{ display: flex; align-items: center; gap: 16px; flex-shrink: 0; }}

  .pill {{ font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 20px; }}
  .pill.red   {{ background: var(--red-dim);   color: var(--red);   border: 1px solid #4a1515; }}
  .pill.amber {{ background: var(--amber-dim); color: var(--amber); border: 1px solid #4a3200; }}
  .pill.green {{ background: var(--green-dim); color: var(--green); border: 1px solid #0a4a30; }}
  .pill.gray  {{ background: var(--surface2);  color: var(--muted); border: 1px solid var(--border); }}

  .stat {{ text-align: right; }}
  .stat-val {{ font-size: 12px; font-weight: 600; color: var(--text); }}
  .stat-lbl {{ font-size: 10px; color: var(--muted); margin-top: 1px; }}
  .stat-val.green {{ color: var(--green); }}
  .stat-val.amber {{ color: var(--amber); }}

  .chevron {{ color: var(--faint); font-size: 10px; transition: transform 0.15s; }}
  .chevron.open {{ transform: rotate(180deg); }}

  .card-body {{ display: none; border-top: 1px solid var(--border); }}
  .card-body.open {{ display: block; }}
  .card-body-inner {{ display: grid; grid-template-columns: 1fr 1fr; }}
  .panel {{ padding: 14px 16px; }}
  .panel + .panel {{ border-left: 1px solid var(--border); }}
  .panel-title {{ font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); margin-bottom: 10px; }}

  .ftable {{ width: 100%; border-collapse: collapse; }}
  .ftable tr + tr td {{ border-top: 1px solid var(--faint); }}
  .ftable td {{ padding: 5px 0; font-size: 11px; vertical-align: middle; }}
  .ftable td:first-child {{ font-family: var(--mono); font-size: 10px; color: var(--text2); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 10px; }}
  .ftable td:last-child {{ text-align: right; color: var(--muted); font-size: 10px; white-space: nowrap; }}

  .leak {{ display: flex; gap: 8px; padding: 8px 10px; background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 5px; }}
  .leak:last-child {{ margin-bottom: 0; }}
  .leak-dot {{ width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }}
  .leak-content {{ flex: 1; min-width: 0; }}
  .leak-rule {{ font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 2px; }}
  .leak-text {{ font-size: 11px; color: var(--text2); line-height: 1.5; }}
  .leak-savings {{ font-size: 10px; color: var(--green); font-weight: 600; margin-top: 3px; }}
  .no-leaks {{ font-size: 11px; color: var(--green); padding: 4px 0; }}

  .note {{ font-size: 10px; color: var(--muted); margin-top: 8px; }}
  .note.amber {{ color: var(--amber); }}

  @media (max-width: 700px) {{
    .card-body-inner {{ grid-template-columns: 1fr; }}
    .panel + .panel  {{ border-left: none; border-top: 1px solid var(--border); }}
    .call-right      {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="summary">
  <div class="metric">
    <div class="metric-label">Calls</div>
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
    <div class="metric-label">Analyzed</div>
    <div class="metric-value">{summary['total_analyzed_tokens']:,}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Total Cost</div>
    <div class="metric-value amber">${summary['total_cost_usd']:.4f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Saveable</div>
    <div class="metric-value green">{summary['total_tokens_saveable']:,} tokens</div>
  </div>
</div>

<div class="main">
  <div id="root"></div>
</div>

<script type="application/json" id="calls-data">
{calls_json}
</script>

<script>
const calls = JSON.parse(document.getElementById('calls-data').textContent);

const SEV_COLOR = {{ high: '#f87171', medium: '#fbbf24', low: '#475569' }};
const RULE_LABEL = {{
  VERBOSE_SCHEMA:    'Verbose Schema',
  BLOATED_ARRAY:     'Bloated Array',
  DUPLICATE_CONTENT: 'Duplicate Content',
  REPEATED_KEYS:     'Repeated Keys',
  LOW_SIGNAL_FIELDS: 'Low Signal',
  DEEP_NESTING:      'Deep Nesting',
}};

function pill(leaks) {{
  if (!leaks.length) return '<span class="pill green">clean</span>';
  const h = leaks.filter(l => l.severity === 'high').length;
  if (h) return `<span class="pill red">${{h}} high</span>`;
  return `<span class="pill amber">${{leaks.length}} leak${{leaks.length > 1 ? 's' : ''}}</span>`;
}}

function fmt(n) {{ return n.toLocaleString(); }}

calls.forEach((c, i) => {{
  const card = document.createElement('div');
  card.className = 'card';

  const sortedFields = [...c.fields].sort((a, b) => {{
    const idxA = parseInt((a.path.match(/\\[(\\d+)\\]/) || [0, 0])[1]);
    const idxB = parseInt((b.path.match(/\\[(\\d+)\\]/) || [0, 0])[1]);
    if (idxA !== idxB) return idxA - idxB;
    return b.attributed_tokens - a.attributed_tokens;
  }});

  const fieldsRows = sortedFields.slice(0, 10).map(f => {{
    const cleanPath = f.path.replace(/\\[\\*\\]/g, '[0]');
    return `
    <tr>
      <td title="${{cleanPath}}">${{cleanPath}}</td>
      <td>${{f.attributed_tokens}} · ${{f.pct_of_total.toFixed(1)}}%</td>
    </tr>`;
  }}).join('');

  const leaksHtml = c.leaks.length === 0
    ? '<div class="no-leaks">✓ No leaks detected</div>'
    : c.leaks.map(l => `
        <div class="leak">
          <div class="leak-dot" style="background:${{SEV_COLOR[l.severity]}}"></div>
          <div class="leak-content">
            <div class="leak-rule">${{RULE_LABEL[l.rule_id] || l.rule_id}}</div>
            <div class="leak-text">${{l.description}}</div>
            <div class="leak-savings">~${{l.estimated_savings}} tokens saveable</div>
          </div>
        </div>`).join('');

  const costNote = c.is_estimated_cost
    ? '<div class="note amber">≈ gpt-4o reference pricing (local model)</div>' : '';

  card.innerHTML = `
    <div class="card-header" onclick="toggle(${{i}})">
      <div class="call-left">
        <div class="call-num">${{c.index}}</div>
        <div>
          <div class="call-model">${{c.model}}</div>
          <div class="call-sub">${{fmt(c.input_tokens)}} in · ${{fmt(c.output_tokens)}} out · ${{fmt(c.analyzed_tokens)}} analyzed · ${{c.duration_ms}}ms</div>
        </div>
      </div>
      <div class="call-right">
        ${{pill(c.leaks)}}
        <div class="stat">
          <div class="stat-val${{c.is_estimated_cost ? ' amber' : ''}}">$${{c.total_cost_usd < 0.001 ? c.total_cost_usd.toFixed(6) : c.total_cost_usd.toFixed(4)}}</div>
          <div class="stat-lbl">cost${{c.is_estimated_cost ? ' ≈' : ''}}</div>
        </div>
        ${{c.tokens_saveable > 0 ? `<div class="stat"><div class="stat-val green">-${{c.tokens_saveable}}</div><div class="stat-lbl">saveable</div></div>` : ''}}
        <div class="chevron" id="chev-${{i}}">▼</div>
      </div>
    </div>
    <div class="card-body" id="body-${{i}}">
      <div class="card-body-inner">
        <div class="panel">
          <div class="panel-title">Top fields by token cost</div>
          <table class="ftable"><tbody>${{fieldsRows}}</tbody></table>
          <div class="note">Attribution is proportionally estimated · total is exact</div>
          ${{costNote}}
        </div>
        <div class="panel">
          <div class="panel-title">Cost leaks (${{c.leaks.length}})</div>
          ${{leaksHtml}}
        </div>
      </div>
    </div>`;

  document.getElementById('root').appendChild(card);
}});

function toggle(i) {{
  document.getElementById('body-' + i).classList.toggle('open');
  document.getElementById('chev-' + i).classList.toggle('open');
}}
</script>
</body>
</html>"""