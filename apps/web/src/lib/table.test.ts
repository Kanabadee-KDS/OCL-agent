// node --test src/lib/table.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { filterRows, matches, options, pageList, paginate, sortRows } from "./table.ts";

type C = { name: string; fac: string; year: number | null };
const rows: C[] = [
  { name: "วท.บ. วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ", fac: "คณะวิทยาศาสตร์", year: 2568 },
  { name: "ศศ.บ. การจัดการภูมิสังคมและวัฒนธรรม", fac: "คณะสังคมศาสตร์", year: 2569 },
  { name: "ปร.ด. เศรษฐศาสตร์เพื่อการพัฒนาอย่างยั่งยืน", fac: "คณะเศรษฐศาสตร์", year: null },
  { name: "วท.บ. วิทยาศาสตร์การอาหารและโภชนาการ", fac: "คณะวิทยาศาสตร์", year: 2567 },
];

test("search ignores spaces and case", () => {
  assert.ok(matches("วท.บ. วิทยาการ", "วท.บ.วิทยา"));
  assert.ok(matches("GEN111 Thai", "gen 111"));
  assert.ok(matches("anything", "  "));
  assert.ok(!matches(null, "x"));
});

test("filters combine with the search; an empty filter means all", () => {
  const got = filterRows(rows, "วท.บ.", (r) => r.name, { fac: "คณะวิทยาศาสตร์", year: "" }, (r, k) => (k === "fac" ? r.fac : String(r.year)));
  assert.equal(got.length, 2);
  assert.equal(filterRows(rows, "", (r) => r.name).length, 4);
});

test("sort: numbers as numbers, empty last in both directions, stable", () => {
  assert.deepEqual(sortRows(rows, (r) => r.year).map((r) => r.year), [2567, 2568, 2569, null]);
  assert.deepEqual(sortRows(rows, (r) => r.year, "desc").map((r) => r.year), [2569, 2568, 2567, null]);
  const same = sortRows(rows, (r) => r.fac);
  assert.equal(same[0].fac, "คณะวิทยาศาสตร์");
  assert.ok(same.indexOf(rows[0]) < same.indexOf(rows[3]), "stable for equal keys");
});

test("paginate reports the range and clamps the page", () => {
  const items = Array.from({ length: 23 }, (_, i) => i);
  assert.deepEqual(paginate(items, 3, 10), { rows: [20, 21, 22], page: 3, pages: 3, total: 23, from: 21, to: 23 });
  assert.equal(paginate(items, 9, 10).page, 3);
  assert.deepEqual(paginate([], 1, 10), { rows: [], page: 1, pages: 1, total: 0, from: 0, to: 0 });
});

test("page list keeps both ends and the neighbourhood of the current page", () => {
  assert.deepEqual(pageList(1, 5), [1, 2, 3, 4, 5]);
  assert.deepEqual(pageList(1, 35), [1, 2, "…", 34, 35]);
  assert.deepEqual(pageList(10, 35), [1, 2, "…", 9, 10, 11, "…", 34, 35]);
  assert.deepEqual(pageList(34, 35), [1, 2, "…", 33, 34, 35]);
});

test("filter options are distinct and sorted", () => {
  assert.deepEqual(options(rows, (r) => r.fac), ["คณะวิทยาศาสตร์", "คณะเศรษฐศาสตร์", "คณะสังคมศาสตร์"]);
});
