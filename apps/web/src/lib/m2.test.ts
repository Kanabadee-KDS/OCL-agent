// node --test src/lib/m2.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { gradeRows, pctSum, sentPct, slugOf } from "./m2.ts";

test("the numbers the plan and report forms show", () => {
  assert.equal(pctSum([{ pct: 60 }, { pct: "40" }, {}]), 100);
  const g = gradeRows({ A: 3, B: "1", E: -2 }, 1, 5);
  assert.deepEqual([g.total, g.remaining, g.over, g.rows[0].pct, g.rows.at(-1)!.n], [4, 4, false, 75, 0]);
  assert.equal(gradeRows({ A: 5 }, 1, 5).over, true, "more students than enrolled");
  assert.equal(sentPct(["sent", "draft", "published", "none"]), 50);
  assert.equal(slugOf("2/2569"), "2-2569");
});
