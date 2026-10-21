"""Coffee-chat tracker with AI prep and thank-you drafts (drafts only: the app never sends email)."""

from __future__ import annotations

from datetime import date

from dash import Input, Output, State, callback, dash_table, dcc, html, no_update

from .. import agents, db, llm
from ..ui import alert, bullets, card, error_box, icon, loading, page, page_icon

COLS = [("contact", "Contact"), ("bank", "Bank"), ("grp", "Group"), ("title", "Title"), ("chat_date", "Date"),
        ("thank_you", "Thank-you sent"), ("notes", "Notes")]


def _rows():
    out = []
    for c in db.coffee_chats():
        out.append({**c, "thank_you": "Yes" if c["thank_you_sent"] else "No"})
    return out


def layout():
    return page(
        "Coffee Chats",
        "Log every conversation. Your notes power bank-specific mock interviews and 'Why us?' answers.",
        page_icon("coffee"),
        card("Add a coffee chat",
             html.Div([
                 html.Div([html.Label("Contact name", className="field"), dcc.Input(id="cc-contact", type="text")]),
                 html.Div([html.Label("Bank", className="field"), dcc.Input(id="cc-bank", type="text")]),
                 html.Div([html.Label("Group", className="field"), dcc.Input(id="cc-group", type="text")]),
                 html.Div([html.Label("Title", className="field"), dcc.Input(id="cc-title", type="text", placeholder="Associate, VP...")]),
             ], className="grid grid-4"),
             html.Div([
                 html.Div([html.Label("Date", className="field"),
                           dcc.DatePickerSingle(className="date-field", id="cc-date", date=date.today().isoformat(), display_format="YYYY-MM-DD")]),
                 html.Div([html.Label("Notes: what did you learn? what advice did they give?", className="field"),
                           dcc.Textarea(id="cc-notes", style={"height": "80px"})]),
             ], className="grid grid-5-7", style={"gridTemplateColumns": "1fr 3fr"}),
             html.Div([html.Button("Save chat", id="cc-add", className="btn"), html.Span(id="cc-msg")], className="btn-row")),
        card("Your network",
             html.Div("Select a row, then use the buttons below.", className="hint", style={"marginBottom": "8px"}),
             dash_table.DataTable(
                 id="cc-table", data=_rows(), row_selectable="single", page_size=10,
                 columns=[{"name": n, "id": i} for i, n in COLS],
                 style_cell={"textAlign": "left", "fontFamily": "Segoe UI, system-ui", "fontSize": "14px", "padding": "8px",
                             "whiteSpace": "normal", "height": "auto", "maxWidth": "420px"},
                 style_header={"backgroundColor": "#00356b", "color": "white", "fontWeight": "600"},
                 style_data_conditional=[{"if": {"filter_query": "{thank_you} = No", "column_id": "thank_you"},
                                          "color": "#a4262c", "fontWeight": "600"}],
             ),
             html.Div([
                 html.Button([icon("spark"), " Prep me for this chat"], id="cc-prep", className="btn"),
                 html.Button("Draft thank-you note", id="cc-ty", className="btn btn-secondary"),
                 html.Button("Mark thank-you sent", id="cc-sent", className="btn btn-secondary"),
                 html.Button("Delete", id="cc-del", className="btn btn-danger"),
             ], className="btn-row")),
        loading(html.Div(id="cc-out"), "The Story Coach is preparing your draft…"),
    )


@callback(Output("cc-table", "data"), Output("cc-msg", "children"), Output("cc-contact", "value"), Output("cc-notes", "value"),
          Input("cc-add", "n_clicks"),
          State("cc-contact", "value"), State("cc-bank", "value"), State("cc-group", "value"), State("cc-title", "value"),
          State("cc-date", "date"), State("cc-notes", "value"), prevent_initial_call=True)
def add_chat(_, contact, bank, grp, title, chat_date, notes):
    if not (contact or "").strip() or not (bank or "").strip():
        return no_update, alert("Contact and bank are required.", "warning"), no_update, no_update
    db.execute("INSERT INTO coffee_chats (contact, bank, grp, title, chat_date, notes) VALUES (?,?,?,?,?,?)",
               (contact.strip(), bank.strip(), (grp or "").strip(), (title or "").strip(), chat_date, notes or ""))
    return _rows(), html.Span("Saved.", className="hint"), "", ""


@callback(Output("cc-out", "children"), Output("cc-table", "data", allow_duplicate=True),
          Output("cc-table", "selected_rows"),
          Input("cc-prep", "n_clicks"), Input("cc-ty", "n_clicks"), Input("cc-sent", "n_clicks"), Input("cc-del", "n_clicks"),
          State("cc-table", "data"), State("cc-table", "selected_rows"), prevent_initial_call=True,
          running=[(Output("cc-prep", "disabled"), True, False), (Output("cc-ty", "disabled"), True, False)])
def act(_p, _t, _s, _d, data, selected):
    from dash import ctx
    if not selected:
        return alert("Select a chat in the table first.", "warning"), no_update, no_update
    chat = data[selected[0]]
    trig = ctx.triggered_id
    if trig == "cc-sent":
        db.execute("UPDATE coffee_chats SET thank_you_sent = 1 WHERE id = ?", (chat["id"],))
        return alert(f"Marked thank-you to {chat['contact']} as sent.", "ok"), _rows(), selected
    if trig == "cc-del":
        db.execute("DELETE FROM coffee_chats WHERE id = ?", (chat["id"],))
        return alert(f"Deleted chat with {chat['contact']}.", "info"), _rows(), []
    try:
        if trig == "cc-prep":
            out = agents.coffee_chat_prep(chat, llm.new_run_id("chatprep"))
            return card(f"Prep for {chat['contact']} ({chat['bank']})",
                        html.Div([html.H4("Your 30-second intro"), html.Div(out["intro_30s"], className="model-answer")],
                                 className="feedback"),
                        html.Div([
                            html.Div([html.H4("Questions to ask"), bullets(out["questions_to_ask"])], className="feedback"),
                            html.Div([html.H4("Worth mentioning"), bullets(out["things_to_mention"])], className="feedback"),
                            html.Div([html.H4("Avoid"), bullets(out["avoid"])], className="feedback"),
                        ], className="grid grid-3")), no_update, no_update
        out = agents.thank_you_note(chat, llm.new_run_id("thanks"))
        text = f"Subject: {out['subject']}\n\n{out['body']}"
        return card(f"Thank-you draft for {chat['contact']}",
                    alert("Draft only: Superday Copilot never sends email. Review, edit and send it yourself.", "info"),
                    html.Div(text, className="model-answer", style={"whiteSpace": "pre-wrap"}),
                    html.Div([dcc.Clipboard(content=text, title="Copy email", className="copy-btn"),
                              html.Span("Copy email", className="hint")], className="copy-row")), no_update, no_update
    except llm.AIError as exc:
        return error_box(exc), no_update, no_update
