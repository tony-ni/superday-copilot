"""Deal prep: paste a press release, the Deal Analyst extracts facts with quotes, a code fact-checker verifies them."""

from __future__ import annotations

import json

from dash import Input, Output, State, callback, dcc, html

from .. import agents, config, db, llm
from ..ui import alert, badge, bullets, card, empty_state, error_box, icon, loading, page, page_icon

SAMPLES = json.loads((config.DATA_DIR / "sample_deals.json").read_text(encoding="utf-8"))


def layout():
    return page(
        "Deal Prep",
        "Prepare 'Tell me about a deal you've followed'. Every fact must quote the source, and a code fact-checker "
        "verifies each quote and number.",
        page_icon("deal"),
        html.Div([
            card("Source",
                 html.Label("Load a sample (fictional) or paste a real press release / article", className="field"),
                 dcc.Dropdown([{"label": s["title"], "value": i} for i, s in enumerate(SAMPLES)], id="deal-sample",
                              placeholder="Load a sample..."),
                 dcc.Textarea(id="deal-text", style={"height": "330px", "marginTop": "10px"},
                              placeholder="Paste the full press release text here..."),
                 html.Div([html.Button([icon("spark"), " Analyze deal"], id="deal-btn", className="btn")], className="btn-row"),
                 html.Div("Only the text you paste is used. The analyst may not add facts from memory.", className="hint",
                          style={"marginTop": "8px"})),
            html.Div([loading(html.Div(id="deal-out", children=card("Result", empty_state(
                "deal", "Your deal brief will appear here",
                "Verified facts, rationale, risks, 60-second talking points and likely interviewer questions."))),
                "The Deal Analyst is reading the source; the fact-checker then verifies every quote…")]),
        ], className="grid grid-5-7"),
        card("Past analyses", _history()),
    )


def _history():
    rows = db.query("SELECT ts, title, result_json FROM deals ORDER BY ts DESC LIMIT 8")
    if not rows:
        return html.Div("No deals analyzed yet.", className="empty")
    body = []
    for r in rows:
        res = json.loads(r["result_json"])
        st = res.get("check_stats", {})
        body.append(html.Tr([html.Td(r["ts"][:16].replace("T", " ")), html.Td(r["title"]),
                             html.Td(f"{st.get('verified', 0)}/{st.get('checked', 0)} verified"),
                             html.Td(badge("injection blocked", "bad") if res.get("guard_flags") or res.get("injection_found") else "-")]))
    return html.Table([html.Thead(html.Tr([html.Th(h) for h in ("When", "Deal", "Fact check", "Safety")])), html.Tbody(body)],
                      className="simple-table")


@callback(Output("deal-text", "value"), Input("deal-sample", "value"), prevent_initial_call=True)
def load_sample(i):
    return SAMPLES[i]["text"] if i is not None else ""


@callback(Output("deal-out", "children"), Input("deal-btn", "n_clicks"), State("deal-text", "value"),
          prevent_initial_call=True, running=[(Output("deal-btn", "disabled"), True, False)])
def analyze(_, text):
    run_id = llm.new_run_id("deal")
    try:
        res = agents.analyze_deal(text or "", run_id)
    except llm.AIError as exc:
        return error_box(exc)
    db.execute("INSERT INTO deals (ts, title, source, result_json, run_id) VALUES (?,?,?,?,?)",
               (db.now(), res["deal_title"], text, json.dumps(res), run_id))
    return render(res)


def _claim_row(label, value, item):
    ok = item["verified"]
    return html.Tr([
        html.Td(html.B(label)) if label is not None else None,
        html.Td([value, html.Div(f"“{item['quote']}”", className="hint", style={"fontStyle": "italic"})]),
        html.Td([badge("✓ verified" if ok else "⚠ unverified", "ok" if ok else "bad"),
                 html.Div(item["check"], className="hint") if not ok else None]),
    ], style={"opacity": 1 if ok else .85})


def render(res: dict):
    st = res["check_stats"]
    parts = []
    if res.get("guard_flags") or res.get("injection_found"):
        parts.append(alert("Safety guard: the source contains instructions aimed at AI systems "
                           f"({'; '.join(res.get('guard_flags') or ['flagged by the analyst'])}). They were "
                           "quarantined: removed before the AI saw the text, so nothing from them can become a fact.", "danger"))
        for r in res.get("removed_text", []):
            parts.append(html.Div([html.B("Removed: "), html.Span(r, className="mono")], className="trace-step guard"))
    parts.append(alert(f"Fact-checker: {st['verified']} of {st['checked']} claims verified against the source. "
                       "Unverified claims should not be repeated in an interview.",
                       "ok" if st["verified"] == st["checked"] else "warning"))
    parts.append(card("Deal facts", html.Table([
        html.Thead(html.Tr([html.Th("Item"), html.Th("Fact and source quote"), html.Th("Check")])),
        html.Tbody([_claim_row(f["label"], f["value"], f) for f in res["facts"]])], className="simple-table")))
    parts.append(html.Div([
        card("Strategic rationale", html.Table(html.Tbody([_claim_row(None, r["claim"], r) for r in res["rationale"]]),
                                               className="simple-table") if res["rationale"] else html.Div("None stated.", className="empty")),
        card("Risks", html.Table(html.Tbody([_claim_row(None, r["claim"], r) for r in res["risks"]]), className="simple-table")
             if res["risks"] else html.Div("No risks stated in the source.", className="empty")),
    ], className="grid grid-2"))
    tps = [html.Li([tp["text"], " ", badge(f"number not in source: {', '.join(tp['unsupported_numbers'])}", "bad")
                    if tp["unsupported_numbers"] else None]) for tp in res["talking_points"]]
    parts.append(card("Your 60-second talking points", html.Ul(tps)))
    qa = [html.Details([html.Summary(q["question"]),
                        html.P([q["answer"], " ", badge(f"check: {', '.join(q['unsupported_numbers'])} not in source", "warn")
                                if q["unsupported_numbers"] else None])], style={"marginBottom": "8px"})
          for q in res["likely_questions"]]
    parts.append(card("Questions an interviewer may ask", *qa))
    return html.Div([html.H2(res["deal_title"], style={"color": "#00356b", "marginTop": 0, "fontSize": "20px"}), *parts])
