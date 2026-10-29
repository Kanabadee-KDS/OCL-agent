// Role names mirror apps/api/src/ocl_api/perms.py (ROLES); groups made on the roles page come
// with their names in the session (roleNames). What a user may do is never decided here:
// menus come as `session.user.perms` (lib/nav.ts canMenu), workflow steps from the API.
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
/** Group names for display; `names` (from the API) covers the groups made on the roles page. */
export const roleLabel = (roles: string[] | undefined, names?: Record<string, string>) =>
  (roles ?? []).map((r) => names?.[r] ?? ROLES[r] ?? r).join(" · ") || "ยังไม่มีสิทธิ์";
