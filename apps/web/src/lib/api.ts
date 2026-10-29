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
  units: string[]; kind: "internal" | "external"; pid: string | null; expires_at: string | null;
  has_password: boolean; last_login_at: string | null; updated_by: string | null; updated_at: string | null;
};
export type UserDetail = UserRow & { events: RoleEvent[] };
export type UserOptions = { roles: { id: string; name: string }[]; units: string[]; units_sample: boolean };
export type Staff = { pid: string; title_short: string | null; name_th: string; faculty: string | null; department: string | null; email: string | null };
export const usersApi = {
  options: () => fetch(`${API_BASE}/api/users/options`, { cache: "no-store" }).then(j<UserOptions>),
  list: () => fetch(`${API_BASE}/api/users`, { cache: "no-store" }).then(j<{ items: UserRow[] }>),
  get: (email: string) => fetch(`${API_BASE}/api/users/${enc(email)}`, { cache: "no-store" }).then(j<UserDetail>),
  add: (body: { pid?: string; email?: string; name?: string; roles: string[]; units: string[]; expires_at?: string | null }) =>
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
