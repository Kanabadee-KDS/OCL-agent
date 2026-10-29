// node --test src/lib/flows.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { blankStep, move, problems, type Step } from "./flows.ts";

const s = (action: string, roles = ["central"]): Step => ({ ...blankStep(), action, roles });

test("move swaps with the neighbour and stays inside the list", () => {
  assert.deepEqual(move([1, 2, 3], 0, 1), [2, 1, 3]);
  assert.deepEqual(move([1, 2, 3], 0, -1), [1, 2, 3]);
  assert.deepEqual(move([1, 2, 3], 2, 1), [1, 2, 3]);
});

test("the same rules as the API", () => {
  assert.deepEqual(problems([s("submit"), s("approve")], null), []);
  assert.ok(problems([s("submit"), s("review")], null).some((p) => p.includes("ขั้นสุดท้าย")));
  assert.ok(problems([s("submit"), s("approve")], 3).some((p) => p.includes("3 ขั้น")));
  assert.ok(problems([s("submit", []), s("approve")], null).some((p) => p.includes("ขั้นที่ 1")));
  assert.deepEqual(problems([{ ...s("approve", []), position: "สภาวิชาการ" }], null), []);
});
