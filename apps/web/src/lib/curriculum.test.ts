// node --test src/lib/curriculum.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { addNode, allCodes, coursesOf, creditSum, findNode, formatCell, ksecLabel, mapNode, mappingColumns, mappingRows, nodeOf, parseCell, renameKsec, setCell, summary, syncKsec, type Node } from "./curriculum.ts";

const plos = [{ code: "PLO1", text: "ก" }, { code: "PLO2", text: "ข" }];

test("ksec follows the PLO list and the summary groups codes by K S E C", () => {
  const ksec = syncKsec(plos, [{ code: "PLO2", items: [{ code: "S2-1", category: "S", text: "x" }] }, { code: "OLD", items: [] }]);
  assert.deepEqual(ksec.map((k) => [k.code, k.text, k.items.length]), [["PLO1", "ก", 0], ["PLO2", "ข", 1]]);
  assert.deepEqual(allCodes(ksec), ["S2-1"]);
  assert.deepEqual(summary(ksec)[1].cells, { K: [], S: ["S2-1"], E: [], C: [] });
});

test("ksec split by study plan keeps one entry per plan and PLO (ป.โท แผน 1 / แผน 2)", () => {
  const two = [
    { code: "PLO1", plan: "แผน 1", text: "ถ้อยคำแผน 1", items: [{ code: "K1-1", category: "K", text: "a" }] },
    { code: "PLO2", plan: "แผน 1", text: "", items: [] },
    { code: "PLO1", plan: "แผน 2", text: "ถ้อยคำแผน 2", items: [{ code: "K1-1", category: "K", text: "b" }] },
  ];
  const k = syncKsec([...plos, { code: "PLO3", text: "ค" }], two);
  assert.deepEqual(k.map(ksecLabel), ["PLO1 · แผน 1", "PLO2 · แผน 1", "PLO3 · แผน 1", "PLO1 · แผน 2", "PLO2 · แผน 2", "PLO3 · แผน 2"]);
  assert.deepEqual([k[0].text, k[3].text, k[1].text], ["ถ้อยคำแผน 1", "ถ้อยคำแผน 2", "ข"], "a plan keeps its own wording, a blank one takes the PLO's");
  assert.deepEqual([k[0].items[0].text, k[3].items[0].text], ["a", "b"], "plan 2 is not merged into plan 1");
  assert.deepEqual(summary(k).map((r) => r.key).length, new Set(summary(k).map((r) => r.key)).size, "unique rows");
  const renamed = syncKsec([{ code: "PLO-A", text: "ก" }], renameKsec(two, "PLO1", "PLO-A"));
  assert.deepEqual(renamed.map((x) => [x.code, x.items.length]), [["PLO-A", 1], ["PLO-A", 1]], "a renamed PLO keeps its KSEC");
});

test("mapping cells read like the book: '1,4' in K1 is K1-1 and K1-4", () => {
  assert.deepEqual(mappingColumns(plos).map((c) => c.col), ["K1", "S1", "E1", "C1", "K2", "S2", "E2", "C2"]);
  assert.deepEqual(parseCell("4, 1,x,1", "K1"), ["K1-1", "K1-4"]);
  assert.equal(formatCell(["K1-1", "K1-4", "S1-2"], "K1"), "1,4");
  const row = { course_code: "ศท111", plos: [], by_column: {}, ksec_codes: [] };
  const r = setCell(row, "S2", "3", plos);
  assert.deepEqual([r.plos, r.ksec_codes], [["PLO2"], ["S2-3"]]);
  assert.deepEqual(setCell(r, "S2", "", plos).plos, [], "emptied cell drops the PLO");
  const rows = mappingRows([{ code_th: "ศท111" }, { code_th: "ใหม่1", name_th: "ใหม่" }], [r]);
  assert.equal(rows[0], r);
  assert.deepEqual(rows[1].by_column, {});
});

const tree: Node[] = [
  { number: "1", name: "หมวดวิชาศึกษาทั่วไป", credits: 24, children: [{ number: "1.1", name: "วิชาบังคับ", children: [] }] },
  { number: "2", name: "หมวดวิชาเฉพาะ", credits: 91, children: [{ number: "2.1", name: "วิชาบังคับ", children: [] }, { number: "2.2", name: "วิชาเลือก", children: [] }] },
];

test("the tree: add, rename, remove, sum", () => {
  const t1 = addNode(tree, "2", "วิชาเลือกเสรี");
  assert.equal(findNode(t1, "2.3")?.node.name, "วิชาเลือกเสรี");
  assert.equal(findNode(t1, "2.3")?.path.map((p) => p.number).join(">"), "2");
  assert.equal(addNode(tree, null, "หมวดวิชาเลือกเสรี").at(-1)?.number, "3");
  assert.equal(findNode(mapNode(t1, "2.3", (n) => ({ ...n, name: "เสรี" })), "2.3")?.node.name, "เสรี");
  assert.equal(findNode(mapNode(t1, "2.3", () => null), "2.3"), undefined);
  assert.equal(creditSum(tree), 115);
});

test("courses belong to a node only by an explicit link", () => {
  const courses = [
    { code_th: "ก1", group: "วิชาบังคับ" },
    { code_th: "ก2", group: "วิชาเลือก" },
    { code_th: "ก3", group: "วิชาบังคับ", node: "2.1" },
    { code_th: "ก4", node: "9.9" },
  ];
  assert.deepEqual(coursesOf(courses, findNode(tree, "2.2")!.node).map((c) => c.code_th), [], "a group name is not a link");
  assert.deepEqual(coursesOf(courses, findNode(tree, "2.1")!.node).map((c) => c.code_th), ["ก3"]);
  assert.deepEqual(courses.map((c) => nodeOf(c, tree)), [null, null, "2.1", null], "a link to a removed group counts as unlinked");
});
