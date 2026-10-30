// node --test src/lib/qa.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { finalOf, pickRound, setOf } from "./qa.ts";

test("the result of a curriculum follows BR-M4-01", () => {
  assert.equal(finalOf({ 1: "pass", 2: "pass", 5: "na" }), "pass");
  assert.equal(finalOf({ 1: "pass", 2: "fail" }), "fail");
  assert.equal(finalOf({ 1: "pass", 2: "pending" }), "pending");
  assert.equal(finalOf({ 1: "pass", 2: undefined }), "pending");
  assert.equal(finalOf({}), "pending");
});

test("rounds and sets", () => {
  const rounds = [{ id: 3, status: "draft" }, { id: 2, status: "open" }, { id: 1, status: "closed" }];
  assert.equal(pickRound(rounds, null), 2);
  assert.equal(pickRound(rounds, 1), 1);
  assert.equal(pickRound(rounds, 9), 2);
  assert.equal(pickRound([], null), null);
  assert.deepEqual(["ประกาศ อว. 2565 (ตรี)", "ศธ. 2558", "", "2560"].map((x) => setOf(x)), [2565, 2558, 2565, 2565]);
});
