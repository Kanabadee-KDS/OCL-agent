// "" (empty) = same origin (behind Caddy); unset = local dev API
// "" or unset = through the Next.js proxy (/api/ocl) which signs the user token for FastAPI
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "/api/ocl").replace(/\/$/, "");

export type Job = {
  id: string;
  filename: string;
  size: number;
  provider: string;
  target: string | null;
  status: "queued" | "ingesting" | "extracting" | "review" | "done" | "failed";
  step: number;
  progress: string;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  timings: Record<string, number>;
  parts: string[];
  confirmed: Record<string, string>;
  confirmed_count: number;
  parts_total: number;
  all_parts: string[];
  counts: { ingest?: { pages: number; tables: number; images: number; chapters: string[]; appendices: string[]; scanned_pages?: number; ocr_pages?: number }; parts?: Record<string, number> };
  llm: { calls: number; prompt_tokens: number; completion_tokens: number; seconds: number; model?: string } | null;
  checks_recomputed_at?: string | null;
  edited_parts?: string[];
};

export type Meta = { confidence: "high" | "medium" | "low"; source: { page: number | null; snippet: string }; by: string; inferred?: boolean; note?: string; alternatives?: { text: string; page: number | null; from: string | null }[] };

export type Part = {
  part: string;
  available: boolean;
  data: Record<string, unknown> | null;
  extracted?: Record<string, unknown>;
  notes?: string[];
  llm?: Record<string, unknown> | null;
  edited?: boolean;
  edit_count?: number;
  confirmed?: boolean;
  confirmed_at?: string | null;
  note?: string;
};

export type Check = { key: string; status: "pass" | "warn" | "fail" | "info"; message: string; part: string };

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}
const enc = encodeURIComponent;

export const api = {
  health: () => fetch(`${API_BASE}/health`).then(j<Record<string, unknown>>),
  list: () => fetch(`${API_BASE}/api/imports`, { cache: "no-store" }).then(j<Job[]>),
  create: (file: File, provider: string, target?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("provider", provider);
    if (target) fd.append("target", target);
    return fetch(`${API_BASE}/api/imports`, { method: "POST", body: fd }).then(j<Job>);
  },
  get: (id: string) => fetch(`${API_BASE}/api/imports/${id}`, { cache: "no-store" }).then(j<Job>),
  part: (id: string, key: string) => fetch(`${API_BASE}/api/imports/${id}/parts/${key}`, { cache: "no-store" }).then(j<Part>),
  savePart: (id: string, key: string, data: unknown, confirm: boolean) =>
    fetch(`${API_BASE}/api/imports/${id}/parts/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, confirm, by: "poc" }),
    }).then(j<Part>),
  finalize: (id: string) => fetch(`${API_BASE}/api/imports/${id}/finalize`, { method: "POST" }).then(j<Job>),
  // สกัดใหม่ (FS-3e): parts null = every part; the parts read again must be confirmed again
  reextract: (id: string, parts: string[] | null, provider: string) =>
    fetch(`${API_BASE}/api/imports/${id}/reextract`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parts, provider }) }).then(j<Job>),
  checks: (id: string) => fetch(`${API_BASE}/api/imports/${id}/checks`, { cache: "no-store" }).then(j<Check[]>),
  source: (id: string, page: number) =>
    fetch(`${API_BASE}/api/imports/${id}/source?page=${page}`, { cache: "no-store" }).then(
      j<{ page: number; pages: number | null; blocks: Array<Record<string, unknown>>; page_image: string | null }>,
    ),
  fileUrl: (id: string, path: string) => `${API_BASE}/api/imports/${id}/files/${path}`,
  // Markdown editor (FS-3f): the book, its chapters and the 10 parts; the edit wins on read
  markdown: (id: string) => fetch(`${API_BASE}/api/imports/${id}/markdown`, { cache: "no-store" }).then(j<{ files: { path: string; edited: boolean }[]; log: { ts: string; by: string; path: string; chars: number }[] }>),
  saveMarkdown: (id: string, path: string, content: string) =>
    fetch(`${API_BASE}/api/imports/${id}/markdown`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content }) }).then(j<{ files: { path: string; edited: boolean }[] }>),
  fileText: (id: string, path: string) => fetch(`${API_BASE}/api/imports/${id}/files/${path}`, { cache: "no-store" }).then((r) => (r.ok ? r.text() : "")),
};

export const PART_LABELS: Record<string, [string, string]> = {
  info: ["ข้อมูลหลัก + หมวด 1 ข้อมูลทั่วไป", "เล่มหมวด 1 ข้อ 1–10, 13"],
  teachers: ["อาจารย์หลักสูตร (จับคู่ HURIS)", "หมวด 1 ข้อ 11–12"],
  plan: ["หมวด 2 แผนรับนิสิต + รูปแบบการสอน", "หมวด 2 ข้อ 4, หมวด 5"],
  plo: ["PLO", "หมวด 3 ข้อ 1"],
  ksec: ["KSEC ตาม PLO", "หมวด 3 ตาราง"],
  structure: ["โครงสร้างหลักสูตร (หมวด)", "หมวด 4 ข้อ 1–2"],
  modules: ["ชุดวิชา + คำอธิบายชุดวิชา", "หมวด 4 ข้อ 3"],
  courses: ["รายวิชา + คำอธิบายรายวิชา + Version", "หมวด 4 ข้อ 2–3"],
  mapping: ["Curriculum Mapping (PLO + KSEC)", "หมวด 4 ข้อ 4.1–4.2"],
  appr: ["สถานภาพและมติอนุมัติ", "หมวด 1 ข้อ 13"],
};

/** Import job status → Thai label + pill colour (shared by /import, /import/history). */
export const JOB_STATUS_TH: Record<Job["status"], [string, "ok" | "warn" | "red" | "info" | "grey"]> = {
  queued: ["รอคิว", "grey"],
  ingesting: ["กำลังแปลงไฟล์", "info"],
  extracting: ["AI กำลังสกัด", "info"],
  review: ["รอตรวจสอบ", "warn"],
  done: ["บันทึกแล้ว", "ok"],
  failed: ["ล้มเหลว", "red"],
};
export const providerLabel = (p: string) => (p === "none" ? "อ่านด้วยกฎ" : p === "ollama" ? "Local AI · Gemma" : p === "gemini" ? "Cloud AI · Gemini" : p);
/** A job has a summary (timings, LLM usage, per-part table) once extraction finished. */
export const hasSummary = (j: Pick<Job, "status">) => j.status === "review" || j.status === "done";

export const fmtBytes = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`);
/** "YYYY-MM-DD HH:MM" in Asia/Bangkok when the stamp carries a zone (Postgres timestamptz); naive stamps are shown as-is. */
export const fmtTime = (iso: string | null | undefined) => {
  if (!iso) return "–";
  if (!/[+-]\d\d:\d\d$|Z$/.test(iso)) return iso.replace("T", " ").slice(0, 16);
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.replace("T", " ").slice(0, 16);
  const p = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
  return p.replace("T", " ").slice(0, 16);
};

// ---------- คู่มือหลักสูตร workflow ----------
export type CurriculumRow = {
  id: number; job_id: string | null; program_code: string | null; name_th: string | null; level: string | null; start_year: number | null;
  status: "import" | "review" | "verified" | "published"; status_th: string; faculty_checked: Record<string, boolean>;
  review_due_at: string | null; finalized_at: string | null; updated_at: string | null; faculty: string | null; revision_type: string | null;
  last_event: { ts: string; by: string; action: string; note: string | null } | null;
  submitted_at?: string | null; verified_at?: string | null; published_at?: string | null; submitted_by?: string | null;
};
export type CurriculumDetail = CurriculumRow & {
  parts: Record<string, { count: number | null; confirmed_at: string | null; edited: boolean }>;
  checks: { pass: number; warn: number; fail: number };
  events: { ts: string; by: string; action: string; from_status: string; to_status: string; note: string | null }[];
  // the approval flow `curriculum` (version this draft follows) and what this user may do in it
  flow: { version: number; steps: FlowStep[] };
  allowed: { submit: boolean; review: boolean; publish: boolean };
  // หมวด 0–5 of the คู่มือ (ocl_api.sections) and which of them this user may change now
  sections: Record<string, { label: string; parts: string[]; updated_by: string | null; updated_at: string | null }>;
  editable: string[];
  limited: Record<string, string[]>; // in review: the only parts of a section that may change
  progress: Record<string, { done: number; total: number; missing: string[] }>;
};
export type CurriculumList = { counts: Record<string, number>; items: CurriculumRow[]; statuses: Record<string, string>; actions: Record<string, string> };
export type DashItem = {
  id: number; name_th: string | null; faculty: string | null; level: string | null; start_year: number | null;
  status: CurriculumRow["status"]; status_th: string; review_due_at: string | null; days: number | null;
  missing: string[]; complete: Record<string, boolean>; revision_type: string | null; total_credits: number | null;
  plo_count: number; course_count: number; ksec: Record<string, number>;
};
export type Dashboard = {
  options: { faculties: string[]; levels: string[]; years: number[] };
  total: number; counts: Record<CurriculumRow["status"], number>;
  by_faculty: { faculty: string; count: number; counts: Record<CurriculumRow["status"], number>; verified_pct: number; longest_days: number }[];
  completeness: Record<string, number>; stuck: DashItem[]; items: DashItem[]; today: string; this_year: number;
};
export const curricula = {
  list: () => fetch(`${API_BASE}/api/curricula`, { cache: "no-store" }).then(j<CurriculumList>),
  get: (id: number | string) => fetch(`${API_BASE}/api/curricula/${id}`, { cache: "no-store" }).then(j<CurriculumDetail>),
  byJob: (jobId: string) => fetch(`${API_BASE}/api/curricula/by-job/${jobId}`, { cache: "no-store" }).then(j<{ id: number; status: string }>),
  create: (body: { name_th: string; level?: string | null; faculty?: string | null }) =>
    fetch(`${API_BASE}/api/curricula`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j<CurriculumDetail>),
  dashboard: (f: { faculty?: string; level?: string; year?: string }) =>
    fetch(`${API_BASE}/api/curricula/dashboard?${new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][])}`, { cache: "no-store" }).then(j<Dashboard>),
  remind: (id: number) => fetch(`${API_BASE}/api/curricula/${id}/remind`, { method: "POST" }).then(j<{ sent: boolean; to: number; step: string }>),
  transition: (id: number | string, body: { action: string; note?: string; section?: string; checked?: boolean }) =>
    fetch(`${API_BASE}/api/curricula/${id}/transition`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j<CurriculumDetail>),
};
export const STATUS_KIND: Record<string, "grey" | "warn" | "info" | "ok"> = { import: "grey", review: "warn", verified: "info", published: "ok" };

// ---------- SUPREME / HURIS copies (ocl_api.external) ----------
export type ExternalSource = {
  system: string; label: string; adapter: string | null; adapter_label?: string; sample?: boolean;
  synced_at?: string; as_of?: string | null; counts?: Record<string, number>;
};
export const external = {
  status: () => fetch(`${API_BASE}/api/external/status`, { cache: "no-store" }).then(j<ExternalSource[]>),
};

// ---------- กลุ่มสิทธิ์ (ocl_api.roles · menu u1) ----------
export type RoleGroup = {
  id: string; name: string; scope: string; scope_kind: string; builtin: boolean; ord: number; users: number;
  modules?: string[]; auto_from_teachers: boolean; notify_on_change: boolean; updated_by: string | null; updated_at: string;
};
export type RoleEvent = { ts: string; by: string | null; action: string; detail: Record<string, unknown> };
export type RoleDetail = RoleGroup & {
  perms: Record<string, string[]>; events: RoleEvent[]; actions: Record<string, string>; scopes: Record<string, string>; notified?: number;
};
export type RoleEdit = Partial<Pick<RoleDetail, "name" | "scope_kind" | "perms" | "auto_from_teachers" | "notify_on_change">>;
const json = (method: string, body: unknown) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const roles = {
  list: () => fetch(`${API_BASE}/api/roles`, { cache: "no-store" }).then(j<{ items: RoleGroup[]; actions: Record<string, string>; scopes: Record<string, string> }>),
  get: (id: string) => fetch(`${API_BASE}/api/roles/${id}`, { cache: "no-store" }).then(j<RoleDetail>),
  create: (name: string, copyFrom: string | null) => fetch(`${API_BASE}/api/roles`, json("POST", { name, copy_from: copyFrom })).then(j<RoleDetail>),
  update: (id: string, body: RoleEdit) => fetch(`${API_BASE}/api/roles/${id}`, json("PUT", body)).then(j<RoleDetail>),
  remove: async (id: string) => {
    const r = await fetch(`${API_BASE}/api/roles/${id}`, { method: "DELETE" });
    if (!r.ok) await j<never>(r);
  },
};

// ---------- ผู้ใช้งาน (ocl_api.api.users · menu u3) ----------
export type UserRow = {
  email: string; name: string; buasri_id: string | null; roles: string[]; active: boolean; usable: boolean;
  units: string[]; kind: "internal" | "external"; pid: string | null; sid?: string | null; expires_at: string | null;
  has_password: boolean; last_login_at: string | null; updated_by: string | null; updated_at: string | null;
};
export type UserDetail = UserRow & { events: RoleEvent[] };
export type UserOptions = { roles: { id: string; name: string }[]; units: string[]; units_sample: boolean };
export type Staff = { pid: string; title_short: string | null; name_th: string; faculty: string | null; department: string | null; email: string | null };
export const usersApi = {
  options: () => fetch(`${API_BASE}/api/users/options`, { cache: "no-store" }).then(j<UserOptions>),
  list: () => fetch(`${API_BASE}/api/users`, { cache: "no-store" }).then(j<{ items: UserRow[] }>),
  get: (email: string) => fetch(`${API_BASE}/api/users/${enc(email)}`, { cache: "no-store" }).then(j<UserDetail>),
  add: (body: { pid?: string; sid?: string; email?: string; name?: string; roles: string[]; units: string[]; expires_at?: string | null }) =>
    fetch(`${API_BASE}/api/users`, json("POST", body)).then(j<UserRow>),
  invite: (body: { email: string; name: string; roles: string[]; units: string[]; expires_at: string }) =>
    fetch(`${API_BASE}/api/users/invite`, json("POST", body)).then(j<UserRow>),
  edit: (email: string, body: { name?: string; roles?: string[]; units?: string[]; expires_at?: string | null; clear_expiry?: boolean }) =>
    fetch(`${API_BASE}/api/users/${enc(email)}`, json("PUT", body)).then(j<UserRow>),
  setActive: (email: string, active: boolean) => fetch(`${API_BASE}/api/users/${enc(email)}/active`, json("POST", { active })).then(j<UserRow>),
  staff: (q: string) => fetch(`${API_BASE}/api/external/staff?q=${enc(q)}&limit=8`, { cache: "no-store" }).then(j<{ items: Staff[]; source: ExternalSource | null }>),
};

// ---------- ขั้นตอนอนุมัติ (ocl_api.flows · menu u2) ----------
export type FlowStep = { roles: string[]; position: string | null; label: string; action: string; days: number; on_reject: string };
export type Flow = {
  id: string; name: string; version: number; fixed_steps: number | null; ord: number;
  notify_next: boolean; notify_sender: boolean; remind_overdue: boolean; updated_by: string | null; updated_at: string | null;
  steps: FlowStep[];
};
export type FlowDetail = Flow & {
  shown_version: number; history: { version: number; by: string | null; ts: string }[];
  actions: Record<string, string>; on_reject: Record<string, string>; groups: { id: string; name: string }[];
};
export const flowsApi = {
  list: () => fetch(`${API_BASE}/api/flows`, { cache: "no-store" }).then(j<{ items: Flow[]; groups: { id: string; name: string }[] }>),
  get: (id: string, version?: number) => fetch(`${API_BASE}/api/flows/${id}${version ? `?version=${version}` : ""}`, { cache: "no-store" }).then(j<FlowDetail>),
  save: (id: string, body: { steps: FlowStep[]; notify_next?: boolean; notify_sender?: boolean; remind_overdue?: boolean }) =>
    fetch(`${API_BASE}/api/flows/${id}`, json("PUT", body)).then(j<FlowDetail>),
};

// ---------- ฟอร์มคู่มือหลักสูตร หมวด 0 1 2 5 (ocl_api.curriculum_form) ----------
export type FormField = {
  key: string; label: string; kind: string; path: string; required: boolean; options?: string[];
  source?: string; hint?: string; lookup?: boolean; lookup_key: string; columns?: FormField[];
  required_when?: { key: string; equals: string };
};
export type FormGroup = { title: string; fields: FormField[] };
export type FormSpec = { sections: Record<string, FormGroup[]>; labels: Record<string, string> };
export type SectionData = Record<string, { label: string; data: Record<string, unknown>; updated_by: string | null; updated_at: string | null }>;
export type TeacherCheck = { responsible: number; required: number; issues: string[]; duplicates: { name: string; curriculum: string; id: number }[] };
export const curriculumForm = {
  spec: () => fetch(`${API_BASE}/api/curricula/form`, { cache: "no-store" }).then(j<FormSpec>),
  addOption: (key: string, value: string) => fetch(`${API_BASE}/api/curricula/form/options`, json("POST", { key, value })).then(j<FormSpec>),
  sections: (id: number | string) => fetch(`${API_BASE}/api/curricula/${id}/sections`, { cache: "no-store" }).then(j<SectionData>),
  save: (id: number | string, n: string, data: Record<string, unknown>) =>
    fetch(`${API_BASE}/api/curricula/${id}/sections/${n}`, json("PUT", { data })).then(j<SectionData[string]>),
  uploadBook: (id: number | string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${API_BASE}/api/curricula/${id}/book`, { method: "POST", body: fd }).then(j<SectionData[string]>);
  },
  bookUrl: (id: number | string) => `${API_BASE}/api/curricula/${id}/book`,
  teacherCheck: (id: number | string) => fetch(`${API_BASE}/api/curricula/${id}/teachers/check`, { cache: "no-store" }).then(j<TeacherCheck>),
};
export type CatalogCourse = {
  code_th: string; code_en: string | null; name_th: string | null; name_en: string | null; credits: number | null; credit_text: string | null;
  description_th: string | null; description_en: string | null; unit: string | null; course_type: string | null; module: string | null; version: number;
};
export const courseCatalog = (q: string, exclude: number | string) =>
  fetch(`${API_BASE}/api/curricula/courses/catalog?q=${encodeURIComponent(q)}&exclude=${exclude}`, { cache: "no-store" }).then(j<CatalogCourse[]>);

// ---------- ฐานข้อมูลรายวิชากลาง (FS-3a · US-M1-18) ----------
export type CourseFields = {
  code_th: string; code_en: string | null; name_th: string | null; name_en: string | null; transcript_th: string | null; transcript_en: string | null;
  credit_text: string | null; course_type: string | null; module: string | null; unit: string | null; major: string | null; reg_no: string | null;
  telebank: string | null; status: string; note: string | null; description_th: string | null; description_en: string | null;
};
export type CourseVersion = { version: number; kind: string; year: number | null; name_th: string; name_en: string | null; credit_text: string | null; description_th: string | null; source: string | null; created_by: string | null; created_at: string };
export type CourseRow = CourseFields & {
  latest: number; label: string; kind: string; year: number | null; credits: number | null; updated_by: string | null; updated_at: string | null;
  used_in: { draft_id: number; name_th: string | null; status: string; version: number | null }[];
};
export type CourseDetail = CourseRow & { versions: CourseVersion[] };
export type CourseList = { items: CourseRow[]; counts: Record<string, number>; options: { types: string[]; statuses: string[]; units: string[] } };
export type LatestVersion = { latest: number; status: string; name_th: string | null; name_en: string | null; credits: number | null; credit_text: string | null; description_th: string | null; description_en: string | null };
export const coursesApi = {
  list: () => fetch(`${API_BASE}/api/courses`, { cache: "no-store" }).then(j<CourseList>),
  get: (code: string) => fetch(`${API_BASE}/api/courses/${enc(code)}`, { cache: "no-store" }).then(j<CourseDetail>),
  create: (body: Partial<CourseFields>) => fetch(`${API_BASE}/api/courses`, json("POST", body)).then(j<CourseDetail>),
  update: (code: string, body: Partial<CourseFields> & { new_version: boolean }) => fetch(`${API_BASE}/api/courses/${enc(code)}`, json("PUT", body)).then(j<CourseDetail>),
  remove: async (code: string) => { const r = await fetch(`${API_BASE}/api/courses/${enc(code)}`, { method: "DELETE" }); if (!r.ok) await j(r); },
  // from a curriculum (หมวด 4): a ร่างรายวิชา Version 1, and the latest Version of each course it uses
  newFor: (draftId: number | string, body: { code_th: string; name_th: string; code_en?: string | null; name_en?: string | null; credit_text?: string | null }) =>
    fetch(`${API_BASE}/api/curricula/${draftId}/courses`, json("POST", body)).then(j<CatalogCourse>),
  versionsFor: (draftId: number | string) => fetch(`${API_BASE}/api/curricula/${draftId}/courses/versions`, { cache: "no-store" }).then(j<Record<string, LatestVersion>>),
};

// ---------- ทะเบียนบุคคลภายนอก (FS-3b · US-M1-19) ----------
export type PersonWork = { title: string; type: string; year: string | null };
export type PersonFields = {
  kind: string; title_full: string | null; title_short: string | null; position: string | null; name_th: string | null; name_en: string | null;
  national_id: string | null; org: string | null; email: string | null; tel: string | null; education: string[][]; works: PersonWork[]; active: boolean;
};
export type Person = PersonFields & { id: string; highest: string | null; updated_at: string; updated_by: string | null; used_in: { draft_id: number; name_th: string | null; status: string }[] };
export type PersonList = { items: Person[]; counts: { all: number; active: number; used: number }; options: { kinds: string[]; levels: string[]; work_types: string[] } };
export type PersonPick = { xid: string; name: string; rank: string | null; highest_level: string | null; org: string | null; kind: string };
export const personsApi = {
  list: () => fetch(`${API_BASE}/api/persons`, { cache: "no-store" }).then(j<PersonList>),
  get: (id: string) => fetch(`${API_BASE}/api/persons/${enc(id)}`, { cache: "no-store" }).then(j<Person>),
  save: (id: string | null, body: PersonFields) => fetch(`${API_BASE}/api/persons${id ? `/${enc(id)}` : ""}`, json(id ? "PUT" : "POST", body)).then(j<Person>),
  remove: async (id: string) => { const r = await fetch(`${API_BASE}/api/persons/${enc(id)}`, { method: "DELETE" }); if (!r.ok) await j(r); },
  search: (q: string) => fetch(`${API_BASE}/api/curricula/persons?q=${enc(q)}`, { cache: "no-store" }).then(j<PersonPick[]>),
};

// ---------- สมอ.08 (FS-3c · US-M1-09 10) ----------
export type SmoTeacher = { name?: string; rank?: string | null; pid?: string | null; xid?: string | null; highest_level?: string | null; responsible?: boolean; group?: string | null; chair?: boolean; [k: string]: unknown };
export type SmoChange = { change: "เพิ่ม" | "แก้ไข" | "นำออก"; before: SmoTeacher | null; after: SmoTeacher | null };
export type SmoBrief = {
  id: string; draft_id: number; name_th: string | null; status: "draft" | "pending" | "returned" | "approved"; status_th: string; step: number; steps_total: number;
  step_label: string; types_th: string[]; start: string; created_by: string; created_at: string; faculty: string | null;
};
export type SmoDetail = SmoBrief & {
  types: string[]; scope: { kind: "mother" | "child"; branch?: string }; fields: Record<string, string>; details: Record<string, string>; reason: string | null;
  teachers: { before?: SmoTeacher[]; after?: SmoTeacher[] }; changes: SmoChange[]; steps: FlowStep[];
  curriculum: { id: number; name_th: string | null; name_en: string | null; status: string; faculty: string | null; edition_year: number | string | null };
  events: { ts: string; by: string; action: string; step: number | null; note: string | null }[];
  files: { id: number; name: string; size: number; by: string; ts: string }[]; can_edit: boolean; can_act: boolean;
};
export type SmoOptions = { curricula: { id: number; name_th: string; status: string; edition_year: number | string | null; faculty: string | null; branches: string[] }[]; types: Record<string, string>; statuses: Record<string, string>; steps: FlowStep[] };
export const smoApi = {
  list: () => fetch(`${API_BASE}/api/smo`, { cache: "no-store" }).then(j<{ items: SmoBrief[]; counts: Record<string, number> }>),
  options: () => fetch(`${API_BASE}/api/smo/options`, { cache: "no-store" }).then(j<SmoOptions>),
  create: (draftId: number) => fetch(`${API_BASE}/api/smo`, json("POST", { draft_id: draftId })).then(j<SmoDetail>),
  get: (id: string) => fetch(`${API_BASE}/api/smo/${enc(id)}`, { cache: "no-store" }).then(j<SmoDetail>),
  save: (id: string, body: { types: string[]; scope: SmoDetail["scope"]; fields: Record<string, string>; after: SmoTeacher[]; details: Record<string, string>; reason: string }) =>
    fetch(`${API_BASE}/api/smo/${enc(id)}`, json("PUT", body)).then(j<SmoDetail>),
  act: (id: string, action: "submit" | "approve" | "return", note?: string) => fetch(`${API_BASE}/api/smo/${enc(id)}/${action}`, json("POST", { note })).then(j<SmoDetail>),
  upload: (id: string, file: File) => { const f = new FormData(); f.append("file", file); return fetch(`${API_BASE}/api/smo/${enc(id)}/files`, { method: "POST", body: f }).then(j<SmoDetail>); },
  fileUrl: (id: string, fid: number) => `${API_BASE}/api/smo/${enc(id)}/files/${fid}`,
};

// ---------- จับคู่ข้อมูล (FS-3d · US-M1-13) ----------
export type TeacherMatch = {
  index: number; name: string | null; rank?: string | null; highest_level?: string | null; state: "linked" | "one" | "many" | "external" | "none"; pid?: string; xid?: string;
  candidates?: { pid: string; name: string; rank: string | null; highest_level: string | null; faculty: string | null; differs: boolean }[];
  externals?: { xid: string; name: string; org: string | null }[];
};
export type CourseMatch = { index: number; code_th: string; name_th: string | null; credit_text: string | null; state: "linked" | "no_code" | "new" | "same" | "changed"; version: number | null; central: { version: number; name_th: string; credit_text: string | null } | null };
export type MatchData = { teachers: TeacherMatch[]; courses: CourseMatch[]; editable: { "0": boolean; "4": boolean }; matched?: number };
export const matchApi = {
  get: (id: number | string) => fetch(`${API_BASE}/api/curricula/${id}/match`, { cache: "no-store" }).then(j<MatchData>),
  teachers: (id: number | string, choices: { index: number; pid?: string; xid?: string; quals?: "huris" | "book" }[]) =>
    fetch(`${API_BASE}/api/curricula/${id}/match/teachers`, json("POST", { choices })).then(j<MatchData>),
  courses: (id: number | string, choices: { index: number; accept: boolean }[]) => fetch(`${API_BASE}/api/curricula/${id}/match/courses`, json("POST", { choices })).then(j<MatchData>),
};

// ---------- แผน/รายงานการจัดการเรียนรู้ (FS-4 · M2) ----------
export type M2Doc = "plan" | "report";
export type M2Status = "none" | "draft" | "sent" | "returned" | "approved" | "published";
export type M2Term = { term: string; slug: string; starts_on: string | null; ends_on: string | null; plan_open: string | null; plan_close: string | null; report_open: string | null; report_close: string | null; target_pct: number; set: boolean };
export type M2Person = { pid: string; name: string };
export type M2Item = {
  key: string; kind: "course" | "module"; code: string; name_th: string | null; unit: string | null; courses: string[]; offered: boolean;
  enrolled: number; sections: number; assign: Record<M2Doc, M2Person[]>; status: Record<M2Doc, M2Status>; mine: Record<M2Doc, boolean>; /** in the account's ขอบเขตข้อมูล, not only assigned */ scoped: boolean;
};
export type M2Items = { term: M2Term; items: M2Item[]; synced_at: string | null; statuses: Record<M2Status, string> };
export type M2Section = { course_code: string; section: string; teachers: string[]; schedule: string | null; room: string | null; enrolled: number; program_code: string | null };
export type M2Pulled = {
  item: M2Item; courses: { code_th: string; code_en?: string | null; name_th?: string | null; name_en?: string | null; credit_text?: string | null; unit?: string | null; description_th?: string | null }[];
  teachers: M2Person[]; sections: M2Section[]; enrolled: number;
  plos: { curriculum: string | null; draft_id: number; plos: { code: string; text: string }[]; rows: { course_code: string; plos?: string[]; by_column?: Record<string, string[]> }[] }[];
};
export type M2DocData = {
  term: M2Term; doc: M2Doc; doc_th: string; status: M2Status; status_th: string; step: number; steps: FlowStep[]; data: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  pulled: M2Pulled; missing: string[]; events: { ts: string; by: string; action: string; note: string | null }[]; window: { open: boolean; from: string | null; to: string | null };
  plan?: { status: M2Status; clos: Record<string, unknown>[] };
  can_edit: boolean; can_submit: boolean; can_certify: boolean; can_publish: boolean; recorder: boolean;
};
export type M2Dashboard = {
  term: M2Term; synced_at: string | null; offered: number; modules: number; unassigned: number; plan_pct: number; report_pct: number;
  published: Record<M2Doc, number>; status: Record<M2Doc, Record<M2Status, number>>;
  units: { unit: string; count: number; plan_pct: number; report_pct: number; below: boolean }[];
  late: { key: string; code: string; name_th: string | null; unit: string | null; doc: M2Doc; status: M2Status; days: number; recorders: string[] }[]; target_pct: number;
};
const m2u = (slug: string, rest = "") => `${API_BASE}/api/m2/terms/${slug}${rest}`;
const m2i = (slug: string, key: string, rest = "") => m2u(slug, `/items/${enc(key)}${rest}`);
export const m2Api = {
  terms: () => fetch(`${API_BASE}/api/m2/terms`, { cache: "no-store" }).then(j<M2Term[]>),
  saveTerm: (slug: string, body: Partial<M2Term>) => fetch(m2u(slug), json("PUT", body)).then(j<M2Term>),
  sync: (slug: string) => fetch(m2u(slug, "/sync"), { method: "POST" }).then(j<{ items: number; removed: number }>),
  items: (slug: string) => fetch(m2u(slug, "/items"), { cache: "no-store" }).then(j<M2Items>),
  assign: (slug: string, key: string, doc: M2Doc, pids: string[]) => fetch(m2i(slug, key, "/assign"), json("PUT", { doc, pids })).then(j<M2Item>),
  copyAssign: (slug: string) => fetch(m2u(slug, "/assign/copy"), { method: "POST" }).then(j<{ copied: number; from: string }>),
  notify: (slug: string) => fetch(m2u(slug, "/assign/notify"), { method: "POST" }).then(j<{ sent: number; recipients: number }>),
  doc: (slug: string, key: string, doc: M2Doc) => fetch(m2i(slug, key, `/${doc}`), { cache: "no-store" }).then(j<M2DocData>),
  save: (slug: string, key: string, doc: M2Doc, data: Record<string, unknown>) => fetch(m2i(slug, key, `/${doc}`), json("PUT", { data })).then(j<M2DocData>),
  copy: (slug: string, key: string, doc: M2Doc) => fetch(m2i(slug, key, `/${doc}/copy`), { method: "POST" }).then(j<M2DocData>),
  submit: (slug: string, key: string, doc: M2Doc) => fetch(m2i(slug, key, `/${doc}/submit`), { method: "POST" }).then(j<M2DocData>),
  certify: (slug: string, key: string, doc: M2Doc, ok: boolean, note?: string) => fetch(m2i(slug, key, `/${doc}/certify`), json("POST", { ok, note })).then(j<M2DocData>),
  publish: (slug: string, key: string, doc: M2Doc, on: boolean) => fetch(m2i(slug, key, `/${doc}/publish?on=${on}`), { method: "POST" }).then(j<M2DocData>),
  dashboard: (slug: string) => fetch(m2u(slug, "/dashboard"), { cache: "no-store" }).then(j<M2Dashboard>),
  remind: (slug: string, key?: string, doc?: M2Doc) => fetch(m2u(slug, "/remind"), json("POST", { key, doc })).then(j<{ sent: number; late: number }>),
};

// ---------- Skill Transcript (FS-5 · M3) ----------
export type SkillCat = "GS" | "SS" | "E" | "C";
export type SkillRow = { code: string; cat: SkillCat; name_th: string; name_en: string | null; definition: string | null; scope: "central" | "program"; curriculum_id: number | null; curriculum: string | null; tools: string[]; sources: string[]; rubric: string[]; active: boolean; used_in: number; updated_at: string };
export type SkillLevel = { level: number; min: number; max: number; en: string; th: string };
export type SkillFramework = { level: string; cohorts: string; frame: string; status: string };
export type SkillSettings = { levels: SkillLevel[]; ethics_pass: number; frameworks: SkillFramework[] };
export type SkillsResp = { items: SkillRow[]; settings: SkillSettings; rights: { cats: SkillCat[]; central: boolean } };
export type SkillBody = Pick<SkillRow, "code" | "cat" | "name_th" | "scope" | "tools" | "sources" | "rubric"> & { name_en?: string | null; definition?: string | null };
export type SkillDbPerm = { id: number; who: string; kind: "role" | "pid"; label: string; cats: SkillCat[]; unit_scope: "all" | "faculty" | "program" };
export type SkillAssign = { pid: string; name?: string; role: string; perms: string[]; scope: "all" | "courses"; courses: string[] };
export type SkillAssignOverview = {
  items: { id: number; name_th: string; faculty: string | null; level: string | null; assign: SkillAssign[]; status: "ok" | "none"; courses: string[] }[];
  kpi: { total: number; assigned: number; none: number; people: number };
  roles: Record<string, { label: string; perms: string[]; scope: "all" | "courses" }>;
  perms: Record<string, string>;
};
export type SkillCurriculum = { id: number; name_th: string; level: string | null; program_code: string | null; faculty: string | null; book_courses: string[] };
export type SkillStatus = "none" | "draft" | "sent" | "returned" | "approved";
export type SkillSetsOverview = {
  items: { id: number; name_th: string; faculty: string | null; status: SkillStatus; version: number | null; cohort_from: number | null; counts: Record<SkillCat, number>; own: number; only_core: boolean }[];
  statuses: Record<SkillStatus, string>;
  kpi: { approved: number; pending: number; none: number; only_core: number };
};
export type SkillRights = { staff: boolean; assigned: boolean; add: boolean; map: boolean; send: boolean; appr: boolean; faculty: boolean; courses: string[] | null };
export type SkillEvent = { ts: string; by: string; action: string; note: string | null };
export type SkillFlowStep = { roles: string[]; position: string | null; label: string; action: string; days: number };
export type SkillSetData = {
  curriculum: SkillCurriculum;
  set: { version: number; status: SkillStatus; status_th: string; skills: string[]; cohort_from: number | null; step: number };
  versions: { version: number; status: SkillStatus; cohort_from: number | null; skills: number; approved_at: string | null }[];
  core: string[]; pool: SkillRow[]; steps: SkillFlowStep[]; events: SkillEvent[]; rights: SkillRights;
  can_edit: boolean; can_submit: boolean; can_certify: boolean; can_revise: boolean;
};
export type SkillMapCourse = { code: string; name_th: string; module: string | null; offered: boolean; skills: string[] };
export type SkillMapping = {
  term: string; curriculum: SkillCurriculum; set: { version: number; cohort_from: number | null; skills: string[] } | null; skills: SkillRow[];
  courses: SkillMapCourse[]; status: SkillStatus; status_th: string; steps: SkillFlowStep[]; events: SkillEvent[];
  kpi: { courses: number; mapped: number; points: number; gaps: string[] }; rights: SkillRights;
  can_edit: boolean; can_submit: boolean; can_certify: boolean; copied_from?: string; skipped?: string[];
};
export type AssessStatus = "todo" | "doing" | "wait" | "ok";
export type AssessRow = { course_code: string; section: string; name_th: string | null; program: string | null; faculty: string | null; curricula: { id: number; name_th: string }[]; skills: string[]; n: number; done: number; teachers: { pid: string; name: string }[]; mine: boolean; status: AssessStatus; deadline: string | null };
export type AssessList = { term: string; items: AssessRow[]; statuses: Record<AssessStatus, string>; deadline: string | null };
export type AssessForm = AssessRow & {
  term: string; students: { sid: string; name_th: string | null }[]; scores: Record<string, Record<string, number>>; skill_rows: SkillRow[];
  levels: SkillLevel[]; confirmed_by: string | null; confirmed_at: string | null; events: SkillEvent[]; can_edit: boolean; can_reopen: boolean; imported?: number;
};
export type CatScores = Record<SkillCat, number | null>;
export type PortfolioItem = { sid: string; name_th: string; program: string | null; program_code: string | null; faculty: string | null; entry_year: number | null; status: string | null; cats: CatScores; overall: number | null; level: string | null };
export type PortfolioSkill = { code: string; cat: SkillCat; name_th: string; name_en: string | null; definition: string | null; avg: number | null; level: string | null; n: number; in_set: boolean; su: "S" | "U" | null; sources: { term: string; course_code: string; course_name: string | null; section: string; score: number }[] };
export type Portfolio = {
  student: { sid: string; name_th: string; program: string | null; program_name: string | null; faculty: string | null; entry_year: number | null; status: string | null; graduated: string | null; advisor: string | null };
  curriculum: { id: number; name_th: string } | null; set: { version: number; cohort_from: number | null; skills: string[] } | null;
  skills: PortfolioSkill[]; cats: CatScores; overall: number | null; level: string | null; by_term: { term: string; label: string; cats: CatScores }[];
  levels: SkillLevel[]; ethics_pass: number; placement: string | null;
  readiness: { graduated: boolean; has_set: boolean; missing: string[]; ethics_u: string[]; ready: boolean };
  transcript: { no: string; status: string; issued_at: string | null } | null;
};
export type TranscriptData = {
  student: { sid: string; name_th: string; program: string | null; program_name: string | null; faculty: string | null; entry_year: number | null; graduated: string | null };
  curriculum: { id: number; name_th: string } | null; set_version: number | null;
  skills: { code: string; cat: SkillCat; name_th: string; name_en: string | null; definition: string | null; avg: number | null; level: string | null; su: "S" | "U" | null }[];
  cats: CatScores; overall: number | null; level: string | null; placement: string | null;
  signer: { id: string; name_th: string; position: string | null } | null; no?: string; issued_on?: string;
};
export type TranscriptDoc = { draft: boolean; no: string | null; data: TranscriptData; signer?: { name_th: string; position: string | null; method: string; sample?: boolean; signed_at?: string }; issued_at?: string | null; checks?: number; levels: SkillLevel[]; readiness: Portfolio["readiness"] };
export type GraduateGroup = "ready" | "incomplete" | "ethics" | "issued";
export type Graduate = { sid: string; name_th: string; program: string | null; faculty: string | null; graduated: string | null; curriculum: { id: number; name_th: string } | null; set_size: number; missing: string[]; has_set: boolean; ethics_u: string[]; group: GraduateGroup; transcript: { no: string; status: string } | null };
export type Graduates = { items: Graduate[]; groups: Record<GraduateGroup, number>; ethics_pass: number };
export type RegisterRow = { no: string; sid: string; name_th: string; program: string | null; status: string; checks: number; issued_at: string | null; by: string | null };
export type SkillDashboard = {
  term: string; sections: number; students: number; assessed_pct: number; status: Record<AssessStatus, number>; transcripts: Record<GraduateGroup, number>; graduates: number;
  units: { faculty: string; sections: number; status: Record<AssessStatus, number>; confirmed_pct: number; assessed_pct: number; below: boolean }[];
  target_pct: number; deadline: string | null; late_days: number;
  late: { course_code: string; section: string; name_th: string | null; faculty: string | null; status: AssessStatus; n: number; done: number; teachers: { pid: string; name: string }[] }[];
};
export type TranscriptCheck = { no: string; name_th: string; sid: string; program: string | null; faculty: string | null; curriculum: string | null; issued_at: string | null; signer: { name_th: string | null; position: string | null }; signature: { method: string | null; sample: boolean; valid: boolean }; checks: number };

const sk = (rest = "") => `${API_BASE}/api/skills${rest}`;
const get = <T,>(u: string) => fetch(u, { cache: "no-store" }).then(j<T>);
const upload = <T,>(u: string, file: File) => { const f = new FormData(); f.append("file", file); return fetch(u, { method: "POST", body: f }).then(j<T>); };
export const skillsApi = {
  list: () => get<SkillsResp>(sk()),
  add: (b: SkillBody) => fetch(sk(), json("POST", b)).then(j<SkillRow>),
  save: (b: SkillBody) => fetch(sk(`/${enc(b.code)}`), json("PUT", b)).then(j<SkillRow>),
  active: (code: string, on: boolean) => fetch(sk(`/${enc(code)}/active?on=${on}`), { method: "POST" }).then(j<SkillRow>),
  templateUrl: () => sk("/template.xlsx"),
  importXlsx: (file: File) => upload<{ added: number; updated: number; errors: { row: number; error: string }[] }>(sk("/import"), file),
  saveSetting: (key: "levels" | "ethics_pass" | "frameworks", data: unknown) => fetch(sk(`/settings/${key}`), json("PUT", { data })).then(j<SkillSettings>),
  dbPerms: () => get<{ items: SkillDbPerm[]; groups: Record<string, string> }>(sk("/db-perms")),
  addDbPerm: (b: Pick<SkillDbPerm, "who" | "cats" | "unit_scope">) => fetch(sk("/db-perms"), json("POST", b)).then(j<SkillDbPerm[]>),
  delDbPerm: (id: number) => fetch(sk(`/db-perms/${id}`), { method: "DELETE" }).then(j<SkillDbPerm[]>),
  assign: () => get<SkillAssignOverview>(sk("/assign")),
  setAssign: (cid: number, rows: SkillAssign[]) => fetch(sk(`/assign/${cid}`), json("PUT", rows)).then(j<SkillAssign[]>),
  sets: () => get<SkillSetsOverview>(sk("/sets")),
  set: (cid: number) => get<SkillSetData>(sk(`/sets/${cid}`)),
  saveSet: (cid: number, skills: string[], cohort_from: number | null) => fetch(sk(`/sets/${cid}`), json("PUT", { skills, cohort_from })).then(j<SkillSetData>),
  addOwn: (cid: number, b: SkillBody) => fetch(sk(`/sets/${cid}/own`), json("POST", b)).then(j<SkillSetData>),
  submitSet: (cid: number) => fetch(sk(`/sets/${cid}/submit`), { method: "POST" }).then(j<SkillSetData>),
  certifySet: (cid: number, ok: boolean, note: string) => fetch(sk(`/sets/${cid}/certify`), json("POST", { ok, note })).then(j<SkillSetData>),
  reviseSet: (cid: number, cohort_from: number | null) => fetch(sk(`/sets/${cid}/revise`), json("POST", { cohort_from })).then(j<SkillSetData>),
  terms: () => get<string[]>(sk("/terms")),
  mapCurricula: (slug: string) => get<{ id: number; name_th: string; faculty: string | null }[]>(sk(`/map/${slug}`)),
  mapping: (slug: string, cid: number) => get<SkillMapping>(sk(`/map/${slug}/${cid}`)),
  saveMapping: (slug: string, cid: number, cells: Record<string, string[]>) => fetch(sk(`/map/${slug}/${cid}`), json("PUT", { cells })).then(j<SkillMapping>),
  copyMapping: (slug: string, cid: number) => fetch(sk(`/map/${slug}/${cid}/copy`), { method: "POST" }).then(j<SkillMapping>),
  submitMapping: (slug: string, cid: number) => fetch(sk(`/map/${slug}/${cid}/submit`), { method: "POST" }).then(j<SkillMapping>),
  certifyMapping: (slug: string, cid: number, ok: boolean, note: string) => fetch(sk(`/map/${slug}/${cid}/certify`), json("POST", { ok, note })).then(j<SkillMapping>),
  sections: (slug: string) => get<AssessList>(sk(`/assess/${slug}`)),
  section: (slug: string, code: string, sec: string) => get<AssessForm>(sk(`/assess/${slug}/${enc(code)}/${enc(sec)}`)),
  saveScores: (slug: string, code: string, sec: string, scores: Record<string, Record<string, number | null>>) => fetch(sk(`/assess/${slug}/${enc(code)}/${enc(sec)}`), json("PUT", { scores })).then(j<AssessForm>),
  confirm: (slug: string, code: string, sec: string) => fetch(sk(`/assess/${slug}/${enc(code)}/${enc(sec)}/confirm`), { method: "POST" }).then(j<AssessForm>),
  reopen: (slug: string, code: string, sec: string, note: string) => fetch(sk(`/assess/${slug}/${enc(code)}/${enc(sec)}/reopen`), json("POST", { note })).then(j<AssessForm>),
  formUrl: (slug: string, code: string, sec: string) => sk(`/assess/${slug}/${enc(code)}/${enc(sec)}/form.xlsx`),
  importScores: (slug: string, code: string, sec: string, file: File) => upload<AssessForm>(sk(`/assess/${slug}/${enc(code)}/${enc(sec)}/import`), file),
  portfolios: () => get<{ items: PortfolioItem[]; levels: SkillLevel[] }>(sk("/portfolio")),
  portfolio: (sid: string) => get<Portfolio>(sk(`/portfolio/${enc(sid)}`)),
  transcript: (sid: string) => get<TranscriptDoc>(sk(`/portfolio/${enc(sid)}/transcript`)),
  me: () => get<Portfolio>(sk("/me")),
  myTranscript: () => get<TranscriptDoc>(sk("/me/transcript")),
  qrUrl: (no: string, origin: string) => sk(`/transcripts/${enc(no)}/qr.svg?origin=${enc(origin)}`),
  graduates: () => get<Graduates>(sk("/issue")),
  issue: (sids: string[]) => fetch(sk("/issue"), json("POST", { sids })).then(j<{ issued: string[] }>),
  register: () => get<RegisterRow[]>(sk("/register")),
  dashboard: (slug: string) => get<SkillDashboard>(sk(`/dashboard/${slug}`)),
  remind: (slug: string, course_code?: string, section?: string) => fetch(sk(`/dashboard/${slug}/remind`), json("POST", { course_code, section })).then(j<{ sent: number; late: number }>),
};

// ---------- ประเมินผลหลักสูตร (FS-6 · M4) ----------
export type QaCriterion = { id: number; set_year: number; no: number; title: string; detail: string | null; sources: string[]; level: "all" | "grad"; rule: string; active: boolean; updated_at: string };
export type QaCriteria = { items: QaCriterion[]; sets: number[]; levels: Record<string, string>; rules: Record<string, string> };
export type QaRoundStatus = "draft" | "open" | "closed";
export type QaRound = { id: number; year: number; name: string; starts_on: string | null; ends_on: string | null; status: QaRoundStatus; status_th: string; closed_at: string | null; programs: number; sets: number[]; confirmed: number };
export type QaDataStatus = "none" | "doing" | "sent" | "confirmed";
export type QaResult = "pass" | "fail" | "pending";
export type QaPerson = { pid: string; name: string };
export type QaRoundItem = { curriculum_id: number; name_th: string | null; level: string | null; faculty: string | null; set_year: number; status: QaDataStatus; evaluators: { email: string; name: string }[] };
export type QaRoundDetail = QaRound & { items: QaRoundItem[] };
export type QaCandidate = { id: number; name_th: string; level: string | null; faculty: string | null; standard: string | null; set_year: number };
export type QaEvaluator = { email: string; name: string; kind: string };
export type QaAssign = Omit<QaRoundDetail, "items"> & {
  items: (QaRoundItem & { recorders: QaPerson[]; confirmer: QaPerson | null; complete: boolean })[];
  kpi: { complete: number; incomplete: number; confirmed: number }; statuses: Record<QaDataStatus, string>;
};
export type QaProgramRow = QaRoundItem & { roles: string[]; status_th: string; results: Record<string, QaResult | "na" | "none">; final: QaResult; complete: boolean };
export type QaPrograms = { id: number; year: number; name: string; status: QaRoundStatus; status_th: string; items: QaProgramRow[]; statuses: Record<QaDataStatus, string>; results: Record<QaResult, string> };
export type QaEvidenceRow = { name: string | null; pid: string | null; degree: string; rank: string; works: number | null; result: QaResult };
export type QaItem = Omit<QaCriterion, "id" | "set_year" | "active" | "updated_at"> & {
  applies: boolean; evidence: { result: QaResult | "na"; text: string; rows?: QaEvidenceRow[] }; note: string;
  result: { result: QaResult; note: string; by: string; at: string } | null;
};
export type QaDetail = {
  round: { id: number; name: string; status: QaRoundStatus; status_th: string }; curriculum: { id: number; name_th: string; level: string | null; faculty: string | null; grad: boolean };
  set_year: number; items: QaItem[]; dates: { curriculum: string; huris: string | null; supreme: string | null };
  status: QaDataStatus; status_th: string; final: QaResult; recorders: QaPerson[]; confirmer: QaPerson | null; evaluators: { email: string; name: string }[];
  roles: string[]; events: { ts: string; by: string; action: string; note: string | null }[];
  can_note: boolean; can_confirm: boolean; can_evaluate: boolean; complete: boolean; results: Record<QaResult, string>;
};
export type QaSummary = {
  id: number; year: number; name: string; status: QaRoundStatus; status_th: string;
  items: { curriculum_id: number; name_th: string | null; level: string | null; faculty: string | null; set_year: number; status: QaDataStatus; final: QaResult; passed: number; total: number; complete: boolean }[];
  kpi: { programs: number; pass: number; fail: number; pending: number };
};

const qa = (rest = "") => `${API_BASE}/api/qa${rest}`;
const qget = <T,>(u: string) => fetch(u, { cache: "no-store" }).then(j<T>);
export const qaApi = {
  criteria: () => qget<QaCriteria>(qa("/criteria")),
  saveCriterion: (id: number | null, b: Omit<QaCriterion, "id" | "updated_at">) => fetch(qa(id ? `/criteria/${id}` : "/criteria"), json(id ? "PUT" : "POST", b)).then(j<QaCriteria>),
  evaluators: () => qget<QaEvaluator[]>(qa("/evaluators")),
  rounds: () => qget<QaRound[]>(qa("/rounds")),
  candidates: () => qget<QaCandidate[]>(qa("/candidates")),
  round: (rid: number) => qget<QaRoundDetail>(qa(`/rounds/${rid}`)),
  saveRound: (rid: number | null, b: { year: number; name?: string; starts_on?: string | null; ends_on?: string | null; programs: { curriculum_id: number; set_year: number; evaluators: string[] }[] }) =>
    fetch(qa(rid ? `/rounds/${rid}` : "/rounds"), json(rid ? "PUT" : "POST", b)).then(j<QaRoundDetail>),
  copyRound: (rid: number) => fetch(qa(`/rounds/${rid}/copy`), { method: "POST" }).then(j<QaRoundDetail>),
  openRound: (rid: number) => fetch(qa(`/rounds/${rid}/open`), { method: "POST" }).then(j<QaRoundDetail>),
  closeRound: (rid: number, note?: string) => fetch(qa(`/rounds/${rid}/close`), json("POST", { note })).then(j<QaRoundDetail>),
  assign: (rid: number) => qget<QaAssign>(qa(`/rounds/${rid}/assign`)),
  setAssign: (rid: number, cid: number, recorders: string[], confirmer: string | null) => fetch(qa(`/rounds/${rid}/assign/${cid}`), json("PUT", { recorders, confirmer })).then(j<QaAssign>),
  copyAssign: (rid: number) => fetch(qa(`/rounds/${rid}/assign/copy`), { method: "POST" }).then(j<QaAssign & { copied: number }>),
  notify: (rid: number) => fetch(qa(`/rounds/${rid}/assign/notify`), { method: "POST" }).then(j<{ sent: number; recipients: number }>),
  programs: (rid: number) => qget<QaPrograms>(qa(`/rounds/${rid}/programs`)),
  detail: (rid: number, cid: number) => qget<QaDetail>(qa(`/rounds/${rid}/programs/${cid}`)),
  saveNotes: (rid: number, cid: number, notes: Record<string, string>) => fetch(qa(`/rounds/${rid}/programs/${cid}/notes`), json("PUT", { notes })).then(j<QaDetail>),
  send: (rid: number, cid: number) => fetch(qa(`/rounds/${rid}/programs/${cid}/send`), { method: "POST" }).then(j<QaDetail>),
  confirm: (rid: number, cid: number, ok: boolean, note: string) => fetch(qa(`/rounds/${rid}/programs/${cid}/confirm`), json("POST", { ok, note })).then(j<QaDetail>),
  evaluate: (rid: number, cid: number, results: Record<string, { result: QaResult; note: string }>) => fetch(qa(`/rounds/${rid}/programs/${cid}/evaluate`), json("POST", { results })).then(j<QaDetail>),
  giveBack: (rid: number, cid: number, note: string) => fetch(qa(`/rounds/${rid}/programs/${cid}/return`), json("POST", { note })).then(j<QaDetail>),
  summary: (rid: number) => qget<QaSummary>(qa(`/rounds/${rid}/summary`)),
  preview: (rid: number, cid?: number) => qget<(QaDetail & { complete: boolean })[]>(qa(`/rounds/${rid}/preview${cid ? `?cid=${cid}` : ""}`)),
};

// ---------- reports R01–R14 · home dashboard · R11 public (FS-7) ----------
export type ReportItem = { code: string; title: string; tor: string; users: string; exports: string[]; proposed: boolean; allowed: boolean; public: boolean; remind: boolean };
export type ReportFilter = { key: string; label: string; value: string; options: [string, string][] };
export type ReportTable = { title: string; columns: { key: string; label: string; num: boolean }[]; rows: Record<string, string | number | null>[]; note: string | null };
export type Report = Omit<ReportItem, "allowed" | "public"> & {
  filters: ReportFilter[]; kpis: { label: string; value: string | number }[]; note: string | null; tables: ReportTable[]; radar?: Record<string, number | null>;
};
export type HomeData = {
  cards: { label: string; value: string | number; sub: string; href: string }[];
  units: M2Dashboard["units"]; target?: number; skills: Record<string, number | null> | null;
  tasks: { text: string; status: string; href: string }[];
};
const rq = (params: Record<string, string>) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return q ? `?${q}` : "";
};
export const reportsApi = {
  catalog: () => fetch(`${API_BASE}/api/reports`, { cache: "no-store" }).then(j<ReportItem[]>),
  report: (code: string, params: Record<string, string>) => fetch(`${API_BASE}/api/reports/${enc(code)}${rq(params)}`, { cache: "no-store" }).then(j<Report>),
  xlsxUrl: (code: string, params: Record<string, string>) => `${API_BASE}/api/reports/${enc(code)}.xlsx${rq(params)}`,
  remind: (code: string, params: Record<string, string>) => fetch(`${API_BASE}/api/reports/${enc(code)}/remind${rq(params)}`, { method: "POST" }).then(j<{ sent: number; late?: number }>),
  home: () => fetch(`${API_BASE}/api/home`, { cache: "no-store" }).then(j<HomeData>),
};
