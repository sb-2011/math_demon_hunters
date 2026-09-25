/* =========================================================================
   Math Demon Hunters — strategy pictures.

   A strategy shows how one problem can be broken into smaller ones. Each
   strategy answers three things:

     applies(question) — is this a problem it can help with?
     plan(question)    — which smaller problems does it break into?
     picture(values)   — what does that look like, given what has been
                         filled in so far?

   The app supplies everything around them: the boxes to type the parts into,
   the checking, the running sum, and the reveal when an answer is missed.
   Adding a strategy means adding one object to STRATEGIES — the first one
   that applies is the one shown, so put the more specific ones first.
   ========================================================================= */
(() => {
  "use strict";

  const TEN = 10;
  const MINUS = "−";

  /* ------------------------- bridge through ten ------------------------- */

  /**
   * A teen number minus a single digit: the jump from one to the other always
   * crosses 10, so 10 can be a stop along the way.  Both halves of the trip
   * are then small enough to see at a glance:
   *
   *     13 − 5  =  (10 − 5) + (13 − 10)  =  5 + 3  =  8
   *
   * Drawn on a number line, the two smaller problems are simply the two hops
   * that make up the distance between 5 and 13.
   */
  const bridgeThroughTen = {
    id: "bridge-ten",
    title: `BRIDGE THROUGH ${TEN}`,

    applies: (q) =>
      q.minuend >= 11 && q.minuend <= 20 && q.subtrahend >= 1 && q.subtrahend <= 9,

    plan(q) {
      const lo = q.subtrahend;
      const hi = q.minuend;
      const steps = [
        { text: `${TEN} ${MINUS} ${lo}`, expected: TEN - lo, tint: "cyan", from: lo, to: TEN },
        { text: `${hi} ${MINUS} ${TEN}`, expected: hi - TEN, tint: "magenta", from: TEN, to: hi },
      ];
      return {
        id: this.id,
        title: this.title,
        caption: `${hi} ${MINUS} ${lo} = (${TEN} ${MINUS} ${lo}) + (${hi} ${MINUS} ${TEN})`,
        steps,
        join: "+",
        total: hi - lo,
        prompt: "Fill in both hops, then add them — that is your answer.",
        picture: (values, total) => numberLine(lo, hi, steps, values, total),
        describe: (values) => describeLine(lo, hi, values),
      };
    },
  };

  /* ------------------------- the number line ---------------------------- */

  const W = 640;
  const H = 232;
  const PAD = 48;
  const BASE = 120; // the line the hops jump from
  const SPAN_Y = 184; // the "whole jump" bracket underneath

  const filled = (value) => typeof value === "number" && Number.isFinite(value);

  /** Draw the two hops over a line running from ``lo`` to ``hi``. */
  function numberLine(lo, hi, steps, values, total) {
    const x = (v) => PAD + ((v - lo) / (hi - lo)) * (W - 2 * PAD);
    const major = new Set([lo, TEN, hi]);

    const ticks = [];
    for (let v = lo; v <= hi; v++) {
      const big = major.has(v);
      ticks.push(
        `<line class="nl__tick${big ? " nl__tick--big" : ""}" x1="${x(v)}" y1="${BASE - (big ? 10 : 6)}" x2="${x(v)}" y2="${BASE + (big ? 12 : 6)}" />`
      );
    }

    const marks = [...major].map((v) => {
      const tint = v === TEN ? "gold" : v === lo ? "cyan" : "magenta";
      return `<circle class="nl__dot nl__dot--${tint}" cx="${x(v)}" cy="${BASE}" r="7" />
              <text class="nl__mark nl__mark--${tint}" x="${x(v)}" y="${BASE + 40}" text-anchor="middle">${v}</text>`;
    });

    const hops = steps.map((step, i) => {
      const x1 = x(step.from);
      const x2 = x(step.to);
      // The control points sit straight above the ends, so the hop lands
      // vertically on its stop — and the apex is exactly `rise` above the line.
      const rise = Math.max(38, Math.min(78, (x2 - x1) * 0.55));
      const lift = rise / 0.75;
      const done = filled(values[i]);
      const apex = BASE - rise;
      return `
        <g class="nl__hop nl__hop--${step.tint}${done ? " is-done" : ""}">
          <path class="nl__arc" d="M${x1} ${BASE} C${x1} ${BASE - lift} ${x2} ${BASE - lift} ${x2} ${BASE}" />
          <path class="nl__tip" d="M${x2 - 8} ${BASE - 17} L${x2 + 8} ${BASE - 17} L${x2} ${BASE - 2} Z" />
          ${chip((x1 + x2) / 2, apex, done ? values[i] : "?", step.tint)}
        </g>`;
    });

    // The whole distance from one number to the other: that is the answer.
    const whole = `
      <g class="nl__whole${filled(total) ? " is-done" : ""}">
        <path class="nl__span" d="M${x(lo)} ${BASE + 52} L${x(lo)} ${SPAN_Y} L${x(hi)} ${SPAN_Y} L${x(hi)} ${BASE + 52}" />
        ${chip((x(lo) + x(hi)) / 2, SPAN_Y, filled(total) ? total : "?", "gold", "whole")}
        <text class="nl__caption" x="${W / 2}" y="${SPAN_Y + 40}" text-anchor="middle">THE WHOLE JUMP</text>
      </g>`;

    return `
      <svg class="nl" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(describeLine(lo, hi, values))}">
        <line class="nl__line" x1="${PAD - 22}" y1="${BASE}" x2="${W - PAD + 22}" y2="${BASE}" />
        ${ticks.join("")}
        ${hops.join("")}
        ${marks.join("")}
        ${whole}
      </svg>`;
  }

  /** The same picture, in words, for anyone reading with a screen reader. */
  function describeLine(lo, hi, values) {
    const hop = (value) => (filled(value) ? `, which is ${value}` : "");
    return (
      `Number line from ${lo} to ${hi}. ` +
      `First hop, ${lo} up to ${TEN}: that is ${TEN} minus ${lo}${hop(values[0])}. ` +
      `Second hop, ${TEN} up to ${hi}: that is ${hi} minus ${TEN}${hop(values[1])}. ` +
      `The two hops added together cover the whole distance, which is the answer.`
    );
  }

  /** A rounded label sitting on a hop, holding its value once it is known. */
  function chip(cx, cy, value, tint, extra = "") {
    const wide = String(value).length > 1;
    const half = wide ? 32 : 25;
    return `
      <g class="nl__chip nl__chip--${tint} ${extra}" transform="translate(${cx} ${cy})">
        <rect x="${-half}" y="-21" width="${half * 2}" height="42" rx="13" />
        <text y="1" text-anchor="middle" dominant-baseline="central">${value}</text>
      </g>`;
  }

  function esc(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  /* ------------------------------ registry ------------------------------ */

  const STRATEGIES = [bridgeThroughTen];

  window.MathHunterStrategies = {
    list: STRATEGIES,
    /** The plan for this problem, or null when no strategy covers it. */
    find(question) {
      if (!question) return null;
      const strategy = STRATEGIES.find((s) => s.applies(question));
      return strategy ? strategy.plan(question) : null;
    },
  };
})();
