/* =========================================================================
   Math Demon Hunters — what makes this trainer itself.

   Loaded before app.js, which is shared with the other trainer and reads
   everything game-specific from here: the operator, the words on screen, the
   colours the effects throw around, and which pairs the forge will offer.

   The pool rules mirror engine.Operation on the server — they decide what the
   preview shows, so a hunt the preview accepts is one the server accepts too.
   ========================================================================= */
(() => {
  "use strict";

  const MINUS = "−";
  const MAX_ANSWER_HINT = "allow answers below zero";

  /** How a side reads in a pool count: subtraction drops pairs below zero. */
  function count({ m1, m2, s1, s2, allow_negative }) {
    if (allow_negative) return (m2 - m1 + 1) * (s2 - s1 + 1);
    let total = 0;
    for (let m = m1; m <= m2; m++) total += Math.max(0, Math.min(s2, m) - s1 + 1);
    return total;
  }

  window.MathHunterGame = {
    id: "subtraction",
    glyph: MINUS,
    storage: "mdh", // localStorage namespace — kept from before there were two games
    negativeOption: true,
    sideModes: { m: "one", s: "range" }, // the forge opens on "10 − [0…9]"

    words: {
      sealed: "sealed",
      mark: "👺", // stands in for a picture pack with no thumbnail
      mastered: "⟡ DEMON SEALED ⟡",
      unsealed: "THE SEAL CRACKED!",
      timeUp: "⏳ TIME'S UP!",
      tryAgain: "TRY IT AGAIN",
      victoryCount: "demons sealed",
      poolCount: (n) => `${n} demon${n === 1 ? "" : "s"} in this hunt`,
      praise: ["STRIKE! +1", "CLEAN HIT! +1", "NICE! +1", "SHARP! +1", "BOOM! +1"],
      corrected: ["FIXED IT! +1", "THAT'S IT! +1", "GOT IT NOW! +1"],
      slow: ["GOT IT — now faster!", "Correct! Speed it up.", "Nice — quicker next time."],
    },

    palette: {
      embers: ["rgba(255,203,61,", "rgba(34,229,255,", "rgba(255,46,151,", "rgba(139,59,255,"],
      burst: ["#ffcb3d", "#22e5ff", "#ff2e97", "#8b3bff", "#fdf3ff"],
      confetti: ["#ffcb3d", "#22e5ff", "#ff2e97", "#8b3bff", "#fdf3ff", "#ff6b4a"],
      charm: "#ffcb3d", // the talismans in the confetti
      charmInk: "rgba(180,20,60,.9)",
      done: "#ffcb3d", // the progress ring on a hunt card
      going: "#22e5ff",
    },

    pool: {
      count,

      /** Every pair in the pool, in the order the hunt board shows them. */
      pairs({ m1, m2, s1, s2, allow_negative }) {
        const pairs = [];
        for (let m = m1; m <= m2; m++) {
          for (let s = s1; s <= s2; s++) {
            if (allow_negative || m >= s) pairs.push([m, s]);
          }
        }
        return pairs;
      },

      /** What is wrong with these ranges, or null when nothing is. */
      validate(values, rules) {
        const { m1, m2, s1, s2 } = values;
        const max = rules.max_operand;
        if ([m1, m2, s1, s2].some((n) => n < 0 || n > max)) {
          return `Numbers must be between 0 and ${max}.`;
        }
        if (m1 > m2) return "The start numbers have to go from low to high.";
        if (s1 > s2) return "The take-away numbers have to go from low to high.";
        const total = count(values);
        if (total === 0) {
          return `Every pair there goes below zero — raise the start numbers, lower the take-aways, or ${MAX_ANSWER_HINT}.`;
        }
        if (total > rules.max_pool_size) {
          return `Those ranges make ${total} problems — keep it to ${rules.max_pool_size} or fewer.`;
        }
        return null;
      },
    },
  };
})();
