// Editing the steps of an approval flow (flow-edit), same rules as the API (ocl_api.flows):
// the last step approves or signs, a fixed flow keeps its number of steps. No imports.

export type Step = { roles: string[]; position: string | null; label: string; action: string; days: number; on_reject: string };

export function move<T>(list: readonly T[], i: number, by: -1 | 1): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return [...list];
  const out = [...list];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

export const blankStep = (): Step => ({ roles: [], position: null, label: "", action: "review", days: 3, on_reject: "sender" });

/** What the API would refuse, said before saving (empty = fine). */
export function problems(steps: readonly Step[], fixed: number | null): string[] {
  const out: string[] = [];
  if (!steps.length) out.push("ต้องมีอย่างน้อย 1 ขั้นตอน");
  if (fixed && steps.length !== fixed) out.push(`ขั้นตอนนี้ต้องมี ${fixed} ขั้นตามสถานะของงาน`);
  const last = steps[steps.length - 1];
  if (last && !["approve", "sign"].includes(last.action)) out.push("ขั้นสุดท้ายต้องเป็นการอนุมัติหรือลงนาม");
  steps.forEach((s, i) => {
    if (!s.roles.length && !(s.position ?? "").trim()) out.push(`ขั้นที่ ${i + 1} ยังไม่มีผู้ดำเนินการ`);
    if (s.days < 0 || s.days > 365) out.push(`ขั้นที่ ${i + 1} ระยะเวลาต้องอยู่ระหว่าง 0–365 วันทำการ`);
  });
  return out;
}
