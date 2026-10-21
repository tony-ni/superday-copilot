"""Mock interview: the Interviewer agent designs a bank-specific interview, the Grader scores every
answer (and may trigger a follow-up), and the Interviewer writes a Superday-style debrief."""

from __future__ import annotations

import json

import plotly.graph_objects as go
from dash import Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update

from .. import agents, db, llm, tools
from ..delivery import delivery_stats, target_seconds
from ..ui import (VOICE_NOTE, YALE, YALE_2, alert, badge, bullets, card, empty_state, error_box, feedback_panel,
                  fig_layout, icon, kbd, loading, page, page_icon, score_circle, voice_controls)

COMMON_BANKS = ["Goldman Sachs", "Morgan Stanley", "J.P. Morgan", "Bank of America", "Citi", "Evercore", "Lazard",
                "Centerview Partners", "Moelis & Company", "PJT Partners", "Perella Weinberg", "Guggenheim",
                "Houlihan Lokey", "Jefferies"]
MAX_FOLLOW_UPS = 2


def bank_options():
    """Banks with open applications first (nearest deadline first), then other tracked banks, then common banks."""
    tracked = [a["bank"] for a in db.applications() if a["status"] not in ("Submitted", "Rejected") and a["deadline"]
               and a["deadline"] >= db.now()[:10]]
    for b in [a["bank"] for a in db.applications()] + [c["bank"] for c in db.coffee_chats()]:
        if b not in tracked:
            tracked.append(b)
    return tracked + [b for b in COMMON_BANKS if b not in tracked]


def layout():
    banks = bank_options()
    setup = card(
        "Set up your interview",
        html.Div([
            html.Div([html.Label("Bank", className="field"),
                      dcc.Dropdown(banks, banks[0] if banks else None, id="mock-bank", clearable=False)]),
            html.Div([html.Label("Group", className="field"),
                      dcc.Input(id="mock-group", type="text", placeholder="e.g., M&A, Restructuring, Consumer & Retail",
                                value="")]),
            html.Div([html.Label("Length", className="field"),
                      dcc.Dropdown([{"label": f"{n} questions", "value": n} for n in (3, 5, 7)], 5, id="mock-n",
                                   clearable=False)]),
        ], className="grid grid-3"),
        dcc.Checklist([{"label": " Show feedback after each answer (turn off for a realistic Superday)", "value": "fb"}],
                      ["fb"], id="mock-fb", style={"marginTop": "12px"}),
        html.Div([html.Button([icon("play"), " Start mock interview"], id="mock-start", className="btn btn-lg")],
                 className="btn-row"),
        html.Div([
            html.Div([html.B("1"), html.Span("The Interviewer reads your coffee-chat notes for this bank and your weakest topics.")]),
            html.Div([html.B("2"), html.Span("Answer each question by voice or by typing. The Grader scores it against a "
                                             "reference answer and may ask a follow-up.")]),
            html.Div([html.B("3"), html.Span("Get a Superday-style debrief with a hire signal and what to drill next.")]),
        ], className="steps"),
        id="mock-setup",
    )
    live = html.Div([
        html.Div([
            card("Interview", html.Div(id="mock-transcript", className="transcript")),
        ]),
        html.Div([
            card(None,
                 html.Div(id="mock-progress", style={"marginBottom": "10px"}),
                 html.Div(id="mock-question"),
                 html.Div([html.Label("Your answer", className="field", htmlFor="mock-answer"),
                           voice_controls("mock", "mock-answer")], className="answer-head"),
                 dcc.Textarea(id="mock-answer", className="answer-box",
                              placeholder="Answer out loud with the mic, or type what you would say…"),
                 html.Div([
                     html.Button([icon("send"), " Submit answer"], id="mock-submit", className="btn"),
                     html.Button("End interview now", id="mock-end", className="btn btn-secondary"),
                     html.Span([kbd("Ctrl"), " + ", kbd("Enter"), " to submit"], className="hint shortcut"),
                 ], className="btn-row"),
                 html.Div(VOICE_NOTE, className="hint voice-note"),
                 loading(html.Div(id="mock-busy", style={"minHeight": "24px", "marginTop": "8px"}),
                         "The Grader is scoring your answer, then the Interviewer moves on…")),
            html.Div(id="mock-last-fb"),
        ]),
    ], className="grid grid-2", id="mock-live", style={"display": "none"})

    return page(
        "Mock Interview",
        "A bank-specific mock interview that remembers your networking and your weak spots.",
        page_icon("mic"),
        dcc.Store(id="mock-state"), dcc.Store(id="mock-voice"), html.Div(id="mock-scroll", style={"display": "none"}),
        loading(html.Div(setup), "The Interviewer is reading your notes and choosing questions…"), live,
        loading(html.Div(id="mock-summary"), "The Interviewer is writing your debrief…"),
        card("Past mock interviews", _history()),
    )


def _history():
    rows = db.query("SELECT * FROM mock_sessions WHERE status = 'finished' ORDER BY started DESC LIMIT 10")
    if not rows:
        return empty_state("history", "No finished interviews yet", "Your debriefs and hire signals will be listed here.")
    body = []
    for r in rows:
        s = json.loads(r["summary_json"] or "{}")
        body.append(html.Tr([html.Td(r["started"][:16].replace("T", " ")), html.Td(r["bank"]), html.Td(r["grp"] or "-"),
                             html.Td(f"{r['overall']:.1f}/5" if r["overall"] else "-"),
                             html.Td(s.get("debrief", {}).get("hire_signal", "-"))]))
    return html.Table([html.Thead(html.Tr([html.Th(h) for h in ("Date", "Bank", "Group", "Avg score", "Hire signal")])),
                       html.Tbody(body)], className="simple-table")


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
@callback(
    Output("mock-state", "data"), Output("mock-answer", "value"), Output("mock-busy", "children"),
    Output("mock-voice", "data"), Output("mock-voice-status", "children"),
    Input("mock-start", "n_clicks"), Input("mock-submit", "n_clicks"), Input("mock-end", "n_clicks"),
    State("mock-bank", "value"), State("mock-group", "value"), State("mock-n", "value"), State("mock-fb", "value"),
    State("mock-answer", "value"), State("mock-state", "data"), State("mock-voice", "data"),
    prevent_initial_call=True,
    running=[(Output("mock-submit", "disabled"), True, False), (Output("mock-start", "disabled"), True, False)],
)
def step(_start, _submit, _end, bank, group, n, fb, answer, state, voice):
    trigger = ctx.triggered_id
    keep = (no_update, no_update)
    try:
        if trigger == "mock-start":
            return _start_session(bank, group or "", int(n), bool(fb)), "", "", None, ""
        if not state or state.get("status") != "active":
            return no_update, no_update, "", *keep
        if trigger == "mock-submit":
            if not (answer or "").strip():
                return no_update, no_update, alert("Answer first: use the mic or type it.", "warning"), *keep
            state = _submit_answer(state, answer, voice)
            if state["pending"] is None:
                state = _finish(state)
            return state, "", "", None, ""
        if trigger == "mock-end":
            return _finish(state), "", "", None, ""
    except llm.AIError as exc:
        return no_update, no_update, error_box(exc), *keep
    return no_update, no_update, "", *keep


def _start_session(bank, group, n, show_fb):
    run_id = llm.new_run_id("mock")
    plan = agents.design_interview(bank, group, n, run_id)
    sid = db.execute("INSERT INTO mock_sessions (started, bank, grp, status, plan_json, run_id) VALUES (?,?,?,?,?,?)",
                     (db.now(), bank, group, "active", json.dumps(plan), run_id))
    first = plan["questions"][0]
    return {"session_id": sid, "run_id": run_id, "bank": bank, "group": group, "status": "active",
            "show_fb": show_fb, "opening": plan["opening"], "prep_note": plan["prep_note"],
            "queue": plan["questions"][1:], "total": len(plan["questions"]), "main_done": 0,
            "pending": {**first, "follow_up": False}, "turns": [], "follow_ups": 0}


def _submit_answer(state, answer, voice=None):
    q = state["pending"]
    ref = tools.question_by_id(q["id"])
    grade = agents.grade_answer(ref, answer, state["run_id"], asked_as=q["asked"],
                                delivery=delivery_stats(answer, voice, ref["id"]))
    agents.save_attempt("mock", ref, q["asked"], answer, grade, state["session_id"])
    state["turns"].append({**q, "answer": answer, "grade": grade})
    if not q["follow_up"]:
        state["main_done"] += 1
    follow = (grade.get("follow_up_question") or "").strip()
    if follow and not q["follow_up"] and state["follow_ups"] < MAX_FOLLOW_UPS and not grade.get("injection_attempt"):
        state["follow_ups"] += 1
        state["pending"] = {"id": q["id"], "category": q["category"], "asked": follow, "why": "Follow-up on your last answer",
                            "follow_up": True}
    elif state["queue"]:
        nxt = state["queue"].pop(0)
        state["pending"] = {**nxt, "follow_up": False}
    else:
        state["pending"] = None
    db.execute("UPDATE mock_sessions SET summary_json = ? WHERE id = ?", (json.dumps({"turns": state["turns"]}), state["session_id"]))
    return state


def _finish(state):
    state["status"] = "finished"
    state["pending"] = None
    turns = state["turns"]
    overall = round(sum(t["grade"]["overall"] for t in turns) / len(turns), 2) if turns else None
    debrief = agents.debrief(state["bank"], state["group"], turns, state["run_id"]) if turns else None
    state["debrief"], state["overall"] = debrief, overall
    db.execute("UPDATE mock_sessions SET finished = ?, status = 'finished', overall = ?, summary_json = ? WHERE id = ?",
               (db.now(), overall, json.dumps({"turns": turns, "debrief": debrief}), state["session_id"]))
    return state


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
@callback(
    Output("mock-setup", "style"), Output("mock-live", "style"), Output("mock-transcript", "children"),
    Output("mock-question", "children"), Output("mock-progress", "children"), Output("mock-last-fb", "children"),
    Output("mock-summary", "children"),
    Input("mock-state", "data"),
)
def render(state):
    if not state:
        return {}, {"display": "none"}, [], None, None, None, None
    active = state["status"] == "active"
    bubbles = [_bubble("Interviewer", f"{state['opening']}", "int")]
    for t in state["turns"]:
        bubbles.append(_bubble("Interviewer" + (" (follow-up)" if t["follow_up"] else ""), t["asked"], "int"))
        bubbles.append(_bubble("You", t["answer"], "you"))
        if state["show_fb"] or not active:
            g = t["grade"]
            bubbles.append(html.Div([html.Div("Grader", className="who"),
                                     f"{g['overall']}/5 · {g['verdict']}"], className="bubble bubble-fb"))
    if active and state["pending"]:
        bubbles.append(_bubble("Interviewer" + (" (follow-up)" if state["pending"]["follow_up"] else ""),
                               state["pending"]["asked"], "int"))

    question = progress = last_fb = summary = None
    if active and state["pending"]:
        p = state["pending"]
        lo, hi = target_seconds(p["id"])
        question = html.Div([
            html.Div([html.Div(f"{p['category']} · {p['id']} · {'follow-up' if p['follow_up'] else p['why']}", className="meta"),
                      html.Div(p["asked"], className="q-text")], id="mock-qtext"),
            html.Div([html.Button([icon("volume"), " Read aloud"], className="btn-ghost", type="button",
                                  **{"data-speak": "mock-qtext"}),
                      html.Span(f"Aim for {lo}–{hi} seconds", className="q-target")], className="q-actions"),
        ], className="question-box")
        n_now = min(state["main_done"] + 1, state["total"])
        progress = html.Div([
            html.Div([
                html.Span(f"Question {n_now} of {state['total']}", className="progress-label"),
                badge(f"{state['bank']}{' · ' + state['group'] if state['group'] else ''}", "ok"),
            ], className="progress-head"),
            html.Div(html.Div(style={"width": f"{100 * (n_now - 1) / state['total']:.0f}%"}, className="progress-fill"),
                     className="progress-track"),
            html.Div(alert("Prep note: " + state["prep_note"], "info"), style={"marginTop": "10px"}) if state["prep_note"] else None,
        ])
        if state["show_fb"] and state["turns"]:
            last = state["turns"][-1]
            last_fb = card("Feedback on your last answer", feedback_panel(last["grade"], tools.question_by_id(last["id"])))
    if not active:
        summary = _summary(state)
    return ({"display": "none"}, {} if active else {"display": "none"},
            bubbles, question, progress, last_fb, summary)


def _bubble(who, text, kind):
    return html.Div([html.Div(who, className="who"), text], className=f"bubble bubble-{kind}")


def _summary(state):
    turns, d = state["turns"], state.get("debrief")
    if not turns:
        return card("Interview ended", html.Div("No answers were submitted.", className="empty"))
    signal_kind = {"Strong yes": "ok", "Lean yes": "ok", "Lean no": "warn", "No": "bad"}.get(d["hire_signal"], "blue") if d else "blue"
    fig = go.Figure(go.Bar(
        x=[f"Q{i}{'f' if t['follow_up'] else ''}" for i, t in enumerate(turns, 1)], y=[t["grade"]["overall"] for t in turns],
        marker_color=[YALE if t["grade"]["overall"] >= 4 else YALE_2 for t in turns],
        text=[t["category"] for t in turns], hovertemplate="%{text}: %{y}/5<extra></extra>"))
    fig.update_yaxes(range=[0, 5.2], dtick=1, title="Score")
    detail = [html.Details([html.Summary(f"Q{i} · {t['category']} · {t['grade']['overall']}/5 · {t['asked'][:90]}"),
                            html.Div([html.P([html.B("Your answer: "), t["answer"]]),
                                      feedback_panel(t["grade"], tools.question_by_id(t["id"]))],
                                     style={"padding": "8px 4px"})], style={"marginBottom": "8px"})
              for i, t in enumerate(turns, 1)]
    return html.Div([
        card("Interview debrief",
             html.Div([
                 html.Div([score_circle(round(state["overall"])),
                           html.Div([html.Div(f"Average {state['overall']:.1f}/5 across {len(turns)} answers", className="kpi-label"),
                                     html.Div(d["headline"] if d else "", style={"fontWeight": 600, "fontSize": "17px"})])],
                          style={"display": "flex", "gap": "14px", "alignItems": "center"}),
                 html.Div(["Hire signal: ", badge(d["hire_signal"], signal_kind)], style={"margin": "10px 0"}) if d else None,
                 html.P(d["overall_assessment"]) if d else None,
             ]),
             html.Div([
                 html.Div([html.H4("Strengths"), bullets(d["top_strengths"] if d else [])], className="feedback"),
                 html.Div([html.H4("Priority fixes"), bullets(d["priority_fixes"] if d else [])], className="feedback"),
                 html.Div([html.H4("Drill next"), bullets([f"{x['category']}: {x['why']}" for x in (d["next_drills"] if d else [])])],
                          className="feedback"),
             ], className="grid grid-3"),
             dcc.Graph(figure=fig_layout(fig, 240), config={"displayModeBar": False}),
             html.Div([dcc.Link(html.Button("Start another interview", className="btn btn-secondary"), href="/mock", refresh=True),
                       dcc.Link(html.Button("Drill technicals", className="btn btn-secondary"), href="/technicals")],
                      className="btn-row")),
        card("Answer-by-answer feedback", *detail),
    ])


# Keep the newest message in view.
clientside_callback(
    """function(children) {
        setTimeout(function() {
            var el = document.getElementById('mock-transcript');
            if (el) { el.scrollTop = el.scrollHeight; }
        }, 60);
        return '';
    }""",
    Output("mock-scroll", "children"), Input("mock-transcript", "children"),
)
