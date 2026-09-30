/* =========================================================================
   Math Jewel Hunters — strategy pictures.

   A strategy shows how one problem can be broken into smaller ones. Each
   strategy answers three things:

     applies(question) — is this a problem it can help with?
     plan(question)    — which smaller problems does it break into?
     picture(values)   — what does that look like, given what has been
                         filled in so far?

   The app supplies everything around them: the boxes to type the parts into,
   the checking, the running sum, and the reveal when an answer is missed.

   Multiplication is drawn as what it is: equal groups.  4 × 6 is four piles of
   six shards of the Shikon Jewel, and adding the piles up is the answer.  A
   question arrives as ``left`` and ``right`` — here, how many piles and how
   many shards in each.
   ========================================================================= */
(() => {
  "use strict";

  const TIMES = "×";

  // How wide a spread of shapes stays countable at a glance.  More piles than
  // this and the picture stops helping; more shards than this in one pile and
  // counting them is harder than the multiplication.
  const MAX_PILES = 5;
  const MAX_PER_PILE = 10;
  const TINTS = ["cyan", "magenta", "gold", "violet", "bone"];

  const shardWord = (n) => `${n} shard${n === 1 ? "" : "s"}`;

  /**
   * One box per pile, each holding how many shards are in it.  Adding them up
   * is the answer, so the last step of the work stays the kid's to do.
   */
  function groupPlan(id, title, piles, per, caption, prompt) {
    const steps = Array.from({ length: piles }, (_, i) => ({
      text: `Pile ${i + 1}`,
      expected: per,
      tint: TINTS[i % TINTS.length],
    }));
    return {
      id,
      title,
      caption,
      steps,
      join: "+",
      total: piles * per,
      prompt,
      picture: (values, total) => groupsPicture(piles, per, steps, values, total),
      describe: (values) => describeGroups(piles, per, values),
    };
  }

  /* ---------------------------- equal groups ---------------------------- */

  /**
   * The plain reading of ``a × b``: a piles with b shards in each.
   *
   *     4 × 6  =  6 + 6 + 6 + 6  =  24
   */
  const equalGroups = {
    id: "equal-groups",
    title: "EQUAL GROUPS",

    applies: (q) =>
      q.left >= 2 && q.left <= MAX_PILES && q.right >= 1 && q.right <= MAX_PER_PILE,

    plan(q) {
      const piles = q.left;
      const per = q.right;
      return groupPlan(
        this.id,
        this.title,
        piles,
        per,
        `${piles} ${TIMES} ${per} = ${piles} piles of ${per}`,
        "Count each pile, then add the piles up — that is your answer."
      );
    },
  };

  /* ------------------------------ turn it round -------------------------- */

  /**
   * Too many piles to lay out, but few enough shards to turn the problem round:
   * ``9 × 2`` is nine piles of two, which is the same total as two piles of nine.
   * The picture draws the easier way of seeing it, and says so.
   */
  const turnItRound = {
    id: "turn-it-round",
    title: "TURN IT ROUND",

    applies: (q) =>
      q.left > MAX_PILES &&
      q.left <= MAX_PER_PILE &&
      q.right >= 2 &&
      q.right <= MAX_PILES,

    plan(q) {
      const piles = q.right; // the flipped reading: fewer piles, bigger ones
      const per = q.left;
      return groupPlan(
        this.id,
        this.title,
        piles,
        per,
        `${q.left} ${TIMES} ${q.right} is the same as ${piles} ${TIMES} ${per} — ${piles} piles of ${per}`,
        "Same total either way round. Count each pile, then add them up."
      );
    },
  };

  /* ----------------------------- the picture ----------------------------- */

  const W = 640;
  const PAD = 26;
  const GAP = 14;
  const CELL = 30; // one shard's square of space inside a pile
  const TOP = 10;

  const filled = (value) => typeof value === "number" && Number.isFinite(value);

  /** Where everything sits, given how many piles of how many there are. */
  function layout(piles, per) {
    const pileW = (W - 2 * PAD - GAP * (piles - 1)) / piles;
    const fits = Math.max(1, Math.min(5, Math.floor((pileW - 12) / CELL)));
    const cols = Math.min(per, fits);
    const rows = Math.ceil(per / cols);
    const pileH = rows * CELL + 22;
    const chipY = TOP + pileH + 24;
    const spanY = chipY + 42;
    return { pileW, cols, rows, pileH, chipY, spanY, height: spanY + 44 };
  }

  /** One shard of the jewel: a small crystal, tilted so a pile looks gathered. */
  function shard(cx, cy, index) {
    const tilt = ((index * 37) % 31) - 15;
    return `
      <g class="grp__shard" transform="translate(${cx} ${cy}) rotate(${tilt})">
        <path class="grp__shard-body" d="M0 -11 L7 -3.5 L4 10 L-4 10 L-7 -3.5 Z" />
        <path class="grp__shard-shine" d="M0 -8 L4 -3 L1.5 7" />
      </g>`;
  }

  /** The shards of one pile, laid out in rows and centred. */
  function pileShards(per, cols, x, y, pileW, offset) {
    const shards = [];
    for (let i = 0; i < per; i++) {
      const row = Math.floor(i / cols);
      const inRow = Math.min(cols, per - row * cols);
      const column = i % cols;
      const cx = x + pileW / 2 + (column - (inRow - 1) / 2) * CELL;
      const cy = y + 16 + row * CELL + CELL / 2;
      shards.push(shard(cx, cy, offset + i));
    }
    return shards.join("");
  }

  /** The piles, their counts, and the whole jewel they add up to. */
  function groupsPicture(piles, per, steps, values, total) {
    const box = layout(piles, per);
    const left = (i) => PAD + i * (box.pileW + GAP);

    const drawn = steps.map((step, i) => {
      const x = left(i);
      const done = filled(values[i]);
      return `
        <g class="grp__pile grp__pile--${step.tint}${done ? " is-done" : ""}">
          <rect class="grp__pen" x="${x}" y="${TOP}" width="${box.pileW}" height="${box.pileH}" rx="16" />
          ${pileShards(per, box.cols, x, TOP, box.pileW, i * per)}
          ${chip(x + box.pileW / 2, box.chipY, done ? values[i] : "?", step.tint)}
        </g>`;
    });

    // Every pile together: that is the answer.
    const whole = `
      <g class="grp__whole${filled(total) ? " is-done" : ""}">
        <path class="grp__span" d="M${PAD} ${box.chipY + 24} L${PAD} ${box.spanY} L${W - PAD} ${box.spanY} L${W - PAD} ${box.chipY + 24}" />
        ${chip(W / 2, box.spanY, filled(total) ? total : "?", "gold", "whole")}
        <text class="grp__caption" x="${W / 2}" y="${box.spanY + 38}" text-anchor="middle">EVERY PILE TOGETHER</text>
      </g>`;

    return `
      <svg class="grp" viewBox="0 0 ${W} ${box.height}" role="img" aria-label="${esc(describeGroups(piles, per, values))}">
        ${drawn.join("")}
        ${whole}
      </svg>`;
  }

  /** The same picture, in words, for anyone reading with a screen reader. */
  function describeGroups(piles, per, values) {
    const counted = values.filter(filled).length;
    return (
      `${piles} piles of jewel shards, ${shardWord(per)} in each. ` +
      `${counted} of the ${piles} piles have been counted so far. ` +
      `All the piles added together make the answer.`
    );
  }

  /** A rounded label under a pile, holding its count once it is known. */
  function chip(cx, cy, value, tint, extra = "") {
    const wide = String(value).length > 1;
    const half = wide ? 32 : 25;
    return `
      <g class="grp__chip grp__chip--${tint} ${extra}" transform="translate(${cx} ${cy})">
        <rect x="${-half}" y="-21" width="${half * 2}" height="42" rx="13" />
        <text y="1" text-anchor="middle" dominant-baseline="central">${value}</text>
      </g>`;
  }

  function esc(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  /* ------------------------------ registry ------------------------------ */

  const STRATEGIES = [equalGroups, turnItRound];

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
