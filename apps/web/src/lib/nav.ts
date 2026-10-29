// Menus of the customer's mock (samples/ui-mock.html: NAV). Who sees which menu comes from the
// API as `perms` (role_perms, FS-1a), not from here. A menu with `href` is built; the rest show
// as "อยู่ระหว่างพัฒนา" until their FS phase (docs/plan.md). No imports: node --test runs it.

export type NavItem = {
  id: string; // the mock's menu id (c1, p2, ...); also the permission key of the menu
  label: string;
  route: string; // the mock's route, as named in docs/brd/91-traceability.md
  tag?: "ใหม่" | "เสนอเพิ่ม";
  href?: string; // app path once the page exists
  phase?: string; // FS phase that builds it
  inherits?: string; // shown whenever this other menu is shown (pages added beyond the mock)
};
export type NavSection = { cap: string; items: NavItem[] };
export type NavModule = { k: string; label: string; icon: string; secs: NavSection[] };

export const NAV: NavModule[] = [
  {
    k: "d", label: "แดชบอร์ด", icon: "chart", secs: [
      { cap: "ติดตามการบันทึกและสถิติ", items: [{ id: "d1", label: "หลักสูตร", route: "dash-cur", href: "/dashboard" }] },
    ],
  },
  {
    k: "c", label: "บริหารข้อมูลหลักสูตร", icon: "book", secs: [
      { cap: "คู่มือหลักสูตร", items: [
        { id: "c1", label: "คู่มือหลักสูตร", route: "cur", href: "/curricula" },
        { id: "c1b", label: "ตรวจสอบและบันทึก PLO โดยคณะ", route: "fac-plo", tag: "ใหม่", href: "/curricula/review" },
        { id: "c2", label: "งานปรับปรุงแก้ไขหลักสูตร (สมอ.08)", route: "smo", href: "/smo" },
      ] },
      { cap: "นำเข้าข้อมูลเล่มหลักสูตรด้วย AI", items: [
        { id: "c3", label: "นำเข้าข้อมูลเล่มหลักสูตร", route: "import", href: "/import" },
        { id: "c3h", label: "ประวัติการนำเข้าทั้งหมด", route: "import", href: "/import/history", inherits: "c3" },
      ] },
      { cap: "ข้อมูลหลัก (Master)", items: [
        { id: "c5", label: "บริหารรายวิชา", route: "course-master", tag: "ใหม่", href: "/courses" },
        { id: "c4", label: "บริหารบุคคลภายนอก", route: "ext-person", tag: "ใหม่", href: "/persons" },
      ] },
    ],
  },
  {
    k: "p", label: "แผนการจัดการเรียนรู้รายวิชา/ชุดวิชา", icon: "plan", secs: [
      { cap: "กำหนดผู้บันทึก", items: [{ id: "p1", label: "กำหนดผู้บันทึกแผนและรายงานผลฯ", route: "plan-assign", phase: "FS-4" }] },
      { cap: "บันทึกแผน/รายงานการจัดการเรียนรู้", items: [
        { id: "p2", label: "บันทึกแผนการจัดการเรียนรู้", route: "plan", phase: "FS-4" },
        { id: "p4", label: "บันทึกรายงานการจัดการการเรียนรู้", route: "rep", phase: "FS-4" },
      ] },
    ],
  },
  {
    k: "s", label: "Skill Transcript", icon: "skill", secs: [
      { cap: "ตั้งค่าฐานข้อมูลพื้นฐาน", items: [{ id: "s1", label: "บริหารฐานข้อมูล Skill", route: "skill-db", phase: "FS-5" }] },
      { cap: "ตั้งค่าการบันทึกข้อมูล", items: [
        { id: "s2", label: "กำหนดผู้บันทึกแผนการประเมิน Skill", route: "skill-assign", phase: "FS-5" },
        { id: "s2b", label: "กำหนด Skill ตามหลักสูตร", route: "skill-cur", tag: "ใหม่", phase: "FS-5" },
        { id: "s3", label: "กำหนดรายวิชาประเมิน Skill", route: "skill-map", phase: "FS-5" },
      ] },
      { cap: "บันทึกการประเมิน Skill", items: [{ id: "s4", label: "บันทึกประเมิน Skill", route: "assess", phase: "FS-5" }] },
      { cap: "ติดตามการประเมิน Skill", items: [
        { id: "s5", label: "Skill Portfolio", route: "portfolio", phase: "FS-5" },
        { id: "s6", label: "ออกเอกสาร Skill Transcript", route: "issue", tag: "เสนอเพิ่ม", phase: "FS-5" },
      ] },
    ],
  },
  {
    k: "q", label: "ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", icon: "qa", secs: [
      { cap: "ตั้งค่าการประเมิน", items: [
        { id: "q1", label: "รอบการประเมิน", route: "qa-rounds", phase: "FS-6" },
        { id: "q2", label: "เกณฑ์และข้อคำถาม", route: "qa-criteria", phase: "FS-6" },
        { id: "q1b", label: "กำหนดผู้บันทึกและผู้ยืนยันข้อมูล", route: "qa-assign", tag: "ใหม่", phase: "FS-6" },
      ] },
      { cap: "ตรวจสอบและประเมิน", items: [
        { id: "q3", label: "ตรวจสอบข้อมูลองค์ประกอบที่ 1", route: "qa-check", phase: "FS-6" },
        { id: "q4", label: "สรุปผลการประเมิน", route: "qa-result", phase: "FS-6" },
      ] },
    ],
  },
  {
    k: "r", label: "รายงาน", icon: "chart", secs: [
      { cap: "ภาพรวม", items: [{ id: "r0", label: "ศูนย์รายงาน", route: "reports", phase: "FS-7" }] },
      { cap: "ติดตามการดำเนินงาน", items: [
        { id: "r1", label: "ติดตามการบันทึกแผน/ผลฯ", route: "rpt", phase: "FS-7" },
        { id: "r2", label: "ความครบถ้วนการประเมิน Skill", route: "rpt", phase: "FS-7" },
        { id: "r3", label: "สถานะคู่มือหลักสูตร/สมอ.08", route: "rpt", phase: "FS-7" },
      ] },
      { cap: "ผลลัพธ์ทักษะ", items: [
        { id: "r4", label: "สรุปภาพรวมทักษะนิสิต", route: "rpt", phase: "FS-7" },
        { id: "r5", label: "สถิติตามกลุ่มผู้เรียน", route: "rpt", phase: "FS-7" },
        { id: "r6", label: "เปรียบเทียบและแนวโน้มทักษะ", route: "rpt", phase: "FS-7" },
      ] },
      { cap: "รายบุคคลและเอกสาร", items: [
        { id: "r7", label: "ผลคะแนน Skill รายวิชา", route: "rpt", phase: "FS-7" },
        { id: "r8", label: "ผลลัพธ์รายบุคคล", route: "rpt", phase: "FS-7" },
        { id: "r9", label: "ทะเบียนการออก Skill Transcript", route: "rpt", phase: "FS-7" },
      ] },
      { cap: "หลักสูตรและประกันคุณภาพ", items: [
        { id: "ra", label: "ผลการตรวจสอบข้อมูลหลักสูตร", route: "rpt", phase: "FS-7" },
        { id: "rb", label: "สถิติหลักสูตร (สาธารณะ)", route: "rpt", phase: "FS-7" },
        { id: "rc", label: "รายงานคู่มือหลักสูตร (Excel)", route: "rpt", phase: "FS-7" },
      ] },
    ],
  },
  {
    k: "u", label: "บริหารจัดการสิทธิ์", icon: "lock", secs: [
      { cap: "บริหารกลุ่มสิทธิ์", items: [
        { id: "u1", label: "กำหนดกลุ่มสิทธิ์การใช้งาน", route: "roles", href: "/roles" },
        { id: "u2", label: "กำหนดการตั้งค่าการอนุมัติ", route: "approval", href: "/approval" },
      ] },
      { cap: "บริหารผู้ใช้งาน", items: [{ id: "u3", label: "กำหนดผู้ใช้งาน", route: "users", href: "/users" }] },
    ],
  },
  {
    k: "m", label: "สำหรับนิสิต", icon: "user", secs: [
      { cap: "ผลทักษะของฉัน", items: [
        { id: "m1", label: "Skill Portfolio ของฉัน", route: "me", phase: "FS-5" },
        { id: "m2", label: "Skill Transcript ของฉัน", route: "my-transcript", phase: "FS-5" },
      ] },
    ],
  },
];

/** Menu id -> actions the user holds (view, add, edit, delete, approve, print), from the API
 *  (ocl_api.perms / role_perms) at sign-in and at every minute's re-check (auth.ts). */
export type Perms = Readonly<Record<string, readonly string[]>>;

function itemOf(id: string): NavItem | undefined {
  for (const m of NAV) for (const s of m.secs) for (const i of s.items) if (i.id === id) return i;
  return undefined;
}

/** Whether the user holds `action` on menu `id` (the union of all their groups). */
export function canMenu(perms: Perms | undefined, id: string, action = "view"): boolean {
  const item = itemOf(id);
  if (!item) return false;
  if (item.inherits) return canMenu(perms, item.inherits, action);
  return !!perms?.[id]?.includes(action);
}

/** The menu tree trimmed to what the user may see; empty sections and modules dropped. */
export function visibleNav(perms: Perms | undefined): NavModule[] {
  return NAV.map((m) => ({
    ...m,
    secs: m.secs
      .map((s) => ({ ...s, items: s.items.filter((i) => canMenu(perms, i.id)) }))
      .filter((s) => s.items.length > 0),
  })).filter((m) => m.secs.length > 0);
}

// built pages below a menu (detail pages highlight their parent menu, like the mock's ROUTE_NAV)
const PATH_MENU: [string, string][] = [
  ["/dashboard", "d1"],
  ["/import/history", "c3h"],
  ["/import", "c3"],
  ["/curricula/review", "c1b"],
  ["/curricula", "c1"],
  ["/courses", "c5"],
  ["/persons", "c4"],
  ["/smo", "c2"],
  ["/roles", "u1"],
  ["/users", "u3"],
  ["/approval", "u2"],
];

/** The menu a path belongs to, for highlighting and for the per-page permission check. */
export function menuOfPath(path: string): string | undefined {
  return PATH_MENU.find(([p]) => path === p || path.startsWith(p + "/"))?.[1];
}

/** Built pages the user may open, in menu order: the first one is their landing page. */
export function builtPages(perms: Perms | undefined): NavItem[] {
  return visibleNav(perms).flatMap((m) => m.secs.flatMap((s) => s.items.filter((i) => i.href)));
}
