// The role-edit matrix (menu × ดู/เพิ่ม/แก้ไข/ลบ/อนุมัติ/พิมพ์), same rule as the API
// (ocl_api.roles.normalize): any action brings "view" with it, removing "view" clears the menu.
// No imports: node --test runs it.

export const ACTION_ORDER = ["view", "add", "edit", "delete", "approve", "print"] as const;
export type Matrix = Record<string, string[]>;

const sorted = (acts: Iterable<string>) => ACTION_ORDER.filter((a) => [...acts].includes(a));

/** Tick or untick one action of one menu. */
export function toggle(m: Matrix, menu: string, action: string, on: boolean): Matrix {
  const cur = new Set(m[menu] ?? []);
  if (on) {
    cur.add(action);
    cur.add("view");
  } else if (action === "view") {
    cur.clear();
  } else {
    cur.delete(action);
  }
  const out = { ...m };
  if (cur.size) out[menu] = sorted(cur);
  else delete out[menu];
  return out;
}

/** Tick all six actions of a menu, or clear it. */
export function toggleRow(m: Matrix, menu: string, on: boolean): Matrix {
  const out = { ...m };
  if (on) out[menu] = [...ACTION_ORDER];
  else delete out[menu];
  return out;
}

/** How many menu-action ticks differ: the save button says how much is unsaved. */
export function changes(a: Matrix, b: Matrix): number {
  const pairs = (m: Matrix) => new Set(Object.entries(m).flatMap(([k, v]) => v.map((x) => `${k}:${x}`)));
  const pa = pairs(a);
  const pb = pairs(b);
  return [...pa].filter((x) => !pb.has(x)).length + [...pb].filter((x) => !pa.has(x)).length;
}
