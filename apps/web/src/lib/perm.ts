// Mirror of apps/api/src/ocl_api/auth.py (ROLES / PERMISSIONS): keep both in sync.
export const ROLES: Record<string, string> = {
  admin: "ผู้ดูแลระบบ",
  central: "ผู้ดูแลส่วนกลาง",
  curator: "ผู้ตรวจสอบระดับหลักสูตร",
  faculty: "ผู้ตรวจสอบระดับส่วนงาน",
  evaluator: "ผู้ประเมินหลักสูตร",
  teacher: "อาจารย์ผู้สอน",
  advisor: "อาจารย์ที่ปรึกษา",
  student: "นิสิต",
  exec: "ผู้บริหาร",
};
export const PERMISSIONS: Record<string, string[]> = {
  import_read: ["admin", "central", "curator", "faculty"],
  import_write: ["admin", "central", "curator"],
  users_manage: ["admin", "central"],
};
export const can = (roles: string[] | undefined, perm: string) => (roles ?? []).some((r) => PERMISSIONS[perm]?.includes(r));
export const roleLabel = (roles: string[] | undefined) => (roles ?? []).map((r) => ROLES[r] ?? r).join(" · ") || "ยังไม่มีสิทธิ์";
