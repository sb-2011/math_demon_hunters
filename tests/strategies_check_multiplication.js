/* Checks for the multiplication strategy pictures.
   Run by tests/test_strategies.py, or on its own with
   `node tests/strategies_check_multiplication.js`. */

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SOURCE = path.join(__dirname, "..", "src", "mathhunters", "web", "multiplication", "strategies.js");

// The file is a browser script that hangs its API off `window`; give it one.
const sandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(SOURCE, "utf8"), sandbox, { filename: SOURCE });
const strategies = sandbox.window.MathHunterStrategies;

let checks = 0;
const failures = [];

function check(what, condition) {
  checks += 1;
  if (!condition) failures.push(what);
}

/* --- equal groups: 2…5 piles of 1…10 ----------------------------------- */

const COVERED = [];
for (let left = 2; left <= 5; left++) {
  for (let right = 1; right <= 10; right++) COVERED.push({ left, right });
}

for (const q of COVERED) {
  const label = `${q.left} x ${q.right}`;
  const plan = strategies.find(q);
  check(`${label}: a plan is offered`, plan !== null);
  if (!plan) continue;

  check(`${label}: drawn the way it is written`, plan.id === "equal-groups");
  check(`${label}: one pile per group`, plan.steps.length === q.left);
  check(`${label}: every pile holds the group size`, plan.steps.every((s) => s.expected === q.right));
  check(`${label}: the piles add up to the answer`,
    plan.steps.reduce((sum, s) => sum + s.expected, 0) === q.left * q.right);
  check(`${label}: the total is the answer`, plan.total === q.left * q.right);
  check(`${label}: the parts are added, not something else`, plan.join === "+");
  check(`${label}: the caption states the strategy`,
    plan.caption === `${q.left} × ${q.right} = ${q.left} piles of ${q.right}`);
  check(`${label}: no pile label gives the count away`,
    plan.steps.every((s, i) => s.text === `Pile ${i + 1}`));

  // The picture is built from arithmetic on the two numbers; a slip there shows
  // up as NaN inside the markup rather than as an exception.
  const blank = plan.picture(plan.steps.map(() => null), null);
  const worked = plan.picture(plan.steps.map((s) => s.expected), plan.total);
  for (const [state, svg] of [["blank", blank], ["worked", worked]]) {
    check(`${label} (${state}): draws an svg`, svg.trim().startsWith("<svg") && svg.trim().endsWith("</svg>"));
    check(`${label} (${state}): no broken numbers`, !/NaN|undefined|Infinity/.test(svg));
    check(`${label} (${state}): one pen per pile`, (svg.match(/grp__pen/g) || []).length === q.left);
    check(`${label} (${state}): every shard is drawn`,
      (svg.match(/grp__shard-body/g) || []).length === q.left * q.right);
    check(`${label} (${state}): the picture is described in words`, svg.includes(`aria-label="${q.left} piles of jewel shards, ${q.right} shard`));
  }
  check(`${label}: uncounted piles show a question mark`, (blank.match(/>\?</g) || []).length === q.left + 1);
  check(`${label}: a counted pile shows its count`, worked.includes(`>${q.right}</text>`));
  check(`${label}: a worked picture shows the whole total`, worked.includes(`>${plan.total}</text>`));
}

/* --- turn it round: too many piles, so swap the two numbers ------------- */

const FLIPPED = [];
for (let left = 6; left <= 10; left++) {
  for (let right = 2; right <= 5; right++) FLIPPED.push({ left, right });
}

for (const q of FLIPPED) {
  const label = `${q.left} x ${q.right}`;
  const plan = strategies.find(q);
  check(`${label}: a plan is offered`, plan !== null);
  if (!plan) continue;

  check(`${label}: turned round rather than laid out in ${q.left} piles`, plan.id === "turn-it-round");
  check(`${label}: as many piles as the smaller number`, plan.steps.length === q.right);
  check(`${label}: each pile holds the bigger number`, plan.steps.every((s) => s.expected === q.left));
  check(`${label}: the total is unchanged by turning it round`, plan.total === q.left * q.right);
  check(`${label}: the caption says what was swapped`,
    plan.caption === `${q.left} × ${q.right} is the same as ${q.right} × ${q.left} — ${q.right} piles of ${q.left}`);

  const svg = plan.picture(plan.steps.map((s) => s.expected), plan.total);
  check(`${label}: no broken numbers`, !/NaN|undefined|Infinity/.test(svg));
  check(`${label}: every shard is drawn`, (svg.match(/grp__shard-body/g) || []).length === q.left * q.right);
}

/* --- nothing is drawn off the edge of the picture ----------------------- */

/** Everything the picture draws, checked against the box it is drawn in. */
function staysInside(plan) {
  const svg = plan.picture(plan.steps.map((s) => s.expected), plan.total);
  const [W, H] = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/).slice(1).map(Number);
  for (const m of svg.matchAll(/class="grp__pen" x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"/g)) {
    const [x, y, w, h] = m.slice(1).map(Number);
    if (x < 0 || y < 0 || x + w > W + 0.5 || y + h > H + 0.5) return false;
  }
  // Shards and count chips are placed by their centre; keep their boxes in too.
  for (const m of svg.matchAll(/translate\(([-\d.]+) ([-\d.]+)\)/g)) {
    const [x, y] = m.slice(1).map(Number);
    if (x - 33 < 0 || y - 22 < 0 || x + 33 > W || y + 22 > H) return false;
  }
  return true;
}

for (const q of [...COVERED, ...FLIPPED]) {
  check(`${q.left} x ${q.right}: the whole picture fits in its box`, staysInside(strategies.find(q)));
}

/* --- when nothing applies ---------------------------------------------- */

const UNCOVERED = [
  { left: 1, right: 5 },   // one pile is not a group to add up
  { left: 5, right: 0 },   // empty piles draw nothing
  { left: 0, right: 7 },
  { left: 7, right: 8 },   // too many piles, and too many in each to turn round
  { left: 9, right: 9 },
  { left: 12, right: 3 },  // piles bigger than a picture can hold
  { left: 6, right: 11 },
];

for (const q of UNCOVERED) {
  check(`${q.left} x ${q.right}: no strategy claims it`, strategies.find(q) === null);
}
check("a missing question is handled", strategies.find(null) === null);

/* --- the registry itself ------------------------------------------------ */

check("every strategy has an id, a title, applies() and plan()", strategies.list.every(
  (s) => s.id && s.title && typeof s.applies === "function" && typeof s.plan === "function"
));
check("strategy ids are unique", new Set(strategies.list.map((s) => s.id)).size === strategies.list.length);
check("no problem is claimed by two strategies", [...COVERED, ...FLIPPED].every(
  (q) => strategies.list.filter((s) => s.applies(q)).length === 1
));

/* --- report ------------------------------------------------------------- */

if (failures.length) {
  console.error(`${failures.length} of ${checks} checks failed:`);
  for (const failure of failures.slice(0, 20)) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`ok — ${checks} checks over ${COVERED.length + FLIPPED.length} covered problems`);
