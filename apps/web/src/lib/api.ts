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
  checks: (id: string) => fetch(`${API_BASE}/api/imports/${id}/checks`, { cache: "no-store" }).then(j<Check[]>),
  source: (id: string, page: number) =>
    fetch(`${API_BASE}/api/imports/${id}/source?page=${page}`, { cache: "no-store" }).then(
      j<{ page: number; pages: number | null; blocks: Array<Record<string, unknown>>; page_image: string | null }>,
    ),
  fileUrl: (id: string, path: string) => `${API_BASE}/api/imports/${id}/files/${path}`,
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
  id: number; job_id: string; program_code: string | null; name_th: string | null; level: string | null; start_year: number | null;
  status: "import" | "review" | "verified" | "published"; status_th: string; faculty_checked: Record<string, boolean>;
  review_due_at: string | null; finalized_at: string | null; updated_at: string | null; faculty: string | null; revision_type: string | null;
  last_event: { ts: string; by: string; action: string; note: string | null } | null;
  submitted_at?: string | null; verified_at?: string | null; published_at?: string | null;
};
export type CurriculumDetail = CurriculumRow & {
  parts: Record<string, { count: number | null; confirmed_at: string | null; edited: boolean }>;
  checks: { pass: number; warn: number; fail: number };
  events: { ts: string; by: string; action: string; from_status: string; to_status: string; note: string | null }[];
  // the approval flow `curriculum` (version this draft follows) and what this user may do in it
  flow: { version: number; steps: FlowStep[] };
  allowed: { submit: boolean; review: boolean; publish: boolean };
};
export type CurriculumList = { counts: Record<string, number>; items: CurriculumRow[]; statuses: Record<string, string>; actions: Record<string, string> };
export const curricula = {
  list: () => fetch(`${API_BASE}/api/curricula`, { cache: "no-store" }).then(j<CurriculumList>),
  get: (id: number | string) => fetch(`${API_BASE}/api/curricula/${id}`, { cache: "no-store" }).then(j<CurriculumDetail>),
  byJob: (jobId: string) => fetch(`${API_BASE}/api/curricula/by-job/${jobId}`, { cache: "no-store" }).then(j<{ id: number; status: string }>),
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
const enc = encodeURIComponent;
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
