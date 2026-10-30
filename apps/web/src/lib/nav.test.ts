// node --test src/lib/nav.test.ts · the menu tree trimmed by the `perms` the API sends.
// Which role holds which menu is tested on the API (tests/test_auth.py), where it lives.
import { test } from "node:test";
import assert from "node:assert/strict";
import { NAV, builtPages, canMenu, menuOfPath, visibleNav, type Perms } from "./nav.ts";

// what the API sends a teacher and a faculty reviewer by default (ocl_api.perms)
const teacher: Perms = Object.fromEntries(["p2", "p4", "s4", "s5", "r0", "r7", "r8"].map((m) => [m, ["view", "add", "edit", "print"]]));
const faculty: Perms = { c1: ["view", "edit"], c3: ["view", "print"], c3h: ["view", "print"], r1: ["view"] };
const ids = (p: Perms) => visibleNav(p).flatMap((m) => m.secs.flatMap((s) => s.items.map((i) => i.id)));

test("only menus with 'view' are shown, empty modules disappear", () => {
  assert.deepEqual(ids(teacher), ["p2", "p4", "s4", "s5", "r0", "r7", "r8"]);
  assert.deepEqual(visibleNav(teacher).map((m) => m.k), ["p", "s", "r"]);
  assert.deepEqual(ids({ c1: ["edit"] }), [], "an action without view shows nothing");
  assert.deepEqual(visibleNav(undefined), []);
});

test("actions are checked per menu", () => {
  assert.ok(canMenu(teacher, "p2", "edit"));
  assert.ok(!canMenu(teacher, "p2", "approve"));
  assert.ok(!canMenu(faculty, "c3", "add"), "the faculty reviewer reads imports only");
});

test("import history follows the import menu", () => {
  assert.ok(canMenu({ c3: ["view"] }, "c3h"));
  assert.ok(!canMenu(teacher, "c3h"));
});

test("detail pages belong to their menu", () => {
  assert.equal(menuOfPath("/import/abc123"), "c3");
  assert.equal(menuOfPath("/import/history"), "c3h");
  assert.equal(menuOfPath("/curricula/7"), "c1");
  assert.equal(menuOfPath("/importer"), undefined);
  assert.equal(menuOfPath("/plans/assign"), "p1");
  assert.equal(menuOfPath("/plans/2-2569/C:x"), "p2");
  assert.equal(menuOfPath("/reports/2-2569/C:x"), "p4");
  assert.equal(menuOfPath("/dashboard/plans"), "d2");
  assert.equal(menuOfPath("/dashboard/skills"), "d3");
  assert.equal(menuOfPath("/skills/mapping"), "s3");
  assert.equal(menuOfPath("/skills"), "s1");
  assert.equal(menuOfPath("/assess/2-2569/x/1"), "s4");
  assert.equal(menuOfPath("/portfolio/123/transcript"), "s5");
  assert.equal(menuOfPath("/me/transcript"), "m2");
  assert.equal(menuOfPath("/me"), "m1");
});

test("landing page is the first built page the user may open", () => {
  assert.equal(builtPages(faculty)[0]?.href, "/curricula");
  assert.deepEqual(builtPages(teacher).map((i) => i.href), ["/plans", "/reports", "/assess", "/portfolio"], "FS-4 FS-5: plans, reports, skill scores, portfolio");
});

test("every menu id is unique", () => {
  const all = NAV.flatMap((m) => m.secs.flatMap((s) => s.items.map((i) => i.id)));
  assert.equal(new Set(all).size, all.length);
  assert.equal(all.length, 43); // 39 menus of the mock + import history (US-M1-21) + the three dashboards the mock adds (NAV.unshift)
});
