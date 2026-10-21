"""Dashboard: KPIs, code-computed alerts, the Planner agent's week plan and score charts."""

from __future__ import annotations

import json
from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from .. import agents, db, llm
from ..ui import YALE, YALE_2, alert, badge, card, error_box, fig_layout, kpi, loading, page

MODULE_LINKS = {"Mock Interview": "/mock", "Technicals": "/technicals", "Behavioral": "/behavioral",
                "Deal Prep": "/deals", "Coffee Chats": "/chats", "Applications": "/applications"}


def layout():
    apps = db.applications()
    chats = db.coffee_chats()
    today = date.today()
    submitted = sum(a["status"] == "Submitted" for a in apps)
    upcoming = [a for a in apps if a["deadline"] and a["status"] != "Submitted" and a["deadline"] >= today.isoformat()]
    next_deadline = upcoming[0] if upcoming else None
    pending_ty = [c for c in chats if c["chat_date"] and c["chat_date"] < today.isoformat() and not c["thank_you_sent"]]
    recent = db.query("SELECT overall FROM attempts ORDER BY ts DESC LIMIT 10")
    avg = round(sum(r["overall"] for r in recent) / len(recent), 1) if recent else None
    prof = db.profile()

    kpis = html.Div([
        kpi("Applications", f"{submitted}/{len(apps)}", "submitted"),
        kpi("Next deadline", next_deadline["bank"] if next_deadline else "None",
            f"due {next_deadline['deadline']}" if next_deadline else "nothing pending"),
        kpi("Coffee chats", str(len(chats)), f"{len(pending_ty)} thank-you note(s) pending"),
        kpi("Practice score", f"{avg}/5" if avg else "n/a", "average of last 10 answers"),
    ], className="grid grid-4", style={"marginBottom": "18px"})

    alerts = agents.deterministic_alerts()
    alert_box = card("Alerts", html.Div([alert(a["text"], a["level"]) for a in alerts] or
                                        [alert("No urgent items. Nice work.", "ok")]),
                     html.Div("Computed directly from your trackers (not by AI), so they are always accurate.", className="hint"))

    saved = prof.get("last_plan")
    plan_body = _render_plan(json.loads(saved)) if saved else html.Div(
        "Click the button and the Planner agent will read your applications, coffee chats and practice scores, "
        "then build your next 7 days.", className="empty")

    return page(
        f"Welcome back, {prof.get('name', 'candidate').split(' (')[0]}",
        "Your investment banking recruiting command center: networking, applications and interview prep in one place.",
        kpis,
        html.Div([
            html.Div([
                card("This week's plan",
                     html.Div([html.Button("Build my week with the Planner agent", id="plan-btn", className="btn")],
                              className="btn-row", style={"marginTop": 0, "marginBottom": "10px"}),
                     loading(html.Div(plan_body, id="plan-out"))),
            ]),
            html.Div([alert_box, card("Practice scores by topic", dcc.Graph(figure=_score_fig(), config={"displayModeBar": False}))]),
        ], className="grid grid-2"),
    )


def _render_plan(plan: dict):
    rows = []
    for t in plan.get("tasks", []):
        rows.append(html.Div([
            html.Div(t["day"], className="task-day"),
            html.Div([html.Div(t["task"]), html.Div(t["why"], className="task-why"),
                      badge("check: unknown bank", "warn") if t.get("unverified") else None]),
            html.Div([badge(f"{t['minutes']} min"), html.Br(),
                      dcc.Link(t["module"] + " ›", href=MODULE_LINKS.get(t["module"], "/"), style={"fontSize": "13px"})],
                     style={"textAlign": "right"}),
        ], className="task"))
    return html.Div([html.P(html.B(plan.get("headline", "")), style={"marginTop": 0}), *rows,
                     html.Div(f"Generated {plan.get('generated', '')}", className="hint", style={"marginTop": "8px"})])


def _score_fig():
    summary = db.score_summary()
    fig = go.Figure()
    if summary:
        cats = [s["category"] for s in summary]
        vals = [s["avg_score"] for s in summary]
        fig.add_bar(x=vals, y=cats, orientation="h", marker_color=[YALE if v >= 3.5 else YALE_2 for v in vals],
                    text=[f"{v:.1f}" for v in vals], textposition="outside",
                    hovertemplate="%{y}: %{x:.1f}/5<extra></extra>")
        fig.update_xaxes(range=[0, 5.5], title="Average score (latest 5 answers)")
    else:
        fig.add_annotation(text="No practice yet", showarrow=False)
    return fig_layout(fig, height=280)


@callback(Output("plan-out", "children"), Input("plan-btn", "n_clicks"), prevent_initial_call=True)
def build_plan(_):
    try:
        plan = agents.plan_week(llm.new_run_id("plan"))
    except llm.AIError as exc:
        return error_box(exc)
    plan["generated"] = db.now().replace("T", " ")
    db.set_profile("last_plan", json.dumps(plan))
    return _render_plan(plan)
