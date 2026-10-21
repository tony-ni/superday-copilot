"""Application tracker (no AI needed: plain code is cheaper and always right)."""

from __future__ import annotations

from datetime import date

from dash import Input, Output, State, callback, dash_table, dcc, html, no_update

from .. import db
from ..ui import alert, card, icon, page, page_icon

STATUSES = ["Not started", "In progress", "Submitted", "Interviewing", "Offer", "Rejected"]
COLS = [("bank", "Bank"), ("grp", "Group"), ("office", "Office"), ("deadline", "Deadline"), ("days_left", "Days left"),
        ("status", "Status"), ("referral", "Referral"), ("notes", "Notes")]


def _rows():
    today = date.today()
    return [{**a, "days_left": (date.fromisoformat(a["deadline"]) - today).days if a["deadline"] else None}
            for a in db.applications()]


def layout():
    return page(
        "Applications",
        "Every deadline in one place. Edit Status, Referral or Notes directly in the table; changes save automatically.",
        page_icon("list"),
        card("Add an application",
             html.Div([
                 html.Div([html.Label("Bank", className="field"), dcc.Input(id="ap-bank", type="text")]),
                 html.Div([html.Label("Group", className="field"), dcc.Input(id="ap-group", type="text")]),
                 html.Div([html.Label("Office", className="field"), dcc.Input(id="ap-office", type="text", value="New York")]),
                 html.Div([html.Label("Deadline", className="field"),
                           dcc.DatePickerSingle(className="date-field", id="ap-deadline", display_format="YYYY-MM-DD")]),
             ], className="grid grid-4"),
             html.Div([html.Button([icon("check"), " Add application"], id="ap-add", className="btn"), html.Span(id="ap-msg")], className="btn-row")),
        card("Tracker",
             dash_table.DataTable(
                 id="ap-table", data=_rows(), row_deletable=True, editable=True, sort_action="native",
                 columns=[{"name": n, "id": i, "editable": i in ("status", "referral", "notes"),
                           **({"presentation": "dropdown"} if i == "status" else {})} for i, n in COLS],
                 dropdown={"status": {"options": [{"label": s, "value": s} for s in STATUSES]}},
                 style_cell={"textAlign": "left", "fontFamily": "Segoe UI, system-ui", "fontSize": "14px", "padding": "9px 10px",
                             "whiteSpace": "normal", "height": "auto", "border": "none", "borderBottom": "1px solid #dde5ef"},
                 style_cell_conditional=[
                     {"if": {"column_id": c}, "whiteSpace": "nowrap"} for c in ("office", "deadline", "days_left", "status")
                 ] + [{"if": {"column_id": "days_left"}, "textAlign": "center", "width": "80px"},
                      {"if": {"column_id": "bank"}, "fontWeight": "600"}],
                 style_header={"backgroundColor": "#00356b", "color": "white", "fontWeight": "600", "border": "none"},
                 style_data_conditional=[
                     {"if": {"filter_query": "{days_left} <= 7 && {days_left} >= 0 && {status} != Submitted", "column_id": "days_left"},
                      "backgroundColor": "#fff4dc", "color": "#8a5a00", "fontWeight": "700"},
                     {"if": {"filter_query": "{days_left} < 0 && {status} != Submitted", "column_id": "days_left"},
                      "backgroundColor": "#fde8e8", "color": "#a4262c", "fontWeight": "700"},
                     {"if": {"filter_query": "{status} = Submitted", "column_id": "status"}, "color": "#1f7a4d", "fontWeight": "700"},
                     {"if": {"filter_query": "{status} = Interviewing", "column_id": "status"}, "color": "#286dc0", "fontWeight": "700"},
                     {"if": {"filter_query": "{status} = Offer", "column_id": "status"}, "color": "#ffffff",
                      "backgroundColor": "#1f7a4d", "fontWeight": "700"},
                     {"if": {"filter_query": "{status} = Rejected"}, "color": "#8a96a3"},
                     {"if": {"state": "active"}, "backgroundColor": "#e8f0fa", "border": "1px solid #286dc0"},
                 ],
                 css=[{"selector": ".Select-menu-outer", "rule": "display: block !important"}],
             ),
             html.Div([html.Span("Click a Status, Referral or Notes cell to edit it. Click × to delete a row. "),
                       html.Span(id="ap-saved")], className="hint", style={"marginTop": "8px"})),
    )


@callback(Output("ap-table", "data"), Output("ap-msg", "children"), Input("ap-add", "n_clicks"),
          State("ap-bank", "value"), State("ap-group", "value"), State("ap-office", "value"), State("ap-deadline", "date"),
          prevent_initial_call=True)
def add(_, bank, grp, office, deadline):
    if not (bank or "").strip():
        return no_update, alert("Bank is required.", "warning")
    db.execute("INSERT INTO applications (bank, grp, office, deadline, status) VALUES (?,?,?,?,?)",
               (bank.strip(), (grp or "").strip(), (office or "").strip(), deadline, "Not started"))
    return _rows(), html.Span("Added.", className="hint")


@callback(Output("ap-saved", "children"), Input("ap-table", "data"), State("ap-table", "data_previous"),
          prevent_initial_call=True)
def save(data, previous):
    if previous is None:
        return no_update
    now_ids = {r["id"] for r in data}
    for r in previous:
        if r["id"] not in now_ids:
            db.execute("DELETE FROM applications WHERE id = ?", (r["id"],))
    prev = {r["id"]: r for r in previous}
    changed = 0
    for r in data:
        p = prev.get(r["id"])
        if p and any(p.get(k) != r.get(k) for k in ("status", "referral", "notes")):
            status = r["status"] if r["status"] in STATUSES else p["status"]
            db.execute("UPDATE applications SET status = ?, referral = ?, notes = ? WHERE id = ?",
                       (status, r.get("referral") or "", r.get("notes") or "", r["id"]))
            changed += 1
    return f"Saved at {db.now()[11:16]}." if changed or len(data) != len(previous) else no_update
