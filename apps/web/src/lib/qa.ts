// ประเมินผลหลักสูตร (FS-6): the rules the pages show, the same the API applies (ocl_api.qa).
// No imports: node --test runs it.

export const RESULT_TH: Record<string, string> = { pass: "ผ่าน", fail: "ไม่ผ่าน", pending: "รอพิจารณา", na: "ไม่เกี่ยวข้อง", none: "ยังไม่ประเมิน" };
export const RESULT_KIND: Record<string, "ok" | "red" | "warn" | "grey"> = { pass: "ok", fail: "red", pending: "warn", na: "grey", none: "grey" };
export const DATA_KIND: Record<string, "grey" | "warn" | "info" | "ok"> = { none: "grey", doing: "warn", sent: "info", confirmed: "ok" };
export const ROUND_KIND: Record<string, "info" | "ok" | "grey"> = { draft: "info", open: "ok", closed: "grey" };

/** BR-M4-01: ผ่าน when every applicable item passes, ไม่ผ่าน when one fails, else รอพิจารณา. */
export function finalOf(results: Record<string, string | undefined>): "pass" | "fail" | "pending" {
  const got = Object.values(results).filter((r) => r !== "na");
  if (got.length && got.every((r) => r === "pass")) return "pass";
  if (got.some((r) => r === "fail")) return "fail";
  return "pending";
}

/** The round a page starts on: the one kept for the session, else the open one, else the newest. */
export function pickRound(rounds: readonly { id: number; status: string }[], kept: number | null): number | null {
  if (kept && rounds.some((r) => r.id === kept)) return kept;
  return (rounds.find((r) => r.status === "open") ?? rounds[0])?.id ?? null;
}

/** BR-M4-05: the year of the announcement a curriculum names ("ประกาศ อว. 2565 (ตรี)"). */
export function setOf(standard: string | null | undefined, sets: readonly number[] = [2548, 2558, 2565]): number {
  const m = (standard ?? "").match(/25\d\d/);
  const y = m ? Number(m[0]) : 0;
  return sets.includes(y) ? y : Math.max(...sets);
}
