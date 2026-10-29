// node --test src/lib/smo.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { changes, inScope } from "./smo.ts";

test("the teacher comparison labels each row like the API", () => {
  const a = [{ name: "ก", pid: "1" }, { name: "ข", pid: "2" }, { name: "ค" }];
  const b = [{ name: "ก", pid: "1", rank: "ผศ." }, { name: "ค" }, { name: "ง", xid: "X001" }];
  assert.deepEqual(changes(a, b).map((c) => [c.change, (c.after ?? c.before)?.name]), [["แก้ไข", "ก"], ["เพิ่ม", "ง"], ["นำออก", "ข"]]);
  assert.deepEqual(changes(a, a), []);
  assert.equal(inScope({ group: "แขนง ก" }, { kind: "child", branch: "แขนง ข" }), false);
  assert.equal(inScope({ group: "แขนง ก" }, { kind: "mother" }), true);
});
