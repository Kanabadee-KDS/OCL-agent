// node --test src/lib/llm.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { llmSummary } from "./llm.ts";

const used = { calls: 2, prompt_tokens: 900, completion_tokens: 80, seconds: 4.2, model: "gemma4:26b" };

test("requests made: count, model and tokens", () => {
  assert.equal(llmSummary("ollama", used).value, "2 คำขอ");
  assert.equal(llmSummary("ollama", used).detail, "gemma4:26b · 900/80 tokens · 4.2 s");
});

test("an AI was chosen but the rules read everything (R2 M-11 M-12)", () => {
  const s = llmSummary("gemini", null);
  assert.equal(s.value, "0 คำขอ");
  assert.match(s.detail, /เลือก Cloud AI · Gemini · ไม่ต้องเรียก/);
  assert.equal(llmSummary("ollama", { ...used, calls: 0 }).value, "0 คำขอ");
});

test("rules only", () => {
  assert.deepEqual(llmSummary("none", null), { value: "ไม่ใช้", detail: "อ่านด้วยกฎอย่างเดียว", short: "–" });
});
