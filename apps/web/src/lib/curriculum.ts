// หมวด 3–4 of the คู่มือหลักสูตร (BRD 01 §4): PLO/KSEC, the structure tree, courses and the
// Curriculum Mapping, in the shapes the import writes (extract/plo, ksec, structure, courses,
// mapping). Pure functions so the editors stay small; node --test runs them.

export type SubPlo = string;
export type Plo = { code: string; text: string; sub_plos?: SubPlo[] };
export type KsecItem = { code: string; category: string; subtype?: string | null; text: string };
/** KSEC of one PLO. A curriculum with several study plans (ป.โท แผน 1 / แผน 2) has one entry per
 *  plan and PLO: the same code appears once per `plan`, each with that plan's PLO text. */
export type KsecPlo = { code: string; plan?: string | null; text?: string; items: KsecItem[]; [k: string]: unknown };
export type Node = { number: string; name: string; level?: number; credits?: number | null; module?: boolean; description?: string | null; children?: Node[] };
export type Course = { code_th?: string; version?: number | null; code_en?: string | null; name_th?: string; name_en?: string | null; credits?: number | null; credit_text?: string | null; group?: string | null; node?: string | null; [k: string]: unknown };
export type KsecRow = { course_code: string; course_name?: string; group?: string; plos: string[]; by_column: Record<string, string[]>; ksec_codes: string[] };

export const CATS = ["K", "S", "E", "C"] as const;

export const ksecKey = (k: Pick<KsecPlo, "code" | "plan">) => `${k.plan ?? ""}|${k.code}`;
export const ksecLabel = (k: Pick<KsecPlo, "code" | "plan">) => (k.plan ? `${k.code} · ${k.plan}` : k.code);

/** The study plans the KSEC is split by, in book order ([null] when it is not split). */
export function plansOf(ksec: readonly KsecPlo[]): (string | null)[] {
  const plans = [...new Set(ksec.map((k) => k.plan ?? null))];
  return plans.length ? plans : [null];
}

/** ksec follows the PLO list: per plan, one entry per PLO code in PLO order. Without plans the
 *  text mirrors the PLO; a plan keeps its own wording of the PLO (the book words it per plan). */
export function syncKsec(plos: readonly Plo[], ksec: readonly KsecPlo[]): KsecPlo[] {
  return plansOf(ksec).flatMap((plan) =>
    plos.map((p) => {
      const old = ksec.find((k) => k.code === p.code && (k.plan ?? null) === plan);
      const base = { ...(old ?? { items: [] }), code: p.code, items: old?.items ?? [] };
      return plan ? { ...base, plan, text: old?.text || p.text } : { ...base, text: p.text };
    }),
  );
}

/** A PLO code changed: its KSEC (every plan) moves with it instead of being dropped. */
export const renameKsec = (ksec: readonly KsecPlo[], from: string, to: string) =>
  ksec.map((k) => (k.code === from ? { ...k, code: to } : k));

export const allCodes = (ksec: readonly KsecPlo[]) => ksec.flatMap((k) => k.items.map((i) => i.code)).filter(Boolean);

/** 3.3 ตารางสรุป: per PLO (and plan), the KSEC codes of each category. */
export function summary(ksec: readonly KsecPlo[]): { key: string; label: string; code: string; cells: Record<string, string[]> }[] {
  return ksec.map((k) => ({
    key: ksecKey(k),
    label: ksecLabel(k),
    code: k.code,
    cells: Object.fromEntries(CATS.map((c) => [c, k.items.filter((i) => i.category === c).map((i) => i.code)])),
  }));
}

/** Mapping columns: K1 S1 E1 C1 for PLO1, K2 … for PLO2 (the book's layout). */
export function mappingColumns(plos: readonly Plo[]): { plo: string; col: string; cat: string }[] {
  return plos.flatMap((p, i) => CATS.map((c) => ({ plo: p.code, col: `${c}${i + 1}`, cat: c })));
}

/** "1,4" in column K1 = K1-1, K1-4; and back. */
export function parseCell(text: string, col: string): string[] {
  return [...new Set(text.split(/[,\s]+/).map((x) => x.trim()).filter((x) => /^\d+$/.test(x)))]
    .sort((a, b) => Number(a) - Number(b))
    .map((n) => `${col}-${n}`);
}
export const formatCell = (codes: readonly string[] | undefined, col: string) =>
  (codes ?? []).filter((c) => c.startsWith(`${col}-`)).map((c) => c.slice(col.length + 1)).join(",");

/** One course's mapping after a cell changed: codes, and the PLOs it now serves. */
export function setCell(row: KsecRow, col: string, text: string, plos: readonly Plo[]): KsecRow {
  const by = { ...row.by_column, [col]: parseCell(text, col) };
  if (!by[col].length) delete by[col];
  const cols = mappingColumns(plos);
  const served = plos.filter((p) => cols.some((c) => c.plo === p.code && by[c.col]?.length)).map((p) => p.code);
  return { ...row, by_column: by, ksec_codes: Object.values(by).flat(), plos: served };
}

/** Every course has a mapping row (new courses start empty), in course order. */
export function mappingRows(courses: readonly Course[], rows: readonly KsecRow[]): KsecRow[] {
  return courses.map((c) => rows.find((r) => r.course_code === c.code_th) ?? { course_code: c.code_th ?? "", course_name: c.name_th, group: c.group ?? "", plos: [], by_column: {}, ksec_codes: [] });
}

// ---------- structure tree ----------

export function flatten(tree: readonly Node[], path: Node[] = []): { node: Node; path: Node[] }[] {
  return tree.flatMap((n) => [{ node: n, path }, ...flatten(n.children ?? [], [...path, n])]);
}

export const findNode = (tree: readonly Node[], number: string) => flatten(tree).find((x) => x.node.number === number);

export function mapNode(tree: readonly Node[], number: string, fn: (n: Node) => Node | null): Node[] {
  return tree.flatMap((n) => {
    if (n.number === number) {
      const out = fn(n);
      return out ? [out] : [];
    }
    return [{ ...n, children: mapNode(n.children ?? [], number, fn) }];
  });
}

/** Add a child group under `parent` (or a top-level หมวดวิชา when parent is null), numbered next. */
export function addNode(tree: readonly Node[], parent: string | null, name: string): Node[] {
  const siblings = parent ? findNode(tree, parent)?.node.children ?? [] : tree;
  const last = Math.max(0, ...siblings.map((s) => Number(s.number.split(".").pop()) || 0));
  const number = parent ? `${parent}.${last + 1}` : String(last + 1);
  const level = parent ? number.split(".").length : 1;
  const node: Node = { number, name, level, credits: null, children: [] };
  return parent ? mapNode(tree, parent, (p) => ({ ...p, children: [...(p.children ?? []), node] })) : [...tree, node];
}

/** Courses of a node: those linked to it by number. Imported courses carry only the book's
 *  group text (often a ชุดวิชา name, and "วิชาบังคับ" exists in several หมวด), so a name match
 *  would put them in the wrong place; they stay unlinked until someone picks the group. */
export function coursesOf(courses: readonly Course[], node: Node): Course[] {
  return courses.filter((c) => c.node === node.number);
}

/** The node a course is linked to, or null when nobody has picked one yet. */
export const nodeOf = (c: Course, tree: readonly Node[]) => (c.node && findNode(tree, c.node) ? c.node : null);

export const creditSum = (tree: readonly Node[]) => tree.reduce((a, n) => a + (Number(n.credits) || 0), 0);
