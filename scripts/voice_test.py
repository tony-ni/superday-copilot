"""Browser test for voice answers, using a fake SpeechRecognition (headless Chromium has no microphone).

It checks the real plumbing: mic button states, live transcript into the answer box, the timer, stop-on-grade,
delivery stats sent to the Grader, and read-aloud. Needs the app running on port 8050. Makes one real grading call.
Usage:  python scripts/voice_test.py
"""

import sys

from playwright.sync_api import sync_playwright

FAKE = r"""
window.__spoken = [];
window.speechSynthesis.speak = function (u) { window.__spoken.push(u.text); };
class FakeRecognition {
  constructor() { this.continuous = false; this.interimResults = false; this.lang = ''; this._t = []; }
  _emit(idx, text, isFinal) {
    const res = [{ transcript: text }]; res.isFinal = isFinal;
    const results = []; results[idx] = res; results.length = idx + 1;
    this.onresult && this.onresult({ resultIndex: idx, results });
  }
  start() {
    this._t.push(setTimeout(() => this._emit(0, 'equity value falls by', false), 300));
    this._t.push(setTimeout(() => this._emit(0, 'Equity value falls by 100 because shares are bought back,', true), 700));
    this._t.push(setTimeout(() => this._emit(1, 'um debt rises by 100, so enterprise value is unchanged.', true), 1200));
  }
  stop() { this._t.forEach(clearTimeout); setTimeout(() => this.onend && this.onend(), 50); }
}
window.SpeechRecognition = FakeRecognition; window.webkitSpeechRecognition = FakeRecognition;
"""

ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.add_init_script(FAKE)
    pg.goto("http://127.0.0.1:8050/technicals")
    pg.wait_for_selector(".page-enter")
    # Pick a specific question: EV-3 via the Topic + Question dropdowns is fiddly; use New question until EV topic.
    pg.click("#tech-new")
    pg.wait_for_selector("#tech-question .question-box")
    pg.click("[data-speak='tech-qtext']")
    spoken = pg.evaluate("window.__spoken")
    check("read aloud speaks the question (not the meta line)", spoken and "·" not in spoken[0], spoken[0][:60] if spoken else "")

    pg.click("#tech-mic")
    pg.wait_for_timeout(500)
    check("mic button switches to Stop", "Stop" in pg.inner_text("#tech-mic"))
    check("mic button shows recording state", "recording" in (pg.get_attribute("#tech-mic", "class") or ""))
    pg.wait_for_timeout(2600)
    val = pg.input_value("#tech-answer")
    check("live transcript fills the answer box", "enterprise value is unchanged" in val, val)
    status = pg.inner_text("#tech-voice-status")
    check("status shows a running timer", "Listening" in status and "0:0" in status, status)

    pg.click("#tech-grade")  # mousedown stops the recording first
    pg.wait_for_selector("#tech-feedback .feedback, #tech-feedback .alert", timeout=120_000)
    print("feedback area:", pg.inner_text("#tech-feedback")[:300].replace("\n", " | "))
    check("recording stopped when grading", "Answer by voice" in pg.inner_text("#tech-mic"))
    fb = pg.inner_text("#tech-feedback")
    check("feedback shows spoken-delivery stats", "SPOKEN DELIVERY" in fb.upper() and "wpm" in fb, fb[:200].replace("\n", " | "))
    check("filler word detected", "um" in fb.lower())

    # Ctrl+Enter on the behavioral page grades a typed answer
    pg.goto("http://127.0.0.1:8050/behavioral")
    pg.wait_for_selector(".page-enter")
    pg.click("#beh-new")
    pg.wait_for_selector("#beh-question .question-box")
    pg.fill("#beh-answer", "")
    pg.focus("#beh-answer")
    pg.keyboard.press("Control+Enter")
    pg.wait_for_selector("#beh-feedback .alert", timeout=10_000)
    check("Ctrl+Enter triggers grading (empty answer -> prompt)", "Answer first" in pg.inner_text("#beh-feedback"))
    b.close()
sys.exit(0 if ok else 1)
