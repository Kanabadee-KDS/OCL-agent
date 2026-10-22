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

export type Meta = { confidence: "high" | "medium" | "low"; source: { page: number | null; snippet: string }; by: string; inferred?: boolean; note?: string };

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
