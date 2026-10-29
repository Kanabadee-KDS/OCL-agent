// node --test src/lib/form.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { asInput, columnTotals, fromInput, getPath, setPath } from "./form.ts";

test("paths read and write nested objects and list items without mutating", () => {
  const d = { info: { values: { name_th: "ก" } }, plan: { plans: [{ rows: [] }] } };
  assert.equal(getPath(d, "info.values.name_th"), "ก");
  assert.equal(getPath(d, "info.values.none.deeper"), undefined);
  const e = setPath(d, "info.values.name_en", "A");
  assert.equal(getPath(e, "info.values.name_en"), "A");
  assert.equal(getPath(d, "info.values.name_en"), undefined, "original untouched");
  const f = setPath(d, "plan.plans.0.rows", [{ values: [1] }]);
  assert.ok(Array.isArray((f as { plan: { plans: unknown[] } }).plan.plans));
  assert.deepEqual(getPath(f, "plan.plans.0.rows"), [{ values: [1] }]);
  assert.deepEqual(setPath({}, "appr.mhesi_ack_date", "2026-10-29"), { appr: { mhesi_ack_date: "2026-10-29" } });
});

test("inputs: imported dates, numbers, and blanks", () => {
  assert.equal(asInput({ iso: "2025-03-11", text: "11 มีนาคม 2568" }, "date"), "2025-03-11");
  assert.equal(asInput(null, "text"), "");
  assert.equal(fromInput("127", "int"), 127);
  assert.equal(fromInput("", "int"), null);
  assert.deepEqual(columnTotals([{ values: [50, 50] }, { values: [0, 50] }], 2), [50, 100]);
});
