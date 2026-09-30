/* Checks for the subtraction strategy pictures.
   Run by tests/test_strategies.py, or on its own with
   `node tests/strategies_check_subtraction.js`. */

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SOURCE = path.join(__dirname, "..", "src", "mathhunters", "web", "subtraction", "strategies.js");

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

/* --- when the bridge applies ------------------------------------------- */

const COVERED = [];
for (let left = 11; left <= 20; left++) {
  for (let right = 1; right <= 9; right++) COVERED.push({ left, right });
}

for (const q of COVERED) {
  const label = `${q.left} - ${q.right}`;
  const plan = strategies.find(q);
  check(`${label}: a plan is offered`, plan !== null);
  if (!plan) continue;

  const [first, second] = plan.steps;
  check(`${label}: two smaller problems`, plan.steps.length === 2);
  check(`${label}: first hop is 10 - ${q.right}`, first.expected === 10 - q.right);
  check(`${label}: second hop is ${q.left} - 10`, second.expected === q.left - 10);
  check(`${label}: neither hop goes backwards`, first.expected >= 1 && second.expected >= 1);
  check(`${label}: the hops add up to the answer`, first.expected + second.expected === q.left - q.right);
  check(`${label}: the total is the answer`, plan.total === q.left - q.right);
  check(
    `${label}: the caption states the strategy`,
    plan.caption === `${q.left} − ${q.right} = (10 − ${q.right}) + (${q.left} − 10)`
  );

  // The picture is built from arithmetic on the two numbers; a slip there shows
  // up as NaN inside the markup rather than as an exception.
  const blank = plan.picture([null, null], null);
  const worked = plan.picture([first.expected, second.expected], plan.total);
  for (const [state, svg] of [["blank", blank], ["worked", worked]]) {
    check(`${label} (${state}): draws an svg`, svg.trim().startsWith("<svg") && svg.trim().endsWith("</svg>"));
    check(`${label} (${state}): no broken numbers`, !/NaN|undefined|Infinity/.test(svg));
    check(`${label} (${state}): both endpoints are marked`, svg.includes(`>${q.left}</text>`) && svg.includes(`>${q.right}</text>`));
  }
  check(`${label}: unanswered hops show a question mark`, (blank.match(/>\?</g) || []).length === 3);
  check(`${label}: a worked hop shows its value`, worked.includes(`>${first.expected}</text>`));
  check(`${label}: a worked picture shows the whole jump`, worked.includes(`>${plan.total}</text>`));
}

/* --- when it does not --------------------------------------------------- */

const UNCOVERED = [
  { left: 10, right: 4 },  // not a teen number
  { left: 21, right: 4 },  // past twenty
  { left: 14, right: 0 },  // nothing taken away
  { left: 14, right: 10 }, // the take-away is not a single digit
  { left: 14, right: 14 },
  { left: 9, right: 3 },   // the jump never reaches 10
  { left: 100, right: 7 },
];

for (const q of UNCOVERED) {
  check(`${q.left} - ${q.right}: no strategy claims it`, strategies.find(q) === null);
}
check("a missing question is handled", strategies.find(null) === null);

/* --- the registry itself ------------------------------------------------ */

check("every strategy has an id, a title, applies() and plan()", strategies.list.every(
  (s) => s.id && s.title && typeof s.applies === "function" && typeof s.plan === "function"
));
check("strategy ids are unique", new Set(strategies.list.map((s) => s.id)).size === strategies.list.length);

/* --- report ------------------------------------------------------------- */

if (failures.length) {
  console.error(`${failures.length} of ${checks} checks failed:`);
  for (const failure of failures.slice(0, 20)) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`ok — ${checks} checks over ${COVERED.length} covered problems`);
