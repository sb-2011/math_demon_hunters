/* =========================================================================
   Math Jewel Hunters — what makes this trainer itself.

   Loaded before app.js, which is shared with the other trainer and reads
   everything game-specific from here: the operator, the words on screen, the
   colours the effects throw around, and which pairs the forge will offer.

   The pool rules mirror engine.Operation on the server — they decide what the
   preview shows, so a hunt the preview accepts is one the server accepts too.
   ========================================================================= */
(() => {
  "use strict";

  const TIMES = "×";

  /** Multiplication keeps every pair: none of them go anywhere awkward. */
  const count = ({ m1, m2, s1, s2 }) => (m2 - m1 + 1) * (s2 - s1 + 1);

  window.MathHunterGame = {
    id: "multiplication",
    glyph: TIMES,
    storage: "mjh", // localStorage namespace, kept apart from the other trainer's
    negativeOption: false, // nothing here goes below zero
    sideModes: { m: "one", s: "range" }, // the forge opens on "3 × [1…10]"

    words: {
      sealed: "purified",
      mark: "🔮", // stands in for a picture pack with no thumbnail
      mastered: "⟡ SHARD PURIFIED ⟡",
      unsealed: "THE SHARD IS TAINTED!",
      timeUp: "⏳ TIME'S UP!",
      tryAgain: "TRY IT AGAIN",
      victoryCount: "shards purified",
      poolCount: (n) => `${n} shard${n === 1 ? "" : "s"} in this hunt`,
      praise: ["WIND SCAR! +1", "SACRED ARROW! +1", "IRON REAVER! +1", "CLEAN SLASH! +1", "SHARP! +1"],
      corrected: ["FIXED IT! +1", "THAT'S IT! +1", "GOT IT NOW! +1"],
      slow: ["GOT IT — now faster!", "Correct! Speed it up.", "Nice — quicker next time."],
    },

    palette: {
      embers: ["rgba(255,207,107,", "rgba(86,223,180,", "rgba(255,69,111,", "rgba(154,82,214,"],
      burst: ["#ffcf6b", "#56dfb4", "#ff456f", "#9a52d6", "#f7f2e2"],
      confetti: ["#ffcf6b", "#56dfb4", "#ff456f", "#9a52d6", "#f7f2e2", "#ff8a5c"],
      charm: "#fffaf0", // the paper charms in the confetti
      charmInk: "rgba(190,30,60,.9)",
      done: "#ffcf6b", // the progress ring on a hunt card
      going: "#56dfb4",
    },

    pool: {
      count,

      /** Every pair in the pool, in the order the hunt board shows them. */
      pairs({ m1, m2, s1, s2 }) {
        const pairs = [];
        for (let m = m1; m <= m2; m++) {
          for (let s = s1; s <= s2; s++) pairs.push([m, s]);
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
        if (m1 > m2) return "The number of groups has to go from low to high.";
        if (s1 > s2) return "The group sizes have to go from low to high.";
        // The answer pad holds three digits, so a hunt whose biggest product runs
        // past that would contain problems that cannot be answered at all.
        const biggest = m2 * s2;
        if (biggest > max) {
          return `${m2} ${TIMES} ${s2} is ${biggest}, past the ${max} the answer pad holds — lower the ranges.`;
        }
        const total = count(values);
        if (total > rules.max_pool_size) {
          return `Those ranges make ${total} problems — keep it to ${rules.max_pool_size} or fewer.`;
        }
        return null;
      },
    },
  };
})();
