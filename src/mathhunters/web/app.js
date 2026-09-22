/* =========================================================================
   Math Demon Hunters — front end.
   Talks to the local Python API; all rendering and effects are done here.
   ========================================================================= */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    rules: {
      mastery_target: 3, correct_points: 1, wrong_penalty: 2,
      max_operand: 999, max_pool_size: 40,
      timer_default_seconds: 10, timer_min_seconds: 3, timer_max_seconds: 120,
    },
    assets: {},
    packs: [],
    pack: null, // name of the selected image pack
    history: [],
    series: null,
    vary: "subtrahend", // which side of the subtraction the range sweeps
    timerEnabled: localStorage.getItem("mdh-timer") === "on",
    timerSeconds: parseInt(localStorage.getItem("mdh-timer-seconds"), 10) || 10,
    askedAt: 0,
    busy: false,
    sound: localStorage.getItem("mdh-sound") !== "off",
  };

  /* ----------------------------- API ----------------------------------- */

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const data = await res.json().catch(() => ({ error: "The hunt server sent something unreadable." }));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  /* ----------------------------- sound ---------------------------------- */

  let audioCtx = null;
  const sampleCache = {};

  function ctx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  // Short synthesised blips so the app needs no audio files to feel alive.
  function tone(freq, duration, type = "triangle", gain = 0.16, delay = 0) {
    if (!state.sound) return;
    try {
      const ac = ctx();
      const osc = ac.createOscillator();
      const amp = ac.createGain();
      const t0 = ac.currentTime + delay;
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t0);
      amp.gain.setValueAtTime(0.0001, t0);
      amp.gain.exponentialRampToValueAtTime(gain, t0 + 0.015);
      amp.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
      osc.connect(amp).connect(ac.destination);
      osc.start(t0);
      osc.stop(t0 + duration + 0.02);
    } catch (_) { /* audio is a nicety, never a blocker */ }
  }

  function sfx(name) {
    if (!state.sound) return;
    const url = state.assets[`sfx-${name}`];
    if (url) {
      const el = sampleCache[url] || (sampleCache[url] = new Audio(url));
      el.currentTime = 0;
      el.play().catch(() => {});
      return;
    }
    if (name === "correct") { tone(660, 0.1, "triangle", 0.16); tone(990, 0.16, "triangle", 0.13, 0.07); }
    else if (name === "wrong") { tone(190, 0.2, "sawtooth", 0.13); tone(120, 0.3, "sawtooth", 0.1, 0.08); }
    else if (name === "timeout") { tone(300, 0.18, "square", 0.12); tone(150, 0.4, "sawtooth", 0.12, 0.14); }
    else if (name === "tick") { tone(880, 0.05, "square", 0.06); }
    else if (name === "seal") { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.24, "triangle", 0.14, i * 0.07)); }
    else if (name === "victory") { [523, 659, 784, 1047, 1319, 1568].forEach((f, i) => tone(f, 0.45, "triangle", 0.16, i * 0.12)); }
    else if (name === "key") { tone(420, 0.04, "square", 0.05); }
  }

  /* -------------------------- ambient embers ---------------------------- */

  function startEmbers() {
    const canvas = $("embers");
    const g = canvas.getContext("2d");
    let w = 0, h = 0, sparks = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.width = Math.floor(innerWidth * dpr);
      h = canvas.height = Math.floor(innerHeight * dpr);
      canvas.style.width = innerWidth + "px";
      canvas.style.height = innerHeight + "px";
      const count = Math.round((innerWidth * innerHeight) / 26000);
      sparks = Array.from({ length: Math.max(28, Math.min(110, count)) }, spawn);
    };

    function spawn() {
      const hues = ["rgba(255,203,61,", "rgba(34,229,255,", "rgba(255,46,151,", "rgba(139,59,255,"];
      return {
        x: Math.random() * w, y: Math.random() * h,
        r: Math.random() * 2.4 + 0.6,
        vy: -(Math.random() * 0.35 + 0.1),
        vx: (Math.random() - 0.5) * 0.24,
        a: Math.random() * 0.55 + 0.2,
        tw: Math.random() * Math.PI * 2,
        c: hues[(Math.random() * hues.length) | 0],
      };
    }

    function frame() {
      g.clearRect(0, 0, w, h);
      for (const s of sparks) {
        s.x += s.vx; s.y += s.vy; s.tw += 0.03;
        if (s.y < -10) { s.y = h + 10; s.x = Math.random() * w; }
        if (s.x < -10) s.x = w + 10; else if (s.x > w + 10) s.x = -10;
        const alpha = s.a * (0.6 + 0.4 * Math.sin(s.tw));
        g.beginPath();
        g.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        g.fillStyle = s.c + alpha.toFixed(3) + ")";
        g.shadowBlur = 12; g.shadowColor = s.c + "0.9)";
        g.fill();
      }
      requestAnimationFrame(frame);
    }

    addEventListener("resize", resize);
    resize();
    frame();
  }

  /* --------------------------- screen routing --------------------------- */

  function show(id) {
    for (const el of document.querySelectorAll(".screen")) el.classList.remove("screen--active");
    $(id).classList.add("screen--active");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ------------------------------- home --------------------------------- */

  const inputs = { fixed: $("input-fixed"), t1: $("input-t1"), t2: $("input-t2") };

  function readForge() {
    const num = (el) => {
      const v = parseInt(el.value, 10);
      return Number.isFinite(v) ? v : 0;
    };
    return {
      fixed: num(inputs.fixed),
      t1: num(inputs.t1),
      t2: num(inputs.t2),
      vary: state.vary,
      timer_enabled: state.timerEnabled,
      timer_seconds: state.timerSeconds,
    };
  }

  function validateForge({ fixed, t1, t2 }) {
    const max = state.rules.max_operand;
    if ([fixed, t1, t2].some((n) => n < 0 || n > max)) return `Numbers must be between 0 and ${max}.`;
    if (t1 > t2) return "The range start has to be smaller than the range end.";
    if (t2 - t1 + 1 > state.rules.max_pool_size) return `That range makes ${t2 - t1 + 1} problems — keep it to ${state.rules.max_pool_size} or fewer.`;
    return null;
  }

  /** The two operands of one problem, given the forge values. */
  function operands(values, v) {
    return values.vary === "minuend"
      ? { minuend: v, subtrahend: values.fixed }
      : { minuend: values.fixed, subtrahend: v };
  }

  function seriesLabel(s) {
    const span = `[${s.t1}…${s.t2}]`;
    return s.vary === "minuend" ? `${span} − ${s.fixed}` : `${s.fixed} − ${span}`;
  }

  function setVary(vary) {
    state.vary = vary;
    for (const btn of document.querySelectorAll(".mode")) {
      const on = btn.dataset.vary === vary;
      btn.classList.toggle("mode--on", on);
      btn.setAttribute("aria-checked", String(on));
    }
    $("fixed-label").innerHTML = vary === "minuend"
      ? "Take away <b>B</b> (fixed)"
      : "Start number <b>A</b> (fixed)";
    renderPreview();
  }

  function renderPreview() {
    const values = readForge();
    const err = validateForge(values);
    const chips = $("preview-chips");
    const error = $("forge-error");
    chips.innerHTML = "";

    if (err) {
      error.textContent = err;
      error.hidden = false;
      $("preview-count").textContent = "—";
      $("start-btn").disabled = true;
      $("start-btn").style.opacity = ".45";
      return;
    }
    error.hidden = true;
    $("start-btn").disabled = false;
    $("start-btn").style.opacity = "1";

    const count = values.t2 - values.t1 + 1;
    $("preview-count").textContent = `${count} demon${count === 1 ? "" : "s"} in this hunt`;
    for (let v = values.t1; v <= values.t2; v++) {
      const { minuend, subtrahend } = operands(values, v);
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${minuend} − ${subtrahend}`;
      chip.style.animationDelay = `${(v - values.t1) * 18}ms`;
      chips.appendChild(chip);
    }
  }

  /* --------------------------- image packs ------------------------------ */

  function packImages() {
    const pack = state.packs.find((p) => p.name === state.pack);
    return pack ? pack.images : [];
  }

  /**
   * Each problem is bound to one picture, by its position in the pool, so
   * `10 − 7` always shows the same image. Packs smaller than the pool repeat.
   */
  function imageFor(v) {
    const images = packImages();
    if (!images.length || !state.series) return null;
    const index = state.series.problems.findIndex((p) => p.v === v);
    return images[(index < 0 ? 0 : index) % images.length];
  }

  function preloadPack() {
    for (const url of packImages().slice(0, 60)) new Image().src = url;
  }

  function setPack(name) {
    state.pack = name;
    if (name) localStorage.setItem("mdh-pack", name);
    else localStorage.removeItem("mdh-pack");
    for (const chip of document.querySelectorAll(".pack-chip")) {
      chip.classList.toggle("pack-chip--on", (chip.dataset.pack || "") === (name || ""));
    }
    preloadPack();
  }

  function renderPacks() {
    const row = $("packs-row");
    const list = $("packs-list");
    row.hidden = state.packs.length === 0;
    list.innerHTML = "";
    if (!state.packs.length) return;

    const add = (name, label, thumb, count) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "pack-chip";
      chip.dataset.pack = name || "";
      chip.innerHTML = thumb
        ? `<img src="${thumb}" alt="" loading="lazy" /><span>${label}</span><small>${count}</small>`
        : `<span class="pack-chip__dot">👺</span><span>${label}</span>`;
      chip.addEventListener("click", () => { setPack(name); sfx("key"); });
      list.appendChild(chip);
    };

    add(null, "No pictures", null, 0);
    for (const pack of state.packs) add(pack.name, pack.name, pack.images[0], pack.count);
    setPack(state.pack);
  }

  function renderHistory() {
    const wrap = $("history");
    wrap.innerHTML = "";
    $("history-empty").hidden = state.history.length > 0;

    for (const s of state.history) {
      const pct = s.points_possible ? Math.round((s.points_earned / s.points_possible) * 100) : 0;
      const card = document.createElement("div");
      card.className = "hunt-card" + (s.is_mastered ? " hunt-card--done" : "");
      const circumference = 2 * Math.PI * 24;
      card.innerHTML = `
        ${s.is_mastered ? '<span class="hunt-card__crown">👑</span>' : ""}
        <div class="hunt-card__top">
          <div class="hunt-card__ring">
            <svg viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="24" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="5"/>
              <circle cx="28" cy="28" r="24" fill="none" stroke="${s.is_mastered ? "#ffcb3d" : "#22e5ff"}"
                      stroke-width="5" stroke-linecap="round"
                      stroke-dasharray="${circumference}"
                      stroke-dashoffset="${circumference * (1 - pct / 100)}"/>
            </svg>
            <span class="hunt-card__pct">${pct}%</span>
          </div>
          <div>
            <p class="hunt-card__name">${seriesLabel(s)}</p>
            <p class="hunt-card__meta">${s.mastered_count}/${s.pool_size} sealed${s.completions ? ` · cleared ×${s.completions}` : ""}</p>
            <p class="hunt-card__meta">best combo ${s.best_streak}</p>
          </div>
        </div>
        <div class="hunt-card__actions">
          <button class="btn btn--ghost btn--small" data-act="play">${s.is_mastered ? "REPLAY" : "RESUME"}</button>
          ${!s.is_mastered && s.points_earned > 0 ? '<button class="btn btn--ghost btn--small" data-act="restart">RESET</button>' : ""}
          <button class="btn btn--danger btn--small" data-act="delete" aria-label="Delete hunt">✕</button>
        </div>`;

      card.querySelector('[data-act="play"]').addEventListener("click", () => startSeries(s, false));
      const resetBtn = card.querySelector('[data-act="restart"]');
      if (resetBtn) resetBtn.addEventListener("click", () => startSeries(s, true));
      card.querySelector('[data-act="delete"]').addEventListener("click", async () => {
        if (!confirm(`Delete the hunt ${seriesLabel(s)}? Its progress is lost.`)) return;
        const data = await api(`/api/series/${s.id}`, { method: "DELETE" });
        state.history = data.series;
        renderHistory();
      });
      wrap.appendChild(card);
    }
  }

  /* ------------------------------- play --------------------------------- */

  async function startSeries(values, restart) {
    try {
      const data = await api("/api/series", { method: "POST", body: { ...values, restart } });
      state.series = data;
      inputs.fixed.value = data.fixed; inputs.t1.value = data.t1; inputs.t2.value = data.t2;
      setVary(data.vary);
      preloadPack();
      show("screen-play");
      renderPlay();
      focusAnswer();
      sfx("key");
    } catch (err) {
      const error = $("forge-error");
      error.textContent = err.message;
      error.hidden = false;
    }
  }

  function renderPlay() {
    const s = state.series;
    $("play-label").textContent = seriesLabel(s);

    const pct = s.points_possible ? (s.points_earned / s.points_possible) * 100 : 0;
    $("seal-fill").style.width = `${pct}%`;
    $("seal-text").textContent = `${s.mastered_count} / ${s.pool_size} sealed`;

    $("combo-n").textContent = s.streak;
    $("combo").dataset.level = s.streak >= 9 ? "3" : s.streak >= 5 ? "2" : s.streak >= 2 ? "1" : "0";

    renderCracks(s);
    renderBoard(s);

    if (s.question) {
      $("eq-minuend").textContent = s.question.minuend;
      $("eq-subtrahend").textContent = s.question.subtrahend;
      renderPips(s.question.points);
      renderPackCard(s.question);
      $("answer").value = "";
      state.askedAt = performance.now();
      startClock();
    } else {
      stopClock();
    }
  }

  /** Swap in this problem's picture, or fall back to the drawn demon. */
  function renderPackCard(question) {
    const card = $("pack-card");
    const url = imageFor(question.v);
    if (!url) {
      card.hidden = true;
      $("demon").style.display = state.assets.demon ? "none" : "";
      $("demon-art").hidden = !state.assets.demon;
      return;
    }
    card.hidden = false;
    $("demon").style.display = "none";
    $("demon-art").hidden = true;
    const img = $("pack-img");
    if (img.src !== new URL(url, location.href).href) img.src = url;
    img.alt = `Picture for ${question.text}`;
    card.classList.toggle("pack-card--sealed", question.points >= state.rules.mastery_target);
  }

  /** Whichever artwork is on screen — the pack picture or the drawn demon. */
  function visualTarget() {
    return $("pack-card").hidden ? $("demon") : $("pack-card");
  }

  /* ------------------------------ clock --------------------------------- */

  let clockFrame = null;
  let clockEndsAt = 0;

  function stopClock() {
    cancelAnimationFrame(clockFrame);
    clockFrame = null;
    $("clock").hidden = true;
    $("clock").classList.remove("clock--warn");
  }

  function startClock() {
    stopClock();
    const s = state.series;
    if (!s || !s.timer_enabled || !s.question) return;

    const total = s.timer_seconds * 1000;
    clockEndsAt = performance.now() + total;
    const clock = $("clock");
    const fill = $("clock-fill");
    const num = $("clock-num");
    clock.hidden = false;

    let lastWholeSecond = -1;
    const tick = (now) => {
      const left = Math.max(0, clockEndsAt - now);
      const ratio = left / total;
      fill.style.transform = `scaleX(${ratio})`;

      const seconds = Math.ceil(left / 1000);
      if (seconds !== lastWholeSecond) {
        lastWholeSecond = seconds;
        num.textContent = seconds;
        // Last three seconds: colour shift plus a tick, so it is felt not just seen.
        if (seconds <= 3 && seconds > 0) sfx("tick");
      }
      clock.classList.toggle("clock--warn", left <= 3000);

      if (left <= 0) {
        clockFrame = null;
        submitTimeout();
        return;
      }
      clockFrame = requestAnimationFrame(tick);
    };
    clockFrame = requestAnimationFrame(tick);
  }

  function renderPips(points) {
    const wrap = $("pips");
    const target = state.rules.mastery_target;
    if (wrap.children.length !== target) {
      wrap.innerHTML = "";
      for (let i = 0; i < target; i++) {
        const pip = document.createElement("span");
        pip.className = "pip";
        wrap.appendChild(pip);
      }
    }
    [...wrap.children].forEach((pip, i) => pip.classList.toggle("filled", i < points));
  }

  function renderCracks(s) {
    const ratio = s.pool_size ? s.mastered_count / s.pool_size : 0;
    const cracks = document.querySelectorAll("#demon .demon__cracks path");
    const lit = Math.round(ratio * cracks.length);
    cracks.forEach((path, i) => path.classList.toggle("on", i < lit));
  }

  function renderBoard(s) {
    const board = $("board");
    board.innerHTML = "";
    const activeV = s.question ? s.question.v : null;
    for (const p of s.problems) {
      const tile = document.createElement("div");
      tile.className = "tile" + (p.mastered ? " tile--done" : "") + (p.v === activeV ? " tile--active" : "");
      const pips = Array.from({ length: state.rules.mastery_target },
        (_, i) => `<span class="tile__pip${i < p.points ? " on" : ""}"></span>`).join("");
      tile.innerHTML = `<div class="tile__eq">${p.text}</div><div class="tile__pips">${pips}</div>`;
      board.appendChild(tile);
    }
  }

  function flash(message, kind) {
    const wrap = $("flash");
    wrap.innerHTML = `<span class="flash__msg flash__msg--${kind}">${message}</span>`;
  }

  async function submitAnswer() {
    if (state.busy || !state.series || !state.series.question) return;
    const raw = $("answer").value.trim().replace("−", "-");
    if (!/^-?\d+$/.test(raw)) {
      // Nothing typed yet (or just a stray minus) — nudge instead of scoring it.
      const equation = $("answer").closest(".equation");
      equation.classList.add("shake");
      setTimeout(() => equation.classList.remove("shake"), 450);
      return;
    }

    send({ answer: parseInt(raw, 10) });
  }

  function submitTimeout() {
    if (state.busy || !state.series || !state.series.question) return;
    send({ timed_out: true });
  }

  async function send(payload) {
    state.busy = true;
    stopClock();
    const elapsed = Math.round(performance.now() - state.askedAt);
    const seriesId = state.series.id;

    try {
      const data = await api(`/api/series/${seriesId}/answer`, {
        method: "POST",
        body: { ...payload, elapsed_ms: elapsed },
      });
      state.series = data;
      playFeedback(data.result);

      if (data.result.series_mastered) {
        setTimeout(() => celebrate(data), 700);
      } else {
        // Hold the feedback on screen before moving on; longer for a miss, so
        // there is time to read the correct answer.
        const pause = data.result.correct ? 620 : 1500;
        setTimeout(() => { renderPlay(); focusAnswer(); state.busy = false; }, pause);
        return;
      }
    } catch (err) {
      flash(err.message, "bad");
    }
    state.busy = false;
  }

  function playFeedback(result) {
    const equation = $("answer").closest(".equation");
    const demon = visualTarget();

    if (result.correct) {
      equation.classList.add("strike");
      demon.classList.add("hurt");
      setTimeout(() => { equation.classList.remove("strike"); demon.classList.remove("hurt"); }, 480);

      const pip = $("pips").children[Math.max(0, result.points - 1)];
      if (pip) { pip.classList.add("filled", "pop"); setTimeout(() => pip.classList.remove("pop"), 520); }

      if (result.problem_mastered) {
        flash("⟡ DEMON SEALED ⟡", "seal");
        sfx("seal");
        burstAt(demon, 34);
        $("pack-card").classList.add("pack-card--sealed");
      } else {
        const praise = result.slow
          ? ["GOT IT — now faster!", "Correct! Speed it up.", "Nice — quicker next time."]
          : ["STRIKE! +1", "CLEAN HIT! +1", "NICE! +1", "SHARP! +1", "BOOM! +1"];
        flash(praise[(Math.random() * praise.length) | 0], "good");
        sfx("correct");
        burstAt(demon, 14);
      }
    } else {
      equation.classList.add("shake");
      demon.classList.add("rage");
      setTimeout(() => { equation.classList.remove("shake"); demon.classList.remove("rage"); }, 520);
      renderPips(result.points);
      const lost = Math.abs(result.delta);
      const truth = `${result.text} = ${result.expected}`;
      const penalty = lost ? `−${lost}` : "0";
      let message = `${truth}  (${penalty})`;
      if (result.timed_out) message = `⏳ TIME'S UP! ${truth}`;
      else if (result.seal_broken) message = `THE SEAL CRACKED! ${truth}`;
      flash(message, "bad");
      sfx(result.timed_out ? "timeout" : "wrong");
    }
  }

  function focusAnswer() {
    const el = $("answer");
    el.value = "";
    el.focus({ preventScroll: true });
    state.askedAt = performance.now();
  }

  /* ---------------------------- effects --------------------------------- */

  function burstAt(el, count) {
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const colors = ["#ffcb3d", "#22e5ff", "#ff2e97", "#8b3bff", "#fdf3ff"];
    for (let i = 0; i < count; i++) {
      const dot = document.createElement("span");
      const angle = Math.random() * Math.PI * 2;
      const dist = 60 + Math.random() * 130;
      const size = 4 + Math.random() * 7;
      Object.assign(dot.style, {
        position: "fixed", left: `${cx}px`, top: `${cy}px`, zIndex: 70,
        width: `${size}px`, height: `${size}px`, borderRadius: "50%",
        background: colors[(Math.random() * colors.length) | 0],
        boxShadow: "0 0 12px currentColor", pointerEvents: "none",
      });
      document.body.appendChild(dot);
      const dx = Math.cos(angle) * dist;
      const dy = Math.sin(angle) * dist;
      dot.animate(
        [
          { transform: "translate(-50%, -50%) scale(1)", opacity: 1 },
          { transform: `translate(calc(-50% + ${dx.toFixed(1)}px), calc(-50% + ${dy.toFixed(1)}px)) scale(0)`, opacity: 0 },
        ],
        { duration: 600 + Math.random() * 420, easing: "cubic-bezier(.2,.8,.3,1)" }
      ).onfinish = () => dot.remove();
    }
  }

  let confettiTimer = null;
  /** Runs until returnHome cancels it — the celebration has no time limit. */
  function runConfetti() {
    const canvas = $("confetti");
    const g = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr;
    canvas.style.width = innerWidth + "px"; canvas.style.height = innerHeight + "px";

    const colors = ["#ffcb3d", "#22e5ff", "#ff2e97", "#8b3bff", "#fdf3ff", "#ff6b4a"];
    const bits = Array.from({ length: 190 }, () => ({
      x: Math.random() * canvas.width,
      y: -Math.random() * canvas.height,
      w: (5 + Math.random() * 9) * dpr,
      h: (9 + Math.random() * 16) * dpr,
      vy: (1.6 + Math.random() * 3.4) * dpr,
      vx: (Math.random() - 0.5) * 2.2 * dpr,
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.22,
      c: colors[(Math.random() * colors.length) | 0],
      talisman: Math.random() < 0.3,
    }));

    cancelAnimationFrame(confettiTimer);

    (function frame() {
      g.clearRect(0, 0, canvas.width, canvas.height);
      for (const b of bits) {
        b.y += b.vy; b.x += b.vx; b.rot += b.vr;
        if (b.y > canvas.height + 40) { b.y = -30; b.x = Math.random() * canvas.width; }
        g.save();
        g.translate(b.x, b.y);
        g.rotate(b.rot);
        g.fillStyle = b.talisman ? "#ffcb3d" : b.c;
        g.shadowBlur = 14; g.shadowColor = b.c;
        g.fillRect(-b.w / 2, -b.h / 2, b.w, b.h);
        if (b.talisman) {
          g.fillStyle = "rgba(180,20,60,.9)";
          g.fillRect(-b.w / 3, -b.h / 5, (b.w * 2) / 3, 1.6 * dpr);
          g.fillRect(-b.w / 3, b.h / 8, (b.w * 2) / 3, 1.6 * dpr);
        }
        g.restore();
      }
      confettiTimer = requestAnimationFrame(frame);
    })();
  }

  /* ---------------------------- celebration ----------------------------- */

  function celebrate(s) {
    stopClock();
    const accuracy = s.total_asked ? Math.round((s.total_correct / s.total_asked) * 100) : 100;
    $("victory-series").textContent = seriesLabel(s);

    // Every picture from this hunt, now sealed.
    const gallery = $("victory-gallery");
    const used = [...new Set(s.problems.map((p) => imageFor(p.v)).filter(Boolean))];
    gallery.hidden = used.length === 0;
    gallery.innerHTML = used
      .map((url, i) => `<img src="${url}" alt="" style="animation-delay:${i * 60}ms" />`)
      .join("");
    $("victory-stats").innerHTML = `
      <div class="stat"><span class="stat__n">${s.pool_size}</span><span class="stat__l">demons sealed</span></div>
      <div class="stat"><span class="stat__n">${accuracy}%</span><span class="stat__l">accuracy</span></div>
      <div class="stat"><span class="stat__n">${s.best_streak}</span><span class="stat__l">best combo</span></div>
      <div class="stat"><span class="stat__n">${s.completions}</span><span class="stat__l">times cleared</span></div>`;

    $("victory").classList.add("victory--on");
    $("victory").setAttribute("aria-hidden", "false");
    runConfetti();
    sfx("victory");
    setTimeout(() => burstAt($("victory-btn"), 40), 500);
    setTimeout(() => burstAt($("victory-stats"), 40), 1100);

    // The celebration stays up until it is dismissed by hand.
    setTimeout(() => $("victory-btn").focus({ preventScroll: true }), 900);
  }

  async function returnHome() {
    cancelAnimationFrame(confettiTimer);
    stopClock();
    $("victory").classList.remove("victory--on");
    $("victory").setAttribute("aria-hidden", "true");
    state.busy = false;
    state.series = null;
    await refreshHistory();
    show("screen-home");
  }

  async function refreshHistory() {
    const data = await api("/api/bootstrap");
    state.rules = data.rules;
    state.assets = data.assets;
    state.packs = data.packs || [];
    state.history = data.series;

    // --images is an explicit choice for this launch, so it wins; otherwise fall
    // back to whatever pack was last picked in the app.
    const remembered = localStorage.getItem("mdh-pack");
    const names = state.packs.map((p) => p.name);
    state.pack = data.pack || (names.includes(remembered) ? remembered : null);

    $("rule-target").textContent = state.rules.mastery_target;
    applyAssets();
    renderPacks();
    renderHistory();
  }

  /* ------------------------- custom artwork ----------------------------- */

  function applyAssets() {
    const bind = (id, slot) => {
      const el = $(id);
      const url = state.assets[slot];
      if (url) { el.src = url; el.hidden = false; } else { el.hidden = true; }
    };
    bind("logo-art", "logo");
    bind("victory-art", "victory");

    const demonArt = $("demon-art");
    if (state.assets.demon) {
      demonArt.src = state.assets.demon; demonArt.hidden = false;
      $("demon").style.display = "none";
    } else {
      demonArt.hidden = true;
      $("demon").style.display = "";
    }

    if (state.assets.backdrop) {
      document.querySelector(".sky__wash").style.backgroundImage =
        `linear-gradient(rgba(10,3,32,.62), rgba(7,2,26,.86)), url("${state.assets.backdrop}")`;
      document.querySelector(".sky__wash").style.backgroundSize = "cover";
      document.querySelector(".sky__wash").style.backgroundPosition = "center";
    }

    if (state.assets.music && state.sound) {
      const music = sampleCache.music || (sampleCache.music = new Audio(state.assets.music));
      music.loop = true; music.volume = 0.25;
      // Browsers block autoplay until a gesture; retry on the first click.
      const tryPlay = () => music.play().catch(() => {});
      tryPlay();
      document.addEventListener("click", tryPlay, { once: true });
    }
  }

  /* ------------------------------ wiring -------------------------------- */

  function wire() {
    // Orientation: which side of the subtraction the range sweeps.
    for (const btn of document.querySelectorAll(".mode")) {
      btn.addEventListener("click", () => { setVary(btn.dataset.vary); sfx("key"); });
    }

    // Countdown option
    const timerToggle = $("timer-toggle");
    timerToggle.checked = state.timerEnabled;
    $("input-timer").value = state.timerSeconds;
    $("timer-seconds-row").hidden = !state.timerEnabled;
    timerToggle.addEventListener("change", () => {
      state.timerEnabled = timerToggle.checked;
      localStorage.setItem("mdh-timer", state.timerEnabled ? "on" : "off");
      $("timer-seconds-row").hidden = !state.timerEnabled;
      sfx("key");
    });

    // Steppers — the timer stepper clamps to its own range, the others to operands.
    for (const stepper of document.querySelectorAll(".stepper")) {
      const input = stepper.querySelector(".stepper__input");
      const isTimer = stepper.dataset.field === "timer";
      const low = isTimer ? state.rules.timer_min_seconds : 0;
      const high = () => (isTimer ? state.rules.timer_max_seconds : state.rules.max_operand);

      const commit = (value) => {
        if (isTimer) {
          state.timerSeconds = value;
          localStorage.setItem("mdh-timer-seconds", String(value));
        } else {
          renderPreview();
        }
      };

      for (const btn of stepper.querySelectorAll(".stepper__btn")) {
        btn.addEventListener("click", () => {
          const step = parseInt(btn.dataset.step, 10);
          const next = Math.max(low, Math.min(high(), (parseInt(input.value, 10) || 0) + step));
          input.value = next;
          commit(next);
          sfx("key");
        });
      }
      input.addEventListener("input", () => {
        input.value = input.value.replace(/[^\d]/g, "").slice(0, 3);
        if (isTimer) commit(Math.max(low, Math.min(high(), parseInt(input.value, 10) || low)));
        else renderPreview();
      });
      // Snap a half-typed timer value back into range when the field is left.
      if (isTimer) {
        input.addEventListener("blur", () => {
          const value = Math.max(low, Math.min(high(), parseInt(input.value, 10) || state.rules.timer_default_seconds));
          input.value = value;
          commit(value);
        });
      }
    }

    $("start-btn").addEventListener("click", () => startSeries(readForge(), false));
    $("back-btn").addEventListener("click", returnHome);
    $("victory-btn").addEventListener("click", returnHome);

    // Keypad
    $("keypad").addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-key]");
      if (!btn) return;
      pressKey(btn.dataset.key);
      btn.classList.add("hit");
      setTimeout(() => btn.classList.remove("hit"), 120);
    });

    // Physical keyboard
    document.addEventListener("keydown", (event) => {
      if ($("victory").classList.contains("victory--on")) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); returnHome(); }
        return;
      }
      if (!$("screen-play").classList.contains("screen--active")) {
        if (event.key === "Enter" && !$("start-btn").disabled) startSeries(readForge(), false);
        return;
      }
      if (/^\d$/.test(event.key)) { event.preventDefault(); pressKey(event.key); }
      else if (event.key === "Backspace") { event.preventDefault(); pressKey("del"); }
      else if (event.key === "Enter") { event.preventDefault(); pressKey("enter"); }
      else if (event.key === "-") { event.preventDefault(); pressKey("-"); }
      else if (event.key === "Escape") returnHome();
    });

    // Sound
    const toggle = $("sound-toggle");
    toggle.setAttribute("aria-pressed", String(state.sound));
    toggle.addEventListener("click", () => {
      state.sound = !state.sound;
      localStorage.setItem("mdh-sound", state.sound ? "on" : "off");
      toggle.setAttribute("aria-pressed", String(state.sound));
      if (state.sound) sfx("key");
    });

    // Tapping the equation returns focus to the answer box.
    $("answer").addEventListener("focus", () => $("answer").setSelectionRange(99, 99));
  }

  function pressKey(key) {
    const el = $("answer");
    if (key === "enter") { submitAnswer(); return; }
    sfx("key");
    if (key === "del") { el.value = el.value.slice(0, -1); return; }
    if (key === "-") {
      el.value = el.value.startsWith("-") ? el.value.slice(1) : "-" + el.value;
      return;
    }
    if (el.value.replace("-", "").length >= 3) return;
    el.value += key;
  }

  /* ------------------------------- boot --------------------------------- */

  async function boot() {
    wire();
    startEmbers();
    try {
      await refreshHistory();
    } catch (err) {
      $("forge-error").textContent = `Could not reach the hunt server: ${err.message}`;
      $("forge-error").hidden = false;
    }
    setVary(state.vary);
  }

  boot();
})();
