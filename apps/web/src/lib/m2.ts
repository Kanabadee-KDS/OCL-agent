// แผน/รายงานการจัดการเรียนรู้ (FS-4): the arithmetic the forms show while typing, the same
// rules the API checks before a document may be sent (ocl_api.m2). No imports: node --test.

export const GRADES = ["A", "B+", "B", "C+", "C", "D+", "D", "E"] as const;
export const DONE = ["sent", "approved", "published"];
export const STATUS_KIND: Record<string, "grey" | "info" | "warn" | "red" | "ok"> = {
  none: "grey", draft: "info", sent: "warn", returned: "red", approved: "ok", published: "ok",
};

/** Sum of the CLO/MLO percentages (must be 100 to send). */
export const pctSum = (clos: readonly { pct?: unknown }[]) => Math.round(clos.reduce((a, c) => a + (Number(c.pct) || 0), 0) * 100) / 100;

/** Grade table of the report: count and % of the students who stayed, and the remaining check. */
export function gradeRows(counts: Record<string, unknown>, withdrawn: number, enrolled: number) {
  const n = GRADES.map((g) => Math.max(0, Math.floor(Number(counts[g]) || 0)));
  const total = n.reduce((a, b) => a + b, 0);
  return {
    rows: GRADES.map((g, i) => ({ grade: g, n: n[i], pct: total ? Math.round((n[i] * 1000) / total) / 10 : 0 })),
    total,
    remaining: enrolled - withdrawn,
    over: !!enrolled && total + withdrawn > enrolled,
  };
}

/** % sent for a set of statuses (sent + approved + published ÷ all). */
export const sentPct = (statuses: readonly string[]) => (statuses.length ? Math.round((statuses.filter((s) => DONE.includes(s)).length * 100) / statuses.length) : 0);

/** '2/2569' ↔ '2-2569' (a term in a URL). */
export const slugOf = (term: string) => term.replace("/", "-");
