// node --test src/lib/skills.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { avg, completeCount, coverage, levelOf, parseScore, slugOf, termOf } from "./skills.ts";

const LEVELS = [
  { min: 0, max: 1.49, en: "Novice" }, { min: 1.5, max: 2.49, en: "Advanced Beginner" }, { min: 2.5, max: 3.49, en: "Competent" },
  { min: 3.5, max: 4.49, en: "Proficient" }, { min: 4.5, max: 5, en: "Expert" },
];

test("levels and averages follow BR-M3-01 02", () => {
  assert.deepEqual([0, 1.49, 1.5, 2.495, 4.47, 5].map((x) => levelOf(x, LEVELS)?.en), ["Novice", "Novice", "Advanced Beginner", "Competent", "Proficient", "Expert"]);
  assert.equal(levelOf(null, LEVELS), null);
  assert.equal(avg([4.21, 4.35, 4.51, 4.79]), 4.47, "the mock's example");
  assert.equal(avg([]), null);
});

test("the score grid", () => {
  assert.equal(parseScore(""), null);
  assert.equal(parseScore("4.256"), 4.26);
  assert.ok(Number.isNaN(parseScore("6")) && Number.isNaN(parseScore("x")));
  assert.equal(completeCount(["a", "b"], ["GS1", "E1"], { a: { GS1: 3, E1: 2 }, b: { GS1: 3 } }), 1);
});

test("the mapping's coverage counts offered courses only", () => {
  const c = coverage([{ code: "X1", offered: true }, { code: "X2", offered: true }, { code: "X3", offered: false }], { X1: ["GS1", "E1"], X3: ["C1"] }, ["GS1", "E1", "C1"]);
  assert.deepEqual(c, { mapped: 1, points: 2, gaps: ["C1"] });
  assert.equal(termOf(slugOf("2/2569")), "2/2569");
});
