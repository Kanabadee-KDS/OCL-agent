// Reports R01–R14 (FS-7 · BRD 05): which menu guards each one (as ocl_api.reports.CATALOG) and
// how a cell is shown. No imports: node --test runs it.

export const REPORT_MENU: Readonly<Record<string, string>> = {
  R01: "r1", R02: "r2", R03: "r3", R04: "r4", R05: "r5", R06: "r6", R07: "r7",
  R08: "r8", R09: "r9", R10: "ra", R11: "rb", R12: "rc", R13: "r0", R14: "r0",
};

/** Filters that narrow the rows, so an empty choice means every row; the others pick one. */
export const NARROWING = new Set(["unit", "faculty", "program", "entry"]);

/** The report's link for this user: R11 opens its public page when the user lacks its menu. */
export function reportHref(code: string, can: (menu: string) => boolean): string {
  return code === "R11" && !can("rb") ? "/stats" : `/rpt/${code}`;
}

export function cellText(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "–";
  return typeof v === "number" ? v.toLocaleString("th-TH", { maximumFractionDigits: 2 }) : v;
}
