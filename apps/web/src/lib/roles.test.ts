// node --test src/lib/roles.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { changes, toggle, toggleRow } from "./roles.ts";

test("an action brings view along, view off clears the menu", () => {
  const a = toggle({}, "c1", "edit", true);
  assert.deepEqual(a, { c1: ["view", "edit"] });
  assert.deepEqual(toggle(a, "c1", "edit", false), { c1: ["view"] });
  assert.deepEqual(toggle(a, "c1", "view", false), {});
  assert.deepEqual(toggle({ c1: ["print", "view"] }, "c1", "add", true), { c1: ["view", "add", "print"] }, "kept in mock order");
});

test("whole rows and the unsaved count", () => {
  const all = toggleRow({}, "u3", true);
  assert.equal(all.u3.length, 6);
  assert.deepEqual(toggleRow(all, "u3", false), {});
  assert.equal(changes({ c1: ["view", "edit"] }, { c1: ["view"], r0: ["view"] }), 2);
  assert.equal(changes({ c1: ["view"] }, { c1: ["view"] }), 0);
});
