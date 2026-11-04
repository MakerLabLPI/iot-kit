/* The projector page. One state snapshot at a time, from the inlined
   initial state and then from /events (SSE). Everything is rendered from
   the snapshot; the only client-side state is the countdown clock. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const RING = 2 * Math.PI * 52;

  let state = JSON.parse($("initial").textContent);
  let clockOffset = 0;            // server time - client time, seconds
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const OUTCOME = {
    CC: ["cc", "Nice handshake."],
    BB: ["bb", "Trust issues."],
    CB: ["", "Backstabbed."],
    BC: ["", "Backstabbed."],
  };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls = "") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const hhmmss = (ts) => new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });

  // --- header ------------------------------------------------------------------
  function renderHeader() {
    const s = state;
    const clock = document.querySelector(".clock");
    const label = $("phase-label");
    const hint = $("phase-hint");
    clock.className = "clock " + s.phase;
    label.className = "phase-label " + (s.paused ? "paused" : s.phase);
    $("round-no").textContent = s.round ? `Round ${s.round}` : "No round yet";
    if (s.paused) {
      label.textContent = "Paused";
      hint.textContent = "The teacher will resume the game.";
    } else if (s.phase === "open") {
      label.textContent = "Open";
      hint.textContent = s.pause_pending ? "Last round before the pause." : "Press a button. One clock for everyone.";
    } else if (s.phase === "reveal") {
      label.textContent = "Reveal";
      hint.textContent = "Next round opens in a moment.";
    } else {
      label.textContent = "Waiting for players";
      const n = s.eligible;
      hint.textContent = n === 1 ? "One player in. Need one more." : n === 0 ? "Nobody has joined yet." : "Starting…";
    }
  }

  function tickClock() {
    const s = state;
    const ring = $("ring");
    const secs = $("secs");
    if (!s.phase_ends || s.phase === "idle") {
      ring.style.strokeDashoffset = RING;
      secs.textContent = "";
    } else {
      const now = Date.now() / 1000 + clockOffset;
      const total = s.phase_ends - s.phase_started;
      const left = Math.max(0, s.phase_ends - now);
      ring.style.strokeDashoffset = RING * (1 - left / total);
      secs.textContent = Math.ceil(left);
    }
    requestAnimationFrame(tickClock);
  }

  // --- matches -------------------------------------------------------------------
  const cards = new Map();   // key -> {el, sig}

  function sideHtml(m, pid, side) {
    let status;
    if (state.phase === "reveal" || (state.phase === "idle" && m.points[pid] !== undefined)) {
      const mv = m.moves[pid];
      const rnd = m.random.includes(pid);
      status = `<span class="face ${mv}"><span class="word">${icon(mv === "C" ? "hand" : "dagger")}${mv === "C" ? "Cooperate" : "Betray"}</span>` +
        (rnd ? `<span class="dice" title="no move before the clock ran out: random move">${icon("dice")}random</span>` : "<span></span>") +
        `<span class="pts">${m.points[pid]}</span></span>`;
    } else if (m.locked[pid]) {
      status = `<span class="locked">${icon("tick")}Locked in</span>`;
    } else {
      status = `<span class="waiting">${icon("dots")}Thinking</span>`;
    }
    return `<div class="side ${side}"><div class="pname">${esc(pid)}</div><div class="status">${status}</div></div>`;
  }

  function renderMatches() {
    const s = state;
    const box = $("matches");
    const wanted = new Set();
    const showResults = s.phase === "reveal" || s.phase === "idle";

    if (!s.matches.length) {
      cards.clear();
      box.innerHTML = `<div class="placeholder">${s.eligible >= 2 ? "Pairing up…" : "Waiting for two players to join."}</div>`;
      return;
    }
    s.matches.forEach((m) => {
      const key = `${s.round}:${m.a}:${m.b}`;
      wanted.add(key);
      const sigA = `${m.locked[m.a]}${showResults ? m.moves[m.a] + m.points[m.a] : ""}`;
      const sigB = `${m.locked[m.b]}${showResults ? m.moves[m.b] + m.points[m.b] : ""}`;
      const sig = `${s.phase}|${sigA}|${sigB}`;
      let c = cards.get(key);
      if (!c) {
        const el = document.createElement("article");
        el.className = "match";
        c = { el, sig: null, sideSig: {} };
        cards.set(key, c);
        box.appendChild(el);
      }
      if (c.sig === sig) return;
      c.sig = sig;
      const outcome = showResults && m.points[m.a] !== undefined ? OUTCOME[m.moves[m.a] + m.moves[m.b]] : null;
      // Rebuild only the sides that changed so lock-in pulses fire once
      if (!c.el.children.length) {
        c.el.innerHTML = sideHtml(m, m.a, "a") + `<div class="vs">VS</div>` + sideHtml(m, m.b, "b") + `<div class="outcome"></div>`;
        c.sideSig = { a: sigA, b: sigB, phase: s.phase };
      } else {
        if (c.sideSig.a !== sigA || c.sideSig.phase !== s.phase) c.el.children[0].outerHTML = sideHtml(m, m.a, "a");
        if (c.sideSig.b !== sigB || c.sideSig.phase !== s.phase) c.el.children[2].outerHTML = sideHtml(m, m.b, "b");
        c.sideSig = { a: sigA, b: sigB, phase: s.phase };
      }
      const o = c.el.querySelector(".outcome");
      o.className = "outcome " + (outcome ? outcome[0] : "");
      o.textContent = outcome ? outcome[1] : "";
    });
    if (s.sit_out) {
      const key = `${s.round}:bench:${s.sit_out}`;
      wanted.add(key);
      if (!cards.has(key)) {
        const el = document.createElement("article");
        el.className = "match bench";
        el.innerHTML = `${icon("bench")}<div><div class="pname">${esc(s.sit_out)}</div><div class="why">Sits out this round. Odd one out, back next round.</div></div>`;
        cards.set(key, { el, sig: "bench" });
        box.appendChild(el);
      }
    }
    for (const [key, c] of cards) {
      if (!wanted.has(key)) { c.el.remove(); cards.delete(key); }
    }
  }

  // --- leaderboard --------------------------------------------------------------------
  const rows = new Map();   // id -> tr

  function renderBoard() {
    const s = state;
    const tbody = $("lb");
    $("lb-empty").hidden = s.leaderboard.length > 0;
    document.querySelector(".lb").style.display = s.leaderboard.length ? "" : "none";

    // FLIP: remember where every row is
    const before = new Map();
    for (const [id, tr] of rows) before.set(id, tr.getBoundingClientRect().top);

    const seen = new Set();
    s.leaderboard.forEach((p, i) => {
      seen.add(p.id);
      let tr = rows.get(p.id);
      if (!tr) {
        tr = document.createElement("tr");
        rows.set(p.id, tr);
      }
      tr.className = p.state + (i === 0 && p.state !== "dropped" && p.points > 0 ? " top1" : "");
      const tag = p.state === "waiting" ? `<span class="tag">joins next round</span>`
        : p.state === "dropped" ? `<span class="tag">dropped — join again</span>` : "";
      tr.innerHTML =
        `<td class="r">${p.rank}</td>` +
        `<td><span class="pname">${esc(p.id)}</span>${tag}</td>` +
        `<td class="n pts">${p.points}</td>` +
        `<td class="n">${p.rounds_played}</td>` +
        `<td class="n">${p.rounds_played ? p.avg.toFixed(2) : "–"}</td>`;
      // Reorder in place
      if (tbody.children[i] !== tr) tbody.insertBefore(tr, tbody.children[i] || null);
    });
    for (const [id, tr] of rows) {
      if (!seen.has(id)) { tr.remove(); rows.delete(id); }
    }
    if (reduced) return;
    for (const [id, tr] of rows) {
      const old = before.get(id);
      if (old === undefined) continue;
      const dy = old - tr.getBoundingClientRect().top;
      if (Math.abs(dy) < 1) continue;
      tr.animate([{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }],
        { duration: 380, easing: "cubic-bezier(.2,.7,.2,1)" });
    }
  }

  // --- live log ------------------------------------------------------------------------
  let lastLine = null;   // {ts, text} of the last rendered line

  function lineEl(e) {
    const div = document.createElement("div");
    div.className = "ln " + e.kind;
    div.innerHTML = `<span class="t">${hhmmss(e.ts)}</span>  ${esc(e.text)}`;
    return div;
  }

  function renderLog() {
    const feed = state.feed;
    const box = $("log-lines");
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    let start = 0;
    if (lastLine) {
      const idx = feed.findIndex((e) => e.ts === lastLine.ts && e.text === lastLine.text);
      if (idx === -1) { box.innerHTML = ""; }      // feed was reset
      else start = idx + 1;
    }
    const frag = document.createDocumentFragment();
    for (let i = start; i < feed.length; i++) frag.appendChild(lineEl(feed[i]));
    box.appendChild(frag);
    while (box.children.length > 200) box.removeChild(box.firstChild);
    lastLine = feed.length ? feed[feed.length - 1] : null;
    if (atBottom || start === 0) box.scrollTop = box.scrollHeight;

    const mq = $("mqtt");
    mq.className = "mqtt " + (state.mqtt_connected ? "up" : "");
    mq.textContent = state.mqtt_connected ? "broker" : "broker down";
  }

  // --- glue ---------------------------------------------------------------------------------
  function render() {
    $("log-title").textContent = state.topic_prefix + "/#";
    $("join-topic").textContent = state.topic_prefix + "/<name>/join";
    renderHeader();
    renderMatches();
    renderBoard();
    renderLog();
  }

  function apply(snap) {
    clockOffset = snap.now - Date.now() / 1000;
    state = snap;
    render();
  }

  function connect() {
    const es = new EventSource("/events");
    es.addEventListener("state", (ev) => apply(JSON.parse(ev.data)));
    es.onerror = () => { /* EventSource reconnects by itself */ };
  }

  // Reset button: inline confirm, no browser dialog
  $("reset-btn").onclick = () => { $("reset-btn").hidden = true; $("reset-confirm").hidden = false; };
  $("reset-no").onclick = () => { $("reset-btn").hidden = false; $("reset-confirm").hidden = true; };
  $("reset-yes").onclick = async () => {
    $("reset-btn").hidden = false; $("reset-confirm").hidden = true;
    await fetch("/api/reset", { method: "POST" });
  };

  apply(state);
  requestAnimationFrame(tickClock);
  connect();
})();
