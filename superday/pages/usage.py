"""Usage & Safety: real token counts and cost from every model call, agent traces and guard events."""

from __future__ import annotations

import json

from dash import Input, Output, State, callback, dcc, html

from .. import config, db
from ..ui import alert, badge, card, kpi, page


def layout(search: str = ""):
    """search may be '?run=<run_id>' to open a specific trace."""
    from urllib.parse import parse_qs
    wanted = parse_qs(search.lstrip("?")).get("run", [None])[0]
    tot = db.query("SELECT COUNT(*) calls, COUNT(DISTINCT run_id) runs, COALESCE(SUM(input_tokens),0) inp, "
                   "COALESCE(SUM(cached_tokens),0) cached, COALESCE(SUM(output_tokens),0) outp, "
                   "COALESCE(SUM(cost_usd),0) cost FROM llm_calls WHERE status NOT LIKE 'error%'")[0]
    by_agent = db.query(
        "SELECT agent, COUNT(*) calls, COUNT(DISTINCT run_id) runs, SUM(input_tokens) inp, SUM(cached_tokens) cached, "
        "SUM(output_tokens) outp, SUM(cost_usd) cost, AVG(latency_ms) lat FROM llm_calls WHERE status NOT LIKE 'error%' "
        "GROUP BY agent ORDER BY cost DESC")
    runs = db.query("SELECT run_id, MIN(ts) ts FROM trace_events GROUP BY run_id ORDER BY ts DESC LIMIT 60")
    guards = db.query("SELECT ts, run_id, agent, name, content FROM trace_events WHERE kind = 'guard' ORDER BY ts DESC LIMIT 15")
    cache_rate = tot["cached"] / tot["inp"] if tot["inp"] else 0

    agent_table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ("Agent", "Runs", "Model calls", "Input tok", "Cached tok", "Output tok",
                                                  "Avg latency", "Cost (USD)", "Cost / run")])),
        html.Tbody([html.Tr([html.Td(a["agent"]), html.Td(a["runs"]), html.Td(a["calls"]), html.Td(f"{a['inp']:,}"),
                             html.Td(f"{a['cached']:,}"), html.Td(f"{a['outp']:,}"), html.Td(f"{a['lat'] / 1000:.1f}s"),
                             html.Td(f"${a['cost']:.4f}"), html.Td(f"${a['cost'] / a['runs']:.5f}")]) for a in by_agent]),
    ], className="simple-table") if by_agent else html.Div("No model calls yet.", className="empty")

    guard_list = [html.Div([html.B(g["name"].replace("_", " ")), f" · {g['agent']} · {g['ts'][:16].replace('T', ' ')} · ",
                            html.Span(g["run_id"], className="mono"),
                            html.Pre(g["content"][:400])], className="trace-step guard") for g in guards]

    return page(
        "Usage & Safety",
        "Real token counts from every gpt-6-luna call, step-by-step agent traces and every time a safety guard fired.",
        html.Div([
            kpi("Agent runs", f"{tot['runs']:,}", f"{tot['calls']:,} model calls"),
            kpi("Tokens", f"{(tot['inp'] + tot['outp']):,}", f"{tot['inp']:,} in · {tot['outp']:,} out"),
            kpi("Prompt cache hit", f"{cache_rate:.0%}", f"{tot['cached']:,} cached input tokens"),
            kpi("Total spend", f"${tot['cost']:.4f}", f"today ${db.spend_today():.4f} of ${config.DAILY_SPEND_CAP_USD:.2f} cap"),
        ], className="grid grid-4", style={"marginBottom": "18px"}),
        card("Cost by agent", agent_table,
             html.Div(f"Prices: ${config.PRICE_PER_M['input']}/1M input, ${config.PRICE_PER_M['cached_input']}/1M cached input, "
                      f"${config.PRICE_PER_M['cache_write']}/1M cache write, ${config.PRICE_PER_M['output']}/1M output "
                      f"({config.MODEL}).", className="hint", style={"marginTop": "8px"})),
        html.Div([
            card("Agent trace viewer",
                 dcc.Dropdown([{"label": f"{r['ts'][:16].replace('T', ' ')} · {r['run_id']}", "value": r["run_id"]} for r in runs],
                              wanted or (runs[0]["run_id"] if runs else None), id="trace-run"),
                 html.Div(id="trace-out", style={"marginTop": "10px", "maxHeight": "640px", "overflowY": "auto"})),
            card("Safety guard log", html.Div(guard_list or [html.Div("No guard events yet.", className="empty")],
                                              style={"maxHeight": "700px", "overflowY": "auto"}),
                 html.Div("Guards: injection scanner, PII masking, fact-checker, unknown-contact check, question-id "
                          "validation, step limit, token budget and daily spend cap.", className="hint")),
        ], className="grid grid-2"),
        card("Data",
             html.Div("Reset to the fictional sample candidate or start with a blank profile. The usage log is kept.",
                      className="hint"),
             html.Div([html.Button("Reset sample data", id="data-reset", className="btn btn-secondary"),
                       html.Button("Start blank", id="data-blank", className="btn btn-danger"),
                       html.Span(id="data-msg")], className="btn-row"),
             dcc.ConfirmDialog(id="data-confirm", message="This replaces all trackers and practice history. Continue?"),
             dcc.Store(id="data-action")),
    )


@callback(Output("trace-out", "children"), Input("trace-run", "value"))
def show_trace(run_id):
    if not run_id:
        return html.Div("No runs yet.", className="empty")
    events = db.query("SELECT * FROM trace_events WHERE run_id = ? ORDER BY id", (run_id,))
    calls = db.query("SELECT agent, step, input_tokens, cached_tokens, output_tokens, latency_ms, cost_usd "
                     "FROM llm_calls WHERE run_id = ? ORDER BY id", (run_id,))
    steps = []
    for i, e in enumerate(events, 1):
        content = e["content"]
        try:
            content = json.dumps(json.loads(content), indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
        steps.append(html.Div([html.B(f"{i}. {e['agent']} · {e['kind'].replace('_', ' ')} · {e['name']}"),
                               html.Pre(content[:3000])], className="trace-step" + (" guard" if e["kind"] == "guard" else "")))
    total = sum(c["cost_usd"] for c in calls)
    call_rows = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ("Agent", "Turn", "Input", "Cached", "Output", "Latency", "Cost")])),
        html.Tbody([html.Tr([html.Td(c["agent"]), html.Td(c["step"]), html.Td(c["input_tokens"]), html.Td(c["cached_tokens"]),
                             html.Td(c["output_tokens"]), html.Td(f"{c['latency_ms'] / 1000:.1f}s"),
                             html.Td(f"${c['cost_usd']:.5f}")]) for c in calls])], className="simple-table")
    return html.Div([html.Div([badge(f"{len(calls)} model calls"), " ", badge(f"${total:.5f}", "ok")]),
                     html.Div(call_rows, style={"margin": "10px 0"}), *steps])


@callback(Output("data-confirm", "displayed"), Output("data-action", "data"),
          Input("data-reset", "n_clicks"), Input("data-blank", "n_clicks"), prevent_initial_call=True)
def confirm(*_):
    from dash import ctx
    return True, ctx.triggered_id


@callback(Output("data-msg", "children"), Input("data-confirm", "submit_n_clicks"), State("data-action", "data"),
          prevent_initial_call=True)
def do_reset(_, action):
    if action == "data-blank":
        db.clear_all()
        return alert("Blank profile ready. Add your applications and coffee chats.", "ok")
    db.init(reset=True)
    return alert("Sample data restored. Reload any page to see it.", "ok")
