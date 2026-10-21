/* Voice answers, read-aloud questions and Ctrl+Enter shortcuts.
 *
 * Speech-to-text uses the browser's built-in Web Speech API (Chrome and Edge), so it needs no API key.
 * Superday Copilot never records or stores audio. The browser's speech service turns it into text,
 * and only that text is graded.
 *
 * Markup contract (set in Python):
 *   <button id="{p}-mic" data-voice-target="{textarea id}" data-voice-prefix="{p}">
 *   <span id="{p}-voice-status">   status line, updated through dash_clientside.set_props
 *   dcc.Store id="{p}-voice"        receives {seconds, words} for delivery stats
 *   <button data-speak="{element id}">   reads the question in that element aloud
 */
(function () {
  "use strict";
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var session = null; // the one active recording

  function setProps(id, props) {
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props(id, props);
    }
  }

  function fmt(sec) {
    var m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function idleLabel() { return "🎤 Answer by voice"; }

  function stop(reason) {
    if (!session) return;
    var s = session;
    session = null;
    clearInterval(s.timer);
    try { s.rec.stop(); } catch (e) { /* already stopped */ }
    var seconds = Math.max(0, (Date.now() - s.started) / 1000);
    var prev = (window.__voiceTotals && window.__voiceTotals[s.prefix]) || 0;
    window.__voiceTotals = window.__voiceTotals || {};
    window.__voiceTotals[s.prefix] = prev + seconds;
    var text = (document.getElementById(s.target) || {}).value || "";
    var words = text.trim() ? text.trim().split(/\s+/).length : 0;
    setProps(s.prefix + "-voice", { data: { seconds: Math.round(window.__voiceTotals[s.prefix]), words: words, ts: Date.now() } });
    setProps(s.prefix + "-mic", { children: idleLabel(), className: "btn btn-voice" });
    setProps(s.prefix + "-voice-status", {
      children: reason || ("Recorded " + fmt(seconds) + ". Check the transcript (finance terms like EBITDA can be misheard), then grade it.")
    });
  }

  function start(btn) {
    var target = btn.getAttribute("data-voice-target");
    var prefix = btn.getAttribute("data-voice-prefix");
    if (!SR) {
      setProps(prefix + "-voice-status", { children: "Voice input needs Chrome or Edge. You can still type your answer." });
      return;
    }
    var box = document.getElementById(target);
    var base = box && box.value ? box.value.replace(/\s*$/, " ") : "";
    var rec = new SR();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    var finalText = "";
    session = { rec: rec, target: target, prefix: prefix, started: Date.now(), timer: null };

    rec.onresult = function (ev) {
      var interim = "";
      for (var i = ev.resultIndex; i < ev.results.length; i++) {
        var r = ev.results[i];
        if (r.isFinal) { finalText += r[0].transcript.trim() + " "; }
        else { interim += r[0].transcript; }
      }
      setProps(target, { value: (base + finalText + interim).replace(/\s+/g, " ").replace(/^\s/, "") });
    };
    rec.onerror = function (ev) {
      var msg = {
        "not-allowed": "Microphone access is blocked. Allow the microphone for this site in the address bar, then try again.",
        "service-not-allowed": "Microphone access is blocked. Allow the microphone for this site in the address bar, then try again.",
        "no-speech": "I didn't hear anything. Check your microphone and try again.",
        "audio-capture": "No microphone was found.",
        "network": "The browser's speech service is unreachable (needs internet). You can still type your answer."
      }[ev.error] || ("Voice input stopped (" + ev.error + ").");
      stop(msg);
    };
    rec.onend = function () { if (session && session.rec === rec) stop(); };

    try { rec.start(); } catch (e) { session = null; return; }
    setProps(prefix + "-mic", { children: "■ Stop recording", className: "btn btn-voice recording" });
    setProps(prefix + "-voice-status", { children: "Listening… 0:00. Speak your answer, then click Stop." });
    session.timer = setInterval(function () {
      if (!session) return;
      setProps(prefix + "-voice-status", { children: "Listening… " + fmt((Date.now() - session.started) / 1000) + ". Click Stop when you're done." });
    }, 1000);
  }

  document.addEventListener("click", function (e) {
    var mic = e.target.closest && e.target.closest("[data-voice-target]");
    if (mic) {
      e.preventDefault();
      if (session && session.prefix === mic.getAttribute("data-voice-prefix")) { stop(); }
      else { if (session) stop(); start(mic); }
      return;
    }
    var speak = e.target.closest && e.target.closest("[data-speak]");
    if (speak && window.speechSynthesis) {
      var el = document.getElementById(speak.getAttribute("data-speak"));
      if (!el) return;
      var clone = el.cloneNode(true);
      clone.querySelectorAll(".meta").forEach(function (m) { m.remove(); });
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(clone.textContent.trim());
      u.lang = "en-US";
      u.rate = 1.0;
      window.speechSynthesis.speak(u);
      return;
    }
    // Starting a new question resets the voice timer for that drill.
    var nb = e.target.closest && e.target.closest("[id$='-new'], #mock-submit, #mock-start");
    if (nb && window.__voiceTotals) {
      var p = nb.id.replace(/-(new|submit|start)$/, "");
      window.__voiceTotals[p] = 0;
      if (session && session.prefix === p) stop("");
    }
  });

  // Pressing Grade/Submit while recording finishes the recording first. This runs in the capture phase of the
  // same click, before Dash handles it, so the click still reaches the button and the stats are already stored.
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[id$='-grade'], #mock-submit");
    if (b && session) stop();
  }, true);

  // Ctrl+Enter (Cmd+Enter on Mac) submits the answer box.
  var SUBMIT = { "tech-answer": "tech-grade", "beh-answer": "beh-grade", "mock-answer": "mock-submit" };
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey)) return;
    var id = e.target && e.target.id;
    if (SUBMIT[id]) {
      e.preventDefault();
      if (session) stop();
      var b = document.getElementById(SUBMIT[id]);
      if (b && !b.disabled) b.click();
    }
  });
})();
