// node --test src/lib/reports.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { REPORT_MENU, cellText, reportHref } from "./reports.ts";
import { menuOfPath } from "./nav.ts";

test("each report page belongs to the menu that guards it on the API", () => {
  for (const [code, menu] of Object.entries(REPORT_MENU)) assert.equal(menuOfPath(`/rpt/${code}`), menu, code);
  assert.equal(menuOfPath("/rpt"), "r0");
  assert.equal(menuOfPath("/rptx"), undefined);
});

test("R11 falls back to its public page", () => {
  assert.equal(reportHref("R11", () => false), "/stats");
  assert.equal(reportHref("R11", (m) => m === "rb"), "/rpt/R11");
  assert.equal(reportHref("R07", () => false), "/rpt/R07");
});

test("cells", () => {
  assert.equal(cellText(null), "–");
  assert.equal(cellText(""), "–");
  assert.equal(cellText(1234.567), "1,234.57");
  assert.equal(cellText("ผ่าน"), "ผ่าน");
});
