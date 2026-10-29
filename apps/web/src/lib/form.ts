// Reading and writing the คู่มือหลักสูตร form by the `path` each field declares in the API's
// spec (ocl_api.curriculum_form): "info.values.name_th", "plan.plans", "appr.approvals"...
// Immutable, so React sees every change. No imports: node --test runs it.

type Obj = Record<string, unknown>;

export function getPath(data: unknown, path: string): unknown {
  let cur: unknown = data;
  for (const p of path.split(".")) {
    if (Array.isArray(cur) && /^\d+$/.test(p)) cur = cur[Number(p)];
    else if (cur && typeof cur === "object") cur = (cur as Obj)[p];
    else return undefined;
  }
  return cur;
}

export function setPath<T>(data: T, path: string, value: unknown): T {
  const [head, ...rest] = path.split(".");
  const base = (data && typeof data === "object" ? data : {}) as Obj;
  if (Array.isArray(base) && /^\d+$/.test(head)) {
    const out = [...base];
    out[Number(head)] = rest.length ? setPath(out[Number(head)], rest.join("."), value) : value;
    return out as T;
  }
  return { ...base, [head]: rest.length ? setPath(base[head], rest.join("."), value) : value } as T;
}

/** A table cell or field value as text for an input; dates may be the import's {iso, text}. */
export function asInput(v: unknown, kind: string): string {
  if (v === null || v === undefined) return "";
  if (kind === "date" && typeof v === "object") return String((v as Obj).iso ?? "");
  return String(v);
}

/** The value an input gives back, typed by kind ("" clears it). */
export function fromInput(s: string, kind: string): unknown {
  if (s === "") return null;
  if (kind === "int") return Number.isFinite(Number(s)) ? Number(s) : null;
  return s;
}

/** Sum per year of the intake plan rows (the mock's automatic total). */
export function columnTotals(rows: readonly { values?: readonly (number | null)[] }[], years: number): number[] {
  return Array.from({ length: years }, (_, i) => rows.reduce((a, r) => a + (Number(r.values?.[i]) || 0), 0));
}
