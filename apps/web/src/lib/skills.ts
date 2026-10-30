// Skill Transcript (FS-5): the arithmetic the pages show while typing, the same rules the API
// applies (ocl_api.skills · ocl_api.assess). No imports: node --test runs it.

export const CATS = ["GS", "SS", "E", "C"] as const;
export type Cat = (typeof CATS)[number];
export const CAT_TH: Record<Cat, string> = { GS: "ทักษะทั่วไป", SS: "ทักษะเฉพาะ", E: "จริยธรรม", C: "คุณลักษณะ" };
export const CAT_EN: Record<Cat, string> = { GS: "Generic skills", SS: "Specific skills", E: "Ethics", C: "Characters" };
export const CAT_COLOR: Record<Cat, string> = { GS: "var(--gs)", SS: "var(--ss)", E: "var(--e)", C: "var(--c)" };
export const SET_KIND: Record<string, "grey" | "info" | "warn" | "red" | "ok"> = { none: "grey", draft: "info", sent: "warn", returned: "red", approved: "ok" };
export const ASSESS_KIND: Record<string, "grey" | "info" | "warn" | "ok"> = { todo: "grey", doing: "warn", wait: "info", ok: "ok" };
export const ASSESS_ACT: Record<string, string> = { todo: "เริ่มประเมิน", doing: "ประเมินต่อ", wait: "ยืนยันผล", ok: "ดูผล" };
export const GROUP_TH: Record<string, string> = { ready: "พร้อมออก", incomplete: "ผลประเมินไม่ครบ", ethics: "Ethics ไม่ผ่าน", issued: "ออกแล้ว" };

type Level = { min: number; max: number; en: string; th?: string };

/** BR-M3-02: the level whose range holds the score (ranges on 2 decimals). */
export function levelOf(score: number | null | undefined, levels: readonly Level[]): Level | null {
  if (score == null || !levels.length) return null;
  const s = Math.round(score * 100) / 100;
  return levels.find((l) => l.min <= s && s <= l.max) ?? (s > levels[levels.length - 1].max ? levels[levels.length - 1] : levels[0]);
}

/** BR-M3-01: the plain average, 2 decimals (null when nothing to average). */
export const avg = (xs: readonly number[]) => (xs.length ? Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 100) / 100 : null);

export const fmt2 = (n: number | null | undefined) => (n == null ? "–" : n.toFixed(2));

/** A score typed in the grid: "" = not assessed; otherwise 0–5, 2 decimals; NaN when invalid. */
export function parseScore(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n <= 5 ? Math.round(n * 100) / 100 : NaN;
}

/** Students with every skill scored (the grid's "ประเมินครบแล้ว"). */
export const completeCount = (sids: readonly string[], skills: readonly string[], scores: Record<string, Record<string, number | null | undefined>>) =>
  sids.filter((s) => skills.every((k) => scores[s]?.[k] != null)).length;

/** The mapping grid's counts: offered courses with a skill, points, skills not yet assessed anywhere. */
export function coverage(courses: readonly { code: string; offered: boolean }[], cells: Record<string, readonly string[]>, skills: readonly string[]) {
  const live = courses.filter((c) => c.offered);
  return {
    mapped: live.filter((c) => (cells[c.code] ?? []).length).length,
    points: live.reduce((a, c) => a + (cells[c.code] ?? []).length, 0),
    gaps: skills.filter((s) => !live.some((c) => (cells[c.code] ?? []).includes(s))),
  };
}

/** '2/2569' ↔ '2-2569' (a term in a URL). */
export const slugOf = (term: string) => term.replace("/", "-");
export const termOf = (slug: string) => slug.replace("-", "/");
