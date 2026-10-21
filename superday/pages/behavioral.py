"""Behavioral: the Story Coach drafts answers from your resume + coffee-chat notes; then drill them."""

from __future__ import annotations

from dash import Input, Output, State, callback, dcc, html, no_update

from .. import agents, db, llm
from ..ui import alert, badge, bullets, card, error_box, icon, loading, page, page_icon
from . import practice
from .mock import bank_options

practice.register("beh", "behavioral")

KIND_OPTS = [{"label": "Walk me through your resume", "value": "walk"},
             {"label": "Why investment banking?", "value": "why_ib"},
             {"label": "Why this bank?", "value": "why_bank"},
             {"label": "Why switch careers now?", "value": "switch"}]


def layout():
    banks = bank_options()
    prof = db.profile()
    return page(
        "Behavioral & Story",
        "Turn your real experience and what bankers told you into answers that only you could give.",
        page_icon("chat"),
        html.Div([
            html.Div([
                card("Story Coach",
                     html.Div([
                         html.Div([html.Label("Answer to draft", className="field"),
                                   dcc.Dropdown(KIND_OPTS, "why_bank", id="story-kind", clearable=False)]),
                         html.Div([html.Label("Target bank", className="field"),
                                   dcc.Dropdown(banks, banks[0] if banks else None, id="story-bank")]),
                     ], className="grid grid-2"),
                     html.Div([html.Button([icon("spark"), " Draft my answer"], id="story-btn", className="btn")], className="btn-row"),
                     html.Div("Uses only your resume and your coffee-chat notes. Every banker it cites is checked "
                              "against your tracker.", className="hint", style={"marginTop": "8px"})),
                loading(html.Div(id="story-out"), "The Story Coach is reading your resume and coffee-chat notes…"),
            ]),
            html.Div([
                card("Your resume (used by the Story Coach)",
                     dcc.Textarea(id="resume-text", value=prof.get("resume", ""), style={"height": "260px"}),
                     html.Div([html.Button("Save resume", id="resume-save", className="btn btn-secondary"),
                               html.Span(id="resume-saved", className="hint")], className="btn-row")),
            ]),
        ], className="grid grid-2"),
        html.Div([
            practice.block("beh", ["Behavioral"], "Practice a behavioral question", "Behavioral"),
            card("Recent attempts", practice.history_table("behavioral")),
        ], className="grid grid-2"),
    )


@callback(Output("story-out", "children"), Input("story-btn", "n_clicks"),
          State("story-kind", "value"), State("story-bank", "value"), prevent_initial_call=True,
          running=[(Output("story-btn", "disabled"), True, False)])
def draft(_, kind, bank):
    if kind == "why_bank" and not bank:
        return alert("Pick a target bank first.", "warning")
    try:
        out = agents.draft_story(kind, bank or "", llm.new_run_id("story"))
    except llm.AIError as exc:
        return error_box(exc)
    sources = [html.Li([badge("verified" if s["verified"] else "not in your tracker", "ok" if s["verified"] else "bad"), " ",
                        html.B(s["contact"] if s["source"] == "coffee_chat" else "Resume"), f": {s['detail']}"])
               for s in out["sources_used"]]
    bad = [s for s in out["sources_used"] if not s["verified"]]
    return card(
        f"Draft · about {out['estimated_seconds']} seconds spoken",
        alert("Warning: this draft cites a contact who is not in your coffee-chat tracker. Remove that part.", "danger") if bad else None,
        html.Div(out["answer"], className="model-answer", style={"whiteSpace": "pre-wrap"}),
        html.Div([html.H4("Where each point came from"), html.Ul(sources) if sources else html.Div("No sources listed.", className="empty")],
                 className="feedback"),
        html.Div([html.H4("Coach tips"), bullets(out["tips"])], className="feedback"),
        html.Div([dcc.Clipboard(content=out["answer"], title="Copy answer", className="copy-btn"),
                  html.Span("Copy answer", className="hint")], className="copy-row"),
    )


@callback(Output("resume-saved", "children"), Input("resume-save", "n_clicks"), State("resume-text", "value"),
          prevent_initial_call=True)
def save_resume(_, text):
    db.set_profile("resume", text or "")
    return "Saved."
