// สมอ.08 (FS-3c): the comparison of the old and new teacher lists, as the API computes it
// (ocl_api.smo.changes), so the form previews the change before it is saved. No imports:
// node --test runs it.

export type SmoStatus = "draft" | "pending" | "returned" | "approved";
export const SMO_KIND: Record<SmoStatus, "grey" | "warn" | "red" | "ok"> = { draft: "grey", pending: "warn", returned: "red", approved: "ok" };

export type Teacher = { name?: string; rank?: string | null; pid?: string | null; xid?: string | null; highest_level?: string | null; responsible?: boolean; group?: string | null; chair?: boolean; [k: string]: unknown };
export type Change = { change: "เพิ่ม" | "แก้ไข" | "นำออก"; before: Teacher | null; after: Teacher | null };

const FIELDS = ["name", "rank", "highest_level", "responsible", "group", "chair"] as const;
export const teacherKey = (t: Teacher) => t.pid || t.xid || "name:" + String(t.name ?? "").replace(/\s/g, "");

export function changes(before: readonly Teacher[], after: readonly Teacher[]): Change[] {
  const old = new Map(before.map((t) => [teacherKey(t), t]));
  const now = new Map(after.map((t) => [teacherKey(t), t]));
  const out: Change[] = [];
  for (const [k, t] of now) {
    const b = old.get(k);
    if (!b) out.push({ change: "เพิ่ม", before: null, after: t });
    else if (FIELDS.some((f) => (b[f] ?? null) !== (t[f] ?? null))) out.push({ change: "แก้ไข", before: b, after: t });
  }
  for (const [k, t] of old) if (!now.has(k)) out.push({ change: "นำออก", before: t, after: null });
  return out;
}

/** เล่มแม่: everyone · เล่มลูก: the teachers of that แขนง (0.2 `group`). */
export const inScope = (t: Teacher, scope: { kind: string; branch?: string }) => scope.kind !== "child" || (t.group ?? "") === (scope.branch ?? "");
