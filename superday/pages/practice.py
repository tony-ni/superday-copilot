"""Reusable drill block: pick a question, answer it by typing or by voice, get graded against the reference answer."""

from __future__ import annotations

from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from .. import agents, db, llm, tools
from ..delivery import delivery_stats, target_seconds
from ..ui import (VOICE_NOTE, alert, badge, card, empty_state, error_box, feedback_panel, icon, kbd, loading,
                  voice_controls)

RANDOM = "__random__"


def block(prefix: str, categories: list[str], title: str, default_cat: str):
    cat_opts = [{"label": c, "value": c} for c in categories]
    return html.Div([
        dcc.Store(id=f"{prefix}-store", data={"seen": []}),
        dcc.Store(id=f"{prefix}-voice"),
        card(title,
             html.Div([
                 html.Div([html.Label("Topic", className="field"),
                           dcc.Dropdown(cat_opts, default_cat, id=f"{prefix}-cat", clearable=False)]),
                 html.Div([html.Label("Question", className="field"),
                           dcc.Dropdown(_qopts(default_cat), RANDOM, id=f"{prefix}-qpick", clearable=False)]),
             ], className="grid grid-2"),
             html.Div([html.Button([icon("shuffle"), " New question"], id=f"{prefix}-new", className="btn")],
                      className="btn-row"),
             html.Div(id=f"{prefix}-question", className="question-slot",
                      children=empty_state("question", "Pick a question to start",
                                           "Choose a topic, then click New question. You can answer by typing or by voice.")),
             html.Div([
                 html.Label("Your answer", className="field", htmlFor=f"{prefix}-answer"),
                 voice_controls(prefix, f"{prefix}-answer"),
             ], className="answer-head"),
             dcc.Textarea(id=f"{prefix}-answer", className="answer-box",
                          placeholder="Say it out loud with the mic, or type what you would say…"),
             html.Div([
                 html.Button([icon("check"), " Grade my answer"], id=f"{prefix}-grade", className="btn"),
                 html.Button([icon("reply"), " Answer the follow-up"], id=f"{prefix}-follow",
                             className="btn btn-secondary", style={"display": "none"}),
                 html.Span([kbd("Ctrl"), " + ", kbd("Enter"), " to grade"], className="hint shortcut"),
             ], className="btn-row"),
             html.Div(VOICE_NOTE, className="hint voice-note")),
        loading(html.Div(id=f"{prefix}-feedback"), "The Grader is scoring your answer against the reference…"),
    ])


def register(prefix: str, source: str):
    @callback(Output(f"{prefix}-qpick", "options"), Output(f"{prefix}-qpick", "value"), Input(f"{prefix}-cat", "value"),
              prevent_initial_call=True)
    def _options(cat):
        return _qopts(cat), RANDOM

    @callback(
        Output(f"{prefix}-store", "data"), Output(f"{prefix}-question", "children"), Output(f"{prefix}-answer", "value"),
        Output(f"{prefix}-feedback", "children", allow_duplicate=True), Output(f"{prefix}-follow", "style", allow_duplicate=True),
        Output(f"{prefix}-voice", "data", allow_duplicate=True), Output(f"{prefix}-voice-status", "children", allow_duplicate=True),
        Input(f"{prefix}-new", "n_clicks"), Input(f"{prefix}-follow", "n_clicks"),
        State(f"{prefix}-cat", "value"), State(f"{prefix}-qpick", "value"), State(f"{prefix}-store", "data"),
        prevent_initial_call=True,
    )
    def _new(n_new, n_follow, cat, qpick, store):
        store = store or {"seen": []}
        if ctx.triggered_id == f"{prefix}-follow" and store.get("follow_up"):
            store["asked"] = store.pop("follow_up")
            q = tools.question_by_id(store["qid"])
            return store, _qbox(prefix, q, store["asked"], follow=True), "", None, {"display": "none"}, None, ""
        q = tools.question_by_id(qpick) if qpick and qpick != RANDOM else tools.pick_practice_question(cat, store["seen"])
        store.update(qid=q["id"], asked=q["question"], seen=(store["seen"] + [q["id"]])[-30:])
        store.pop("follow_up", None)
        return store, _qbox(prefix, q, q["question"]), "", None, {"display": "none"}, None, ""

    @callback(
        Output(f"{prefix}-feedback", "children"), Output(f"{prefix}-store", "data", allow_duplicate=True),
        Output(f"{prefix}-follow", "style"),
        Input(f"{prefix}-grade", "n_clicks"), State(f"{prefix}-answer", "value"), State(f"{prefix}-store", "data"),
        State(f"{prefix}-voice", "data"),
        prevent_initial_call=True,
        running=[(Output(f"{prefix}-grade", "disabled"), True, False)],
    )
    def _grade(_, answer, store, voice):
        if not store or not store.get("qid"):
            return alert("Click 'New question' first.", "warning"), no_update, no_update
        if not (answer or "").strip():
            return alert("Answer first: type it or use the mic.", "warning"), no_update, no_update
        q = tools.question_by_id(store["qid"])
        stats = delivery_stats(answer, voice, q["id"])
        try:
            g = agents.grade_answer(q, answer, llm.new_run_id(source), asked_as=store["asked"], delivery=stats)
        except llm.AIError as exc:
            return error_box(exc), no_update, no_update
        agents.save_attempt(source, q, store["asked"], answer, g)
        follow = (g.get("follow_up_question") or "").strip()
        store["follow_up"] = follow or None
        return (card("Feedback", feedback_panel(g, q), className="card-feedback"), store,
                {} if follow and not g.get("injection_attempt") else {"display": "none"})


def _qopts(cat):
    opts = [{"label": "Random question" if cat != "Weakest topic" else "Random from your weakest topic", "value": RANDOM}]
    if cat and cat != "Weakest topic":
        opts += [{"label": f"{q['id']} · {q['question'][:80]}", "value": q["id"]}
                 for q in tools.question_bank() if q["category"] == cat]
    return opts


def _qbox(prefix, q, asked, follow=False):
    stars = "●" * q["difficulty"] + "○" * (3 - q["difficulty"])
    lo, hi = target_seconds(q["id"])
    return html.Div([
        html.Div([
            html.Div(f"{q['category']} · {q['id']} · difficulty {stars}" + (" · follow-up" if follow else ""), className="meta"),
            html.Div(asked, className="q-text"),
        ], id=f"{prefix}-qtext"),
        html.Div([
            html.Button([icon("volume"), " Read aloud"], className="btn-ghost", type="button", **{"data-speak": f"{prefix}-qtext"}),
            html.Span(f"Aim for {lo}–{hi} seconds", className="q-target"),
        ], className="q-actions"),
    ], className="question-box")


def history_table(source: str):
    rows = db.query("SELECT ts, category, question, overall FROM attempts WHERE source = ? ORDER BY ts DESC LIMIT 12", (source,))
    if not rows:
        return empty_state("history", "No attempts yet", "Your graded answers will show up here.")
    return html.Table([
        html.Thead(html.Tr([html.Th("When"), html.Th("Topic"), html.Th("Question"), html.Th("Score")])),
        html.Tbody([html.Tr([html.Td(r["ts"][5:10]), html.Td(r["category"]), html.Td(r["question"][:70]),
                             html.Td(badge(f"{r['overall']}/5", "ok" if r["overall"] >= 4 else "warn" if r["overall"] == 3 else "bad"))])
                    for r in rows]),
    ], className="simple-table")
