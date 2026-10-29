// node --test src/lib/nav.test.ts · checks the menus against BRD 00 §3 (who sees which module)
import { test } from "node:test";
import assert from "node:assert/strict";
import { NAV, ROLE_ACCESS, builtPages, canMenu, menuOfPath, visibleNav } from "./nav.ts";

const mods = (roles: string[]) => visibleNav(roles).map((m) => m.k).join(" ");

test("each role sees the modules of the mock's ROLES table", () => {
  assert.equal(mods(["admin"]), "c p s q r u");
  assert.equal(mods(["central"]), "c p s q r u");
  assert.equal(mods(["curator"]), "c p s q r");
  assert.equal(mods(["faculty"]), "c p s q r");
  assert.equal(mods(["evaluator"]), "q");
  assert.equal(mods(["teacher"]), "p s r");
  assert.equal(mods(["advisor"]), "s r");
  assert.equal(mods(["student"]), "m");
  assert.equal(mods(["exec"]), "r");
  assert.equal(mods([]), "");
});

test("teacher and advisor see only their menus inside a module", () => {
  const items = (roles: string[]) => visibleNav(roles).flatMap((m) => m.secs.flatMap((s) => s.items.map((i) => i.id)));
  assert.deepEqual(items(["teacher"]), ["p2", "p4", "s4", "s5", "r0", "r7", "r8"]);
  assert.deepEqual(items(["advisor"]), ["s5", "r0", "r8"]);
});

test("several roles add up", () => {
  assert.equal(mods(["teacher", "student"]), "p s r m");
  assert.ok(canMenu(["advisor", "faculty"], "c1"));
});

test("import history follows the import menu", () => {
  assert.ok(canMenu(["faculty"], "c3h"));
  assert.ok(!canMenu(["teacher"], "c3h"));
});

test("detail pages belong to their menu", () => {
  assert.equal(menuOfPath("/import/abc123"), "c3");
  assert.equal(menuOfPath("/import/history"), "c3h");
  assert.equal(menuOfPath("/curricula/7"), "c1");
  assert.equal(menuOfPath("/importer"), undefined);
});

test("landing page is the first built page the user may open", () => {
  assert.equal(builtPages(["admin"])[0]?.href, "/curricula");
  assert.deepEqual(builtPages(["student"]), []);
});

test("every role of the API has an access rule and every menu id is unique", () => {
  for (const r of ["admin", "central", "curator", "faculty", "evaluator", "teacher", "advisor", "student", "exec"]) {
    assert.ok(ROLE_ACCESS[r], r);
  }
  const ids = NAV.flatMap((m) => m.secs.flatMap((s) => s.items.map((i) => i.id)));
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids.length, 40); // 39 menus of the mock + import history (US-M1-21)
});
