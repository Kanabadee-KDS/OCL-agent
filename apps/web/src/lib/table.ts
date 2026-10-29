// List logic shared by every table of the mock: search box, select filters, sorting and the
// "แสดง x–y จาก n รายการ · ‹ 1 2 … 9 ›" pager. Pure functions, no imports: node --test runs them.

/** Thai-aware text match: case-insensitive, ignores spaces (Thai books mix spaced and unspaced names). */
export function matches(text: unknown, query: string): boolean {
  const q = query.replace(/\s+/g, "").toLowerCase();
  if (!q) return true;
  return String(text ?? "").replace(/\s+/g, "").toLowerCase().includes(q);
}

/** Rows whose searchable text contains the query and that pass every set filter (empty value = all). */
export function filterRows<T>(
  rows: readonly T[],
  query: string,
  searchText: (row: T) => string,
  filters: Record<string, string> = {},
  filterValue: (row: T, key: string) => string | null | undefined = () => undefined,
): T[] {
  const active = Object.entries(filters).filter(([, v]) => v !== "");
  return rows.filter(
    (r) => matches(searchText(r), query) && active.every(([k, v]) => String(filterValue(r, k) ?? "") === v),
  );
}

export type SortDir = "asc" | "desc";

/** Stable sort; numbers compare as numbers, text with Thai collation, empty values last. */
export function sortRows<T>(rows: readonly T[], value: (row: T) => unknown, dir: SortDir = "asc"): T[] {
  const coll = new Intl.Collator("th", { numeric: true, sensitivity: "base" });
  const sign = dir === "asc" ? 1 : -1;
  return rows
    .map((r, i) => ({ r, i, v: value(r) }))
    .sort((a, b) => {
      const ea = a.v === null || a.v === undefined || a.v === "";
      const eb = b.v === null || b.v === undefined || b.v === "";
      if (ea || eb) return ea === eb ? a.i - b.i : ea ? 1 : -1;
      const c = typeof a.v === "number" && typeof b.v === "number" ? a.v - b.v : coll.compare(String(a.v), String(b.v));
      return c !== 0 ? c * sign : a.i - b.i;
    })
    .map((x) => x.r);
}

export type Page<T> = { rows: T[]; page: number; pages: number; total: number; from: number; to: number };

/** One page of rows (1-based); a page past the end clamps to the last page. */
export function paginate<T>(rows: readonly T[], page: number, size: number): Page<T> {
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const p = Math.min(Math.max(1, Math.floor(page) || 1), pages);
  const start = (p - 1) * size;
  const slice = rows.slice(start, start + size);
  return { rows: slice, page: p, pages, total, from: total ? start + 1 : 0, to: start + slice.length };
}

/** Page numbers for the pager: first, last, current ± 1, with "…" for gaps (like the mock's ‹ 1 2 3 … 35 ›). */
export function pageList(page: number, pages: number): (number | "…")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const keep = new Set([1, 2, pages - 1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const out: (number | "…")[] = [];
  let prev = 0;
  for (const n of [...keep].sort((a, b) => a - b)) {
    if (n - prev > 1) out.push("…");
    out.push(n);
    prev = n;
  }
  return out;
}

/** Distinct non-empty values of a column, sorted, for a select filter. */
export function options<T>(rows: readonly T[], value: (row: T) => string | null | undefined): string[] {
  const coll = new Intl.Collator("th", { numeric: true });
  return [...new Set(rows.map(value).filter((v): v is string => !!v))].sort(coll.compare);
}
