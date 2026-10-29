// node --test src/lib/chart.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { labelAnchor, radarPoint, radarPolygon, radarRing } from "./chart.ts";

test("first axis points straight up, values scale to the radius", () => {
  assert.deepEqual(radarPoint(0, 4, 1).map((v) => Math.round(v)), [160, 50]);
  assert.deepEqual(radarPoint(1, 4, 1).map((v) => Math.round(v)), [260, 150]);
  assert.equal(radarPolygon([5, 0, 0, 0]).split(" ")[0], "160.0,50.0");
  assert.equal(radarPolygon([2.5, 0, 0, 0]).split(" ")[0], "160.0,100.0");
});

test("values outside 0–5 are clamped", () => {
  assert.equal(radarPolygon([9, -1, 0, 0]), radarPolygon([5, 0, 0, 0]));
});

test("rings have one point per axis and labels sit away from the centre", () => {
  assert.equal(radarRing(6, 0.5).split(" ").length, 6);
  assert.equal(labelAnchor([160, 20]), "middle");
  assert.equal(labelAnchor([290, 150]), "start");
  assert.equal(labelAnchor([30, 150]), "end");
});
