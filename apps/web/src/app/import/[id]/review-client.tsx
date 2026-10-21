"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, PART_LABELS, type Check, type Job, type Meta, type Part } from "@/lib/api";
import { ConfPill, Ic, Markdown, Note, PageHead, Pill, Steps } from "@/components/ui";

const ORDER = ["info", "teachers", "plan", "plo", "ksec", "structure", "modules", "courses", "mapping", "appr"];
type Tab = string; // part key | "check" | "preview"

type InfoField = { key: string; label: string; group: string; kind: "text" | "int" | "enum" | "bool" | "list"; options?: string[] };
type InfoData = {
  fields: InfoField[];
  values: Record<string, unknown>;
  meta: Record<string, Meta | undefined>;
  majors: { name: string; meta?: Meta }[];
  collaborations: { institution: string; country: string | null; domestic: boolean; meta?: Meta }[];
  careers: { group: string | null; name: string; meta?: Meta }[];
};
type Node = { number: string; level: number; name: string; credits: number | null; children: Node[]; meta?: Meta; plan?: boolean };
type Plo = { code: string; text: string; sub_plos: { code: string; text: string; meta?: Meta }[]; meta?: Meta };
type MapRow = { course_code: string; course_name: string | null; group: string | null; plos: string[]; meta?: Meta };
type KsecRow = { course_code: string; course_name: string | null; group: string | null; by_column: Record<string, string[]>; ksec_codes: string[]; plos: string[]; meta?: Meta };
type MapData = { plo_codes: string[]; rows: MapRow[]; ksec_columns?: string[]; ksec_rows?: KsecRow[] };
type Module = { number: string; name_th: string; name_en: string | null; credits: number | null; counted: boolean; group: string | null; major?: string | null; description_th: string | null; description_en: string | null; course_codes: string[]; meta?: Meta };
type ModulesData = { modules: Module[]; groups: { name: string; declared_modules: number | null; declared_credits: number | null }[] };
type PlanTable = { name: string | null; years: string[]; rows: { label: string; values: number[] }[]; total: number[] | null; graduates: number[] | null; meta?: Meta };
type PlanData = { plans: PlanTable[]; teaching_modes: string[]; teaching_methods: { outcome: string; methods: string; meta?: Meta }[]; meta: Record<string, Meta | undefined>; intake_per_year?: number };
type Degree = { degree: string; field: string | null; year: number | null; level: string | null; institution: string | null };
type Teacher = { order: number | null; responsible: boolean; rank: string | null; doctor: boolean; name: string; group: string | null; degrees: Degree[]; institutions_text: string | null; highest_level: string | null; meta?: Meta };
type ApprRow = { level_key: string; level: string; body_text?: string; meeting_no: string | null; date: { day?: number; month?: number; year_be?: number; text: string; iso?: string | null } | null; resolution: string; pending: boolean; meta?: Meta };
type ApprData = { status: string | null; previous_program: string | null; previous_year: number | null; start_semester: number | null; start_year: number | null; approvals: ApprRow[]; missing_levels: string[]; meta: Record<string, Meta | undefined> };
type KsecItem = { code: string; category: string; subtype: string | null; text: string; meta?: Meta };
type KsecPlo = { code: string; plan: string | null; group: string | null; text: string; items: KsecItem[]; item_count?: number; meta?: Meta };
type Course = {
  code_th: string; code_en: string | null; name_th: string | null; name_en: string | null; credit_text: string | null;
  credits: number | null; description_th: string | null; description_en: string | null; prerequisite: string | null;
  group: string | null; module: string | null; meta: Meta;
};

export default function ReviewClient() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("info");
  const [part, setPart] = useState<Part | null>(null);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checks, setChecks] = useState<Check[]>([]);
  const [page, setPage] = useState<number | null>(null);
  const [src, setSrc] = useState<{ page: number; pages: number | null; blocks: Array<Record<string, unknown>> } | null>(null);
  const [hit, setHit] = useState<string>("");
  const [preview, setPreview] = useState<Record<string, string>>({});
  const [openDesc, setOpenDesc] = useState<Record<string, boolean>>({});

  // poll the job while it is running
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const j = await api.get(id);
        if (!alive) return;
        setJob(j);
        if (["queued", "ingesting", "extracting"].includes(j.status)) setTimeout(tick, 2000);
      } catch (e) {
        if (alive) setErr((e as Error).message);
      }
    };
    tick();
    return () => { alive = false; };
  }, [id]);

  const inReview = job && (job.status === "review" || job.status === "done");

  const loadPart = useCallback(async (key: string) => {
    setPart(null);
    setData(null);
    const p = await api.part(id, key);
    setPart(p);
    setData(p.data ? structuredClone(p.data) : null);
    setDirty(false);
    const first = firstPage(key, p.data);
    setPage(first);
    setHit("");
  }, [id]);

  useEffect(() => {
    if (!inReview) return;
    let alive = true;
    void (async () => {
      const cs = await api.checks(id).catch(() => [] as Check[]);
      if (alive) setChecks(cs);
      if (ORDER.includes(tab)) await loadPart(tab);
      if (tab === "preview") {
        const xs = await Promise.all(
          ["1-program_info.md", "8-teachers.md", "9-admission_plan.md", "2-course_structure.md", "4-plos.md", "4b-ksec.md", "3b-modules.md", "3-courses_list.md", "5-curriculum_mapping.md", "7-approval.md"].map((n) => api.fileText(id, `extract/md/${n}`).then((t) => [n, t] as const)),
        );
        if (alive) setPreview(Object.fromEntries(xs));
      }
    })();
    return () => { alive = false; };
  }, [inReview, tab, id, loadPart]);

  useEffect(() => {
    if (!inReview || !page) return;
    api.source(id, page).then(setSrc).catch(() => setSrc(null));
  }, [inReview, id, page]);

  async function save(confirm: boolean) {
    if (!data || !ORDER.includes(tab)) return;
    setSaving(true);
    try {
      const p = await api.savePart(id, tab, data, confirm);
      setPart(p);
      setDirty(false);
      const j = await api.get(id);
      setJob(j);
      if (confirm) {
        const avail = j.parts;
        const i = avail.indexOf(tab);
        if (i >= 0 && i + 1 < avail.length) setTab(avail[i + 1]);
        else setTab("check");
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function finalize() {
    try {
      await api.finalize(id);
      router.push(`/import/${id}/done`);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const confirmedCount = job?.confirmed_count ?? 0;
  const total = job?.parts_total ?? 3;

  if (err && !job) return <Note kind="warn">{err}</Note>;
  if (!job) return <div className="card pad">กำลังโหลด…</div>;

  if (!inReview) {
    return (
      <>
        <PageHead crumb={["บริหารข้อมูลหลักสูตร", "นำเข้าข้อมูลเล่มหลักสูตร"]} title="AI กำลังอ่านเล่มหลักสูตร" />
        <Steps current={1} />
        <section className="card pad stack" style={{ alignItems: "center", textAlign: "center", padding: "40px 20px" }}>
          {job.status === "failed" ? (
            <>
              <Pill kind="red">ล้มเหลว</Pill>
              <pre style={{ whiteSpace: "pre-wrap", textAlign: "left", fontSize: 12 }}>{job.error}</pre>
              <Link className="btn" href="/import">กลับไปหน้าอัปโหลด</Link>
            </>
          ) : (
            <>
              <div className="spinner" />
              <b>{job.progress}</b>
              <div className="small faint">{job.filename} · ขั้นที่ {job.step} · {job.provider === "none" ? "อ่านด้วยกฎ" : `AI ${job.provider}`}</div>
              <div className="small faint">หน้านี้จะอัปเดตเองทุก 2 วินาที</div>
            </>
          )}
        </section>
      </>
    );
  }

  const okN = confirmedCount;
  const navBtn = (key: string, i: number) => {
    const avail = job.parts.includes(key);
    const done = Boolean(job.confirmed[key]);
    return (
      <button key={key} className={`${tab === key ? "on" : ""} ${done ? "done" : ""}`} disabled={!avail} onClick={() => setTab(key)} style={avail ? {} : { opacity: 0.5 }}>
        <span className="n">{done && tab !== key ? "✓" : i + 1}</span>
        <span>
          {PART_LABELS[key][0]}
          <span className="small faint" style={{ display: "block", fontWeight: 400 }}>{PART_LABELS[key][1]}{avail ? "" : " · R1"}</span>
        </span>
      </button>
    );
  };

  return (
    <>
      <Link href="/import" className="link-btn small" style={{ color: "var(--red-ink)" }}><Ic name="back" size={14} /> กลับไปหน้าอัปโหลด</Link>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "นำเข้าข้อมูลเล่มหลักสูตร"]}
        title="ตรวจสอบข้อมูลที่ AI สกัดได้"
        sub={`${job.filename} · เทียบกับต้นฉบับทางซ้าย แก้ไขได้ทันที รายการที่ความมั่นใจต่ำจะถูกไฮไลต์`}
        actions={
          <>
            <button className="btn" disabled title="อยู่ใน R1"><Ic name="refresh" size={17} /> สกัดใหม่</button>
            <button className="btn" onClick={() => setTab("preview")}><Ic name="eye" size={17} /> Preview แบบเล่ม</button>
            <button className="btn primary" disabled={okN === 0 || job.status === "done"} onClick={finalize}>
              {job.status === "done" ? "บันทึกแล้ว" : `บันทึกเข้าระบบ (${okN}/${total} ส่วน)`}
            </button>
          </>
        }
      />
      <Steps current={job.status === "done" ? 4 : 2} />
      {err && <Note kind="warn">{err}</Note>}
      <div className="doc">
        <nav className="card doc-nav" aria-label="ส่วนที่นำเข้า">
          {ORDER.map(navBtn)}
          <div className="hr" style={{ margin: "6px 0" }} />
          <button className={tab === "check" ? "on" : ""} onClick={() => setTab("check")}>
            <span className="n"><Ic name="ai" size={13} /></span>
            <span>AI ตรวจความสอดคล้อง<span className="small faint" style={{ display: "block", fontWeight: 400 }}>พบจุดที่ควรตรวจ {checks.filter((c) => c.status !== "pass" && c.status !== "info").length} รายการ</span></span>
          </button>
          <button className={tab === "preview" ? "on" : ""} onClick={() => setTab("preview")}>
            <span className="n"><Ic name="eye" size={13} /></span>
            <span>Preview แบบเล่มหลักสูตร<span className="small faint" style={{ display: "block", fontWeight: 400 }}>Markdown ตาม developer prompt</span></span>
          </button>
          <div className="small faint" style={{ padding: "8px 10px 2px" }}>ยืนยันแล้ว {okN}/{total} ส่วน (POC {total} ส่วน)</div>
        </nav>

        <div className="stack" style={{ minWidth: 0 }}>
          {tab === "check" && <ChecksView checks={checks} go={setTab} />}
          {tab === "preview" && (
            <section className="stack">
              {["1-program_info.md", "8-teachers.md", "9-admission_plan.md", "2-course_structure.md", "4-plos.md", "4b-ksec.md", "3b-modules.md", "3-courses_list.md", "5-curriculum_mapping.md", "7-approval.md"].map((n) => (
                <div key={n} className="card pad stack">
                  <div className="between"><b>{n}</b><a className="btn sm" href={api.fileUrl(id, `extract/md/${n}`)} target="_blank">เปิดไฟล์</a></div>
                  {preview[n] ? <Markdown text={preview[n]} /> : <div className="small faint">กำลังโหลด…</div>}
                </div>
              ))}
              <div className="card pad between"><b>เล่มทั้งเล่ม (Markdown)</b><a className="btn sm" href={api.fileUrl(id, "ingest/book.md")} target="_blank">book.md</a></div>
            </section>
          )}
          {ORDER.includes(tab) && !part && <div className="card pad">กำลังโหลด…</div>}
          {ORDER.includes(tab) && part && part.part === tab && (
            <>
              <div className="between">
                <div>
                  <span className="av" style={{ background: "var(--red)", color: "#fff" }}>{ORDER.indexOf(tab) + 1}</span>{" "}
                  <b>{PART_LABELS[tab][0]}</b> <span className="small faint">· {PART_LABELS[tab][1]}</span>{" "}
                  {part.confirmed && <Pill kind="ok">ยืนยันแล้ว</Pill>} {part.edited && <Pill kind="info">แก้ไขแล้ว {part.edit_count} ครั้ง</Pill>} {dirty && <Pill kind="warn">ยังไม่บันทึก</Pill>}
                </div>
                <div className="row">
                  <button className="btn" disabled={saving || !dirty} onClick={() => save(false)}>บันทึกร่าง</button>
                  <button className="btn primary" disabled={saving || job.status === "done"} onClick={() => save(true)}>
                    <Ic name="check" size={16} /> ยืนยันส่วนนี้ แล้วไปส่วนถัดไป
                  </button>
                </div>
              </div>
              <div className="grid" style={{ gridTemplateColumns: "minmax(0,.8fr) minmax(0,1.4fr)" }}>
                <SourcePanel src={src} page={page} setPage={setPage} hit={hit} filename={job.filename} />
                <section className="card pad stack" style={{ minWidth: 0 }}>
                  {tab === "info" && data && <InfoEditor data={data as unknown as InfoData} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "structure" && data && <StructureEditor data={data as { total_credits: number | null; tree: Node[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "modules" && data && <ModulesEditor data={data as unknown as ModulesData} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "plan" && data && <PlanEditor data={data as unknown as PlanData} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "teachers" && data && <TeachersEditor data={data as { teachers: Teacher[]; responsible_count: number }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "appr" && data && <ApprEditor data={data as unknown as ApprData} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "ksec" && data && <KsecEditor data={data as { plos: KsecPlo[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "plo" && data && <PloEditor data={data as { plos: Plo[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "courses" && data && (
                    <CoursesEditor data={data as { courses: Course[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} open={openDesc} setOpen={setOpenDesc} />
                  )}
                  {tab === "mapping" && data && (
                    <MappingEditor data={data as MapData} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />
                  )}
                  {part.notes && part.notes.length > 0 && <div className="small faint">หมายเหตุจากระบบ: {part.notes.join(" · ")}</div>}
                </section>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );

  function pick(m?: Meta | null) {
    if (!m?.source) return;
    if (m.source.page) setPage(m.source.page);
    setHit(m.source.snippet || "");
  }
}

function firstPage(key: string, data: Record<string, unknown> | null): number | null {
  if (!data) return null;
  const metaPage = (m?: Meta) => m?.source?.page ?? null;
  if (key === "info") {
    const metas = (data.meta as Record<string, Meta | undefined>) ?? {};
    return metaPage(metas.name_th) ?? metaPage(metas.program_code) ?? metaPage(Object.values(metas).find((m) => m?.source?.page));
  }
  if (key === "structure") return metaPage(((data.tree as Node[]) ?? [])[0]?.meta) ?? metaPage((data.meta as { total_credits?: Meta })?.total_credits);
  if (key === "modules") return metaPage(((data.modules as Module[]) ?? [])[0]?.meta);
  if (key === "plan") return metaPage(((data.plans as PlanTable[]) ?? [])[0]?.meta);
  if (key === "teachers") return metaPage(((data.teachers as Teacher[]) ?? [])[0]?.meta);
  if (key === "appr") return metaPage(((data.approvals as ApprRow[]) ?? [])[0]?.meta) ?? metaPage((data.meta as Record<string, Meta | undefined>)?.status);
  if (key === "ksec") return metaPage(((data.plos as KsecPlo[]) ?? [])[0]?.meta);
  if (key === "plo") return metaPage(((data.plos as Plo[]) ?? [])[0]?.meta);
  if (key === "courses") return metaPage(((data.courses as Course[]) ?? [])[0]?.meta);
  if (key === "mapping") return metaPage(((data.rows as MapRow[]) ?? [])[0]?.meta);
  return null;
}

function SourcePanel({ src, page, setPage, hit, filename }: { src: { page: number; pages: number | null; blocks: Array<Record<string, unknown>> } | null; page: number | null; setPage: (p: number) => void; hit: string; filename: string }) {
  const key = hit.slice(0, 24);
  return (
    <section className="card pad stack" style={{ minWidth: 0 }}>
      <div className="between">
        <b>ต้นฉบับ · หน้า {page ?? "–"}{src?.pages ? ` / ${src.pages}` : ""}</b>
        <span className="row" style={{ gap: 4 }}>
          <button className="btn xs" disabled={!page || page <= 1} onClick={() => page && setPage(page - 1)}>‹</button>
          <button className="btn xs" disabled={!page || (src?.pages ? page >= src.pages : false)} onClick={() => page && setPage(page + 1)}>›</button>
        </span>
      </div>
      <div className="small faint" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filename}</div>
      <div style={{ background: "#fff", color: "#211F22", borderRadius: 8, border: "1px solid var(--line)", padding: 12, fontSize: 12.5, lineHeight: 1.8, minHeight: 360, maxHeight: 640, overflow: "auto" }}>
        {!src && <span className="faint">คลิกแถวทางขวาเพื่อเปิดหน้าต้นฉบับ</span>}
        {src?.blocks.map((b, i) => {
          if (b.kind === "table") {
            const rows = b.rows as string[][];
            return (
              <table key={i} className="src-tbl">
                <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} className={key && c.includes(key) ? "hit" : ""}>{c}</td>)}</tr>)}</tbody>
              </table>
            );
          }
          if (b.kind === "image") return <div key={i} className="small faint">[รูป {String(b.path)}]</div>;
          const text = String(b.text ?? "");
          const isHit = key && text.includes(key);
          return <div key={i} className={`src-block ${b.level ? "h" : ""} ${isHit ? "hit" : ""}`}>{text}</div>;
        })}
      </div>
    </section>
  );
}

function InfoEditor({ data, onChange, pick }: { data: InfoData; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const fields = data.fields ?? [];
  const values = data.values ?? {};
  const metas = data.meta ?? {};
  const groups = Array.from(new Set(fields.map((f) => f.group)));
  const setValue = (key: string, v: unknown) => { const c = structuredClone(data); c.values[key] = v; onChange(c as unknown as Record<string, unknown>); };
  const setRow = (list: "majors" | "collaborations" | "careers", i: number, f: string, v: string) => {
    const c = structuredClone(data);
    (c[list][i] as unknown as Record<string, unknown>)[f] = v;
    onChange(c as unknown as Record<string, unknown>);
  };
  const addRow = (list: "majors" | "collaborations" | "careers") => {
    const c = structuredClone(data);
    const blank = list === "majors" ? { name: "" } : list === "collaborations" ? { institution: "", country: null, domestic: true } : { group: null, name: "" };
    (c[list] as unknown[]).push(blank);
    onChange(c as unknown as Record<string, unknown>);
  };
  const delRow = (list: "majors" | "collaborations" | "careers", i: number) => {
    const c = structuredClone(data);
    (c[list] as unknown[]).splice(i, 1);
    onChange(c as unknown as Record<string, unknown>);
  };
  const inferred = fields.filter((f) => metas[f.key]?.inferred && values[f.key] != null).length;
  const empty = fields.filter((f) => values[f.key] == null || values[f.key] === "").length;
  const input = (f: InfoField) => {
    const v = values[f.key];
    const stop = (e: React.SyntheticEvent) => e.stopPropagation();
    if (f.kind === "enum") {
      const opts = f.options ?? [];
      return (
        <select className="inp" value={typeof v === "string" ? v : ""} onChange={(e) => setValue(f.key, e.target.value || null)} onClick={stop}>
          <option value="">– ไม่ระบุ –</option>
          {(typeof v === "string" && !opts.includes(v) ? [v, ...opts] : opts).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    if (f.kind === "bool") {
      return (
        <select className="inp" value={v === true ? "1" : v === false ? "0" : ""} onChange={(e) => setValue(f.key, e.target.value === "" ? null : e.target.value === "1")} onClick={stop}>
          <option value="">– ไม่ระบุ –</option><option value="1">ใช่</option><option value="0">ไม่ใช่</option>
        </select>
      );
    }
    if (f.kind === "int") {
      return <input className="inp" inputMode="numeric" value={v == null ? "" : String(v)} onChange={(e) => { const t = e.target.value.replace(/\D/g, ""); setValue(f.key, t === "" ? null : Number(t)); }} onClick={stop} />;
    }
    if (f.kind === "list") {
      return <input className="inp" value={Array.isArray(v) ? v.join("; ") : ""} placeholder="คั่นด้วย ;" onChange={(e) => setValue(f.key, e.target.value.split(";").map((s) => s.trim()).filter(Boolean))} onClick={stop} />;
    }
    return <input className="inp" value={typeof v === "string" ? v : v == null ? "" : String(v)} onChange={(e) => setValue(f.key, e.target.value || null)} onClick={stop} />;
  };
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row small faint">
        ฟิลด์ {fields.length} · <Pill kind="warn">อนุมานโดยระบบ {inferred}</Pill> <Pill kind="grey">ว่าง {empty}</Pill> คลิกป้ายชื่อฟิลด์เพื่อเปิดหน้าต้นฉบับ · ฟิลด์ที่ระบบอนุมานเองมีป้าย &ldquo;อนุมาน&rdquo; ต้องยืนยัน
      </div>
      {groups.map((g) => (
        <div key={g} className="stack" style={{ gap: 8 }}>
          <b>{g}</b>
          <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 10 }}>
            {fields.filter((f) => f.group === g).map((f) => {
              const m = metas[f.key];
              const low = m?.confidence === "low" || (values[f.key] == null && ["name_th", "name_en", "level", "degree_full_th", "total_credits", "start_year"].includes(f.key));
              return (
                <div key={f.key} className={`field card pad ${low ? "low" : ""}`} style={{ padding: 10, background: "var(--surface-2)", gridColumn: f.kind === "text" && ["name_th", "name_en", "degree_full_th", "degree_full_en", "previous_program", "collaboration_text", "admission_text", "language_text", "program_type_text"].includes(f.key) ? "1 / -1" : undefined }}>
                  <label style={{ cursor: m?.source?.page ? "pointer" : undefined }} onClick={() => pick(m)}>
                    {f.label} {m?.inferred && <Pill kind="warn">อนุมาน</Pill>} {m && <ConfPill meta={m} />} {m?.source?.page && <span className="small faint">หน้า {m.source.page}</span>}
                  </label>
                  {input(f)}
                </div>
              );
            })}
          </div>
        </div>
      ))}
      <SimpleRows title="วิชาเอก/แขนงวิชา" rows={data.majors ?? []} cols={[["name", "ชื่อวิชาเอก/แขนง"]]} onSet={(i, f, v) => setRow("majors", i, f, v)} onAdd={() => addRow("majors")} onDel={(i) => delRow("majors", i)} pick={pick} empty="ไม่มี" />
      <SimpleRows title="ความร่วมมือกับสถาบันอื่น" rows={data.collaborations ?? []} cols={[["institution", "สถาบัน"], ["country", "ประเทศ"]]} onSet={(i, f, v) => setRow("collaborations", i, f, v)} onAdd={() => addRow("collaborations")} onDel={(i) => delRow("collaborations", i)} pick={pick} empty={String(values.collaboration_text ?? "ไม่มี")} />
      <SimpleRows title="อาชีพที่ประกอบได้หลังสำเร็จการศึกษา" rows={data.careers ?? []} cols={[["group", "กลุ่ม/วิชาเอก"], ["name", "อาชีพ"]]} onSet={(i, f, v) => setRow("careers", i, f, v)} onAdd={() => addRow("careers")} onDel={(i) => delRow("careers", i)} pick={pick} empty="ไม่พบ" />
    </div>
  );
}

function SimpleRows({ title, rows, cols, onSet, onAdd, onDel, pick, empty }: { title: string; rows: Array<Record<string, unknown>>; cols: [string, string][]; onSet: (i: number, f: string, v: string) => void; onAdd: () => void; onDel: (i: number) => void; pick: (m?: Meta | null) => void; empty: string }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="between"><b>{title} <span className="small faint">({rows.length})</span></b><button className="btn xs" onClick={onAdd}>+ เพิ่มแถว</button></div>
      {rows.length === 0 ? <div className="small faint">{empty}</div> : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>{cols.map(([k, l]) => <th key={k}>{l}</th>)}<th>หน้า</th><th></th></tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const m = r.meta as Meta | undefined;
                return (
                  <tr key={i} className="click" onClick={() => pick(m)}>
                    {cols.map(([k]) => <td key={k}><input className="cell" value={r[k] == null ? "" : String(r[k])} onChange={(e) => onSet(i, k, e.target.value)} onClick={(e) => e.stopPropagation()} /></td>)}
                    <td>{m?.source?.page ?? "–"}</td>
                    <td><button className="btn xs ghost" onClick={(e) => { e.stopPropagation(); onDel(i); }}>ลบ</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StructureEditor({ data, onChange, pick }: { data: { total_credits: number | null; tree: Node[] }; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const rows = useMemo(() => flatten(data.tree ?? []), [data.tree]);
  const update = (path: number[], field: "name" | "credits", value: string) => {
    const copy = structuredClone(data);
    let node: Node | undefined;
    let list = copy.tree;
    for (const idx of path) { node = list[idx]; list = node.children; }
    if (!node) return;
    if (field === "name") node.name = value;
    else node.credits = value === "" ? null : Number(value);
    onChange(copy);
  };
  return (
    <>
      <div className="row"><b>หน่วยกิตตลอดหลักสูตร</b><input className="inp" style={{ maxWidth: 120 }} value={data.total_credits ?? ""} onChange={(e) => onChange({ ...data, total_credits: e.target.value === "" ? null : Number(e.target.value) })} /><span className="small faint">หน่วยกิต</span></div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>#</th><th>หมวด / กลุ่มวิชา</th><th className="r">หน่วยกิต</th><th>หน้า</th><th>ความมั่นใจ</th></tr></thead>
          <tbody>
            {rows.map(({ node, path, depth }) => (
              <tr key={path.join(".")} className={`click ${node.meta?.confidence === "low" ? "low" : ""}`} onClick={() => pick(node.meta)}>
                <td className="num">{node.number}</td>
                <td><input className="cell" style={{ paddingLeft: 8 + depth * 18 }} value={node.name} onChange={(e) => update(path, "name", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                <td className="r"><input className="cell num" style={{ maxWidth: 80, textAlign: "right" }} value={node.credits ?? ""} onChange={(e) => update(path, "credits", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                <td>{node.meta?.source?.page ?? "–"}</td>
                <td><ConfPill meta={node.meta} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function flatten(tree: Node[], path: number[] = [], depth = 0): { node: Node; path: number[]; depth: number }[] {
  return tree.flatMap((n, i) => [{ node: n, path: [...path, i], depth }, ...flatten(n.children ?? [], [...path, i], depth + 1)]);
}

function PloEditor({ data, onChange, pick }: { data: { plos: Plo[] }; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const set = (i: number, f: "code" | "text", v: string) => { const c = structuredClone(data); c.plos[i][f] = v; onChange(c); };
  return (
    <div className="stack" style={{ gap: 10 }}>
      {(data.plos ?? []).map((p, i) => (
        <div key={i} className={`card pad stack ${p.meta?.confidence === "low" ? "low" : ""}`} style={{ gap: 8, background: "var(--surface-2)", cursor: "pointer" }} onClick={() => pick(p.meta)}>
          <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start", gap: 10 }}>
            <div className="field" style={{ width: 110, flexShrink: 0 }}><label>รหัส</label><input className="inp" value={p.code} onChange={(e) => set(i, "code", e.target.value)} onClick={(e) => e.stopPropagation()} /></div>
            <div className="field" style={{ flex: 1 }}><label>ข้อความ PLO</label><textarea className="inp" rows={2} style={{ height: "auto", padding: 8 }} value={p.text} onChange={(e) => set(i, "text", e.target.value)} onClick={(e) => e.stopPropagation()} /></div>
            <div style={{ paddingTop: 22 }}><ConfPill meta={p.meta} /> <span className="small faint">หน้า {p.meta?.source?.page ?? "–"}</span></div>
          </div>
          {p.sub_plos?.length > 0 && <div className="small">{p.sub_plos.map((s) => <div key={s.code}>　<b>{s.code}</b> {s.text}</div>)}</div>}
        </div>
      ))}
      {(data.plos ?? []).length === 0 && <Note kind="warn">ไม่พบ PLO ในหมวดที่ 3 · กรอกด้วยมือได้ใน R1</Note>}
    </div>
  );
}

function CoursesEditor({ data, onChange, pick, open, setOpen }: { data: { courses: Course[] }; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void; open: Record<string, boolean>; setOpen: (o: Record<string, boolean>) => void }) {
  const set = (i: number, f: keyof Course, v: string) => { const c = structuredClone(data); (c.courses[i] as unknown as Record<string, unknown>)[f] = v; onChange(c); };
  const courses = data.courses ?? [];
  const low = courses.filter((c) => c.meta?.confidence === "low").length;
  return (
    <>
      <div className="row small faint">
        รายวิชา {courses.length} · <Pill kind="red">ความมั่นใจต่ำ {low}</Pill> คลิกแถวเพื่อเปิดหน้าต้นฉบับ · ▾ เปิดคำอธิบาย
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>รหัส</th><th>ชื่อวิชา (ไทย)</th><th>รหัส/ชื่อ (อังกฤษ)</th><th>หน่วยกิต</th><th>กลุ่ม</th><th>หน้า</th><th>ความมั่นใจ</th><th></th></tr></thead>
          <tbody>
            {courses.map((c, i) => (
              <Fragment key={c.code_th + i}>
                <tr className={`click ${c.meta?.confidence === "low" ? "low" : ""}`} onClick={() => pick(c.meta)}>
                  <td><input className="cell" style={{ minWidth: 80 }} value={c.code_th} onChange={(e) => set(i, "code_th", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                  <td><input className="cell" style={{ minWidth: 220 }} value={c.name_th ?? ""} onChange={(e) => set(i, "name_th", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                  <td><input className="cell" style={{ minWidth: 200 }} value={[c.code_en, c.name_en].filter(Boolean).join(" ")} onChange={(e) => { const [code, ...rest] = e.target.value.split(" "); const cp = structuredClone(data); cp.courses[i].code_en = code || null; cp.courses[i].name_en = rest.join(" ") || null; onChange(cp); }} onClick={(e) => e.stopPropagation()} /></td>
                  <td><input className="cell" style={{ minWidth: 90 }} value={c.credit_text ?? ""} onChange={(e) => set(i, "credit_text", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                  <td className="small">{c.module || c.group || ""}</td>
                  <td>{c.meta?.source?.page ?? "–"}</td>
                  <td><ConfPill meta={c.meta} /></td>
                  <td><button className="btn xs ghost" onClick={(e) => { e.stopPropagation(); setOpen({ ...open, [c.code_th]: !open[c.code_th] }); }}>{open[c.code_th] ? "▴" : "▾"}</button></td>
                </tr>
                {(open[c.code_th] || c.meta?.confidence === "low") && (
                  <tr>
                    <td colSpan={8} style={{ background: "var(--surface-2)" }}>
                      {c.meta?.note && <div className="note warn" style={{ marginBottom: 8 }}><b>ต้องตรวจ:</b> {c.meta.note}</div>}
                      <div className="field"><label>คำอธิบายรายวิชา (ไทย)</label><textarea className="cell" rows={3} value={c.description_th ?? ""} onChange={(e) => set(i, "description_th", e.target.value)} /></div>
                      {c.description_en && <div className="small muted" style={{ marginTop: 6 }}>{c.description_en}</div>}
                      {c.prerequisite && <div className="small" style={{ marginTop: 6 }}>บุรพวิชา: {c.prerequisite}</div>}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const degreeLine = (d: Degree) => `${d.degree}${d.field ? ` (${d.field})` : ""}${d.year ? `, ${d.year}` : ""}${d.institution ? ` – ${d.institution}` : ""}`;
const parseDegreeLine = (line: string): Degree | null => {
  const t = line.trim();
  if (!t) return null;
  const [left, inst] = t.split(/\s+[–-]\s+/, 2);
  const y = /,\s*((?:25|19|20)\d\d)\s*$/.exec(left);
  const head = y ? left.slice(0, y.index) : left;
  const f = /\((.+)\)\s*$/.exec(head);
  const degree = (f ? head.slice(0, f.index) : head).trim();
  const level = /ด\.$|^Ph\.?D|^D\.|^DEc/i.test(degree) ? "เอก" : /ม\.$|^M\.|^MBA|^MSc|^PDSC/i.test(degree) ? "โท" : /บ\.$|^B\./i.test(degree) ? "ตรี" : null;
  return { degree, field: f ? f[1].trim() : null, year: y ? Number(y[1]) : null, level, institution: inst?.trim() || null };
};

function ModulesEditor({ data, onChange, pick }: { data: ModulesData; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const mods = data.modules ?? [];
  const set = (i: number, f: keyof Module, v: unknown) => { const c = structuredClone(data); (c.modules[i] as unknown as Record<string, unknown>)[f] = v; onChange(c as unknown as Record<string, unknown>); };
  const add = () => { const c = structuredClone(data); c.modules.push({ number: String(c.modules.length + 1), name_th: "", name_en: null, credits: null, counted: true, group: null, description_th: null, description_en: null, course_codes: [] }); onChange(c as unknown as Record<string, unknown>); };
  const del = (i: number) => { const c = structuredClone(data); c.modules.splice(i, 1); onChange(c as unknown as Record<string, unknown>); };
  const noDesc = mods.filter((m) => !m.description_th).length;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="between">
        <div className="row small faint">ชุดวิชา {mods.length} · <Pill kind="warn">ไม่มีคำอธิบาย {noDesc}</Pill> {(data.groups ?? []).map((g) => `${g.name} ${g.declared_modules ?? "–"} ชุด`).join(" · ")} · คลิกหัวข้อเพื่อเปิดหน้าต้นฉบับ</div>
        <button className="btn xs" onClick={add}>+ เพิ่มชุดวิชา</button>
      </div>
      {mods.length === 0 && <Note kind="warn">ไม่พบชุดวิชาในหมวดที่ 4 (เล่มอาจไม่ใช้ชุดวิชา)</Note>}
      {mods.map((m, i) => (
        <div key={i} className={`card pad stack ${m.meta?.note ? "low" : ""}`} style={{ gap: 8, background: "var(--surface-2)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8 }}>
            <span className="small faint" style={{ paddingBottom: 12, whiteSpace: "nowrap", cursor: "pointer" }} onClick={() => pick(m.meta)}>{m.number} · หน้า {m.meta?.source?.page ?? "–"}</span>
            <div className="field" style={{ flex: "1 1 220px" }}><label>ชื่อชุดวิชา (ไทย)</label><input className="inp" value={m.name_th} onChange={(e) => set(i, "name_th", e.target.value)} /></div>
            <div className="field" style={{ flex: "1 1 180px" }}><label>ชื่ออังกฤษ</label><input className="inp" value={m.name_en ?? ""} onChange={(e) => set(i, "name_en", e.target.value || null)} /></div>
            <div className="field" style={{ flex: "0 0 90px" }}><label>หน่วยกิต</label><input className="inp" value={m.counted === false ? "ไม่นับ" : m.credits ?? ""} onChange={(e) => { const t = e.target.value.trim(); if (t === "ไม่นับ") { set(i, "counted", false); } else { const c = structuredClone(data); c.modules[i].counted = true; c.modules[i].credits = t ? Number(t.replace(/\D/g, "")) || null : null; onChange(c as unknown as Record<string, unknown>); } }} /></div>
            <div className="field" style={{ flex: "0 1 160px" }}><label>กลุ่ม{m.major ? ` · ${m.major}` : ""}</label><input className="inp" value={m.group ?? ""} onChange={(e) => set(i, "group", e.target.value || null)} /></div>
            <button className="btn xs ghost" style={{ marginBottom: 8 }} onClick={() => del(i)}>ลบ</button>
          </div>
          <div className="field"><label>คำอธิบายชุดวิชา (ไทย) {!m.description_th && <Pill kind="red">ไม่พบ</Pill>}</label><textarea className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={m.description_th ?? ""} onChange={(e) => set(i, "description_th", e.target.value || null)} /></div>
          {(m.description_en || false) && <div className="small muted">{m.description_en}</div>}
          <div className="field"><label>รายวิชาในชุด (รหัส คั่นด้วยช่องว่าง)</label><input className="inp" value={(m.course_codes ?? []).join(" ")} onChange={(e) => set(i, "course_codes", e.target.value.split(/[\s,;]+/).filter(Boolean))} /></div>
        </div>
      ))}
    </div>
  );
}

const MODES = ["On-site", "Online", "Hybrid", "WIL"];

function PlanEditor({ data, onChange, pick }: { data: PlanData; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const plans = data.plans ?? [];
  const commit = (c: PlanData) => {
    c.intake_per_year = c.plans.reduce((n, p) => n + (p.rows[0]?.values[0] ?? 0), 0);
    onChange(c as unknown as Record<string, unknown>);
  };
  const setCell = (pi: number, kind: "row" | "total" | "graduates", ri: number, yi: number, v: string) => {
    const c = structuredClone(data);
    const n = v === "" ? 0 : Number(v.replace(/\D/g, ""));
    if (kind === "row") c.plans[pi].rows[ri].values[yi] = n;
    else {
      const arr = (c.plans[pi][kind] ?? c.plans[pi].years.map(() => 0)).slice();
      arr[yi] = n;
      c.plans[pi][kind] = arr;
    }
    commit(c);
  };
  const setName = (pi: number, v: string) => { const c = structuredClone(data); c.plans[pi].name = v || null; commit(c); };
  const toggleMode = (m: string) => { const c = structuredClone(data); const s = new Set(c.teaching_modes ?? []); if (s.has(m)) s.delete(m); else s.add(m); c.teaching_modes = MODES.filter((x) => s.has(x)); commit(c); };
  const num = (arr: number[] | null | undefined, i: number) => String(arr?.[i] ?? 0);
  const modeMeta = data.meta?.teaching_modes;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row small faint">แผนการรับ {plans.length} ตาราง · รับปีละ {data.intake_per_year ?? "–"} คน · คลิกชื่อแผนเพื่อเปิดหน้าต้นฉบับ</div>
      {plans.length === 0 && <Note kind="warn">ไม่พบตารางแผนการรับนิสิตในหมวดที่ 2 ข้อ 4</Note>}
      {plans.map((p, pi) => (
        <div key={pi} className="card pad stack" style={{ gap: 8, background: "var(--surface-2)" }}>
          <div className="row" style={{ flexWrap: "nowrap", alignItems: "center" }} onClick={() => pick(p.meta)}>
            <input className="inp" style={{ maxWidth: 320 }} value={p.name ?? ""} placeholder="ชื่อแผน/วิชาเอก (ถ้ามี)" onChange={(e) => setName(pi, e.target.value)} onClick={(e) => e.stopPropagation()} />
            <span className="small faint">หน้า {p.meta?.source?.page ?? "–"}</span>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>จำนวนนิสิต</th>{p.years.map((y) => <th key={y} className="c">{y}</th>)}</tr></thead>
              <tbody>
                {p.rows.map((r, ri) => (
                  <tr key={r.label}><td>{r.label}</td>{p.years.map((y, yi) => <td key={y} className="c"><input className="cell" style={{ width: 64, textAlign: "center" }} value={String(r.values[yi] ?? 0)} onChange={(e) => setCell(pi, "row", ri, yi, e.target.value)} /></td>)}</tr>
                ))}
                <tr style={{ fontWeight: 600 }}><td>รวม</td>{p.years.map((y, yi) => <td key={y} className="c"><input className="cell" style={{ width: 64, textAlign: "center" }} value={num(p.total, yi)} onChange={(e) => setCell(pi, "total", 0, yi, e.target.value)} /></td>)}</tr>
                <tr><td>คาดว่าจะสำเร็จการศึกษา</td>{p.years.map((y, yi) => <td key={y} className="c"><input className="cell" style={{ width: 64, textAlign: "center" }} value={num(p.graduates, yi)} onChange={(e) => setCell(pi, "graduates", 0, yi, e.target.value)} /></td>)}</tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <div className="card pad stack" style={{ gap: 8, background: "var(--surface-2)" }}>
        <div><b>รูปแบบการสอน</b> {modeMeta?.inferred && <Pill kind="warn">อนุมาน</Pill>} <span className="small faint">{modeMeta?.note}</span></div>
        <div className="row">
          {MODES.map((m) => (
            <label key={m} className="row small" style={{ gap: 6, cursor: "pointer" }}><input type="checkbox" checked={(data.teaching_modes ?? []).includes(m)} onChange={() => toggleMode(m)} /> {m}</label>
          ))}
        </div>
      </div>
      {(data.teaching_methods ?? []).length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <b>วิธีการสอนตามผลลัพธ์การเรียนรู้ (หมวดที่ 5)</b>
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ผลลัพธ์</th><th>วิธีการสอน</th><th>หน้า</th></tr></thead><tbody>
            {data.teaching_methods.map((x, i) => <tr key={i} className="click" onClick={() => pick(x.meta)}><td className="small">{x.outcome}</td><td className="small">{x.methods}</td><td>{x.meta?.source?.page ?? "–"}</td></tr>)}
          </tbody></table></div>
        </div>
      )}
    </div>
  );
}

function TeachersEditor({ data, onChange, pick }: { data: { teachers: Teacher[]; responsible_count: number }; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const rows = data.teachers ?? [];
  const commit = (c: { teachers: Teacher[]; responsible_count: number }) => { c.responsible_count = c.teachers.filter((t) => t.responsible).length; onChange(c as unknown as Record<string, unknown>); };
  const set = (i: number, f: keyof Teacher, v: unknown) => { const c = structuredClone(data); (c.teachers[i] as unknown as Record<string, unknown>)[f] = v; commit(c); };
  const setDegrees = (i: number, text: string) => {
    const c = structuredClone(data);
    const ds = text.split("\n").map(parseDegreeLine).filter((d): d is Degree => d !== null);
    c.teachers[i].degrees = ds;
    const order: Record<string, number> = { เอก: 3, โท: 2, ตรี: 1 };
    c.teachers[i].highest_level = ds.reduce<string | null>((best, d) => ((order[d.level ?? ""] ?? 0) > (order[best ?? ""] ?? 0) ? d.level : best), null);
    commit(c);
  };
  const add = () => { const c = structuredClone(data); c.teachers.push({ order: c.teachers.length + 1, responsible: false, rank: null, doctor: false, name: "", group: null, degrees: [], institutions_text: null, highest_level: null }); commit(c); };
  const del = (i: number) => { const c = structuredClone(data); c.teachers.splice(i, 1); commit(c); };
  const odd = rows.filter((t) => t.meta?.note).length;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="between">
        <div className="row small faint">อาจารย์ประจำ {rows.length} คน · ผู้รับผิดชอบ {rows.filter((t) => t.responsible).length} คน · <Pill kind="warn">ต้องตรวจวุฒิ/สถาบัน {odd}</Pill> คลิกชื่อเพื่อเปิดหน้าต้นฉบับ · คุณวุฒิบรรทัดละ 1 วุฒิ: วุฒิ (สาขา), ปี – สถาบัน</div>
        <button className="btn xs" onClick={add}>+ เพิ่มอาจารย์</button>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>#</th><th>ผู้รับผิดชอบ</th><th>ตำแหน่ง</th><th>ดร.</th><th>ชื่อ-นามสกุล</th><th>วิชาเอก</th><th>คุณวุฒิ ตรี-โท-เอก</th><th>หน้า</th><th></th></tr></thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={i} className={t.meta?.note ? "low" : ""} title={t.meta?.note ?? ""}>
                <td>{t.order ?? ""}</td>
                <td className="c"><input type="checkbox" checked={t.responsible} onChange={(e) => set(i, "responsible", e.target.checked)} /></td>
                <td>
                  <select className="cell" value={t.rank ?? ""} onChange={(e) => set(i, "rank", e.target.value || null)}>
                    <option value="">–</option>{["อาจารย์", "ผศ.", "รศ.", "ศ."].map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="c"><input type="checkbox" checked={t.doctor} onChange={(e) => set(i, "doctor", e.target.checked)} /></td>
                <td onClick={() => pick(t.meta)} style={{ cursor: "pointer" }}><input className="cell" style={{ minWidth: 180 }} value={t.name} onChange={(e) => set(i, "name", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                <td><input className="cell" style={{ minWidth: 120 }} value={t.group ?? ""} onChange={(e) => set(i, "group", e.target.value || null)} /></td>
                <td><textarea className="cell" rows={Math.max(2, t.degrees.length)} style={{ minWidth: 340, fontSize: 12 }} defaultValue={t.degrees.map(degreeLine).join("\n")} onBlur={(e) => setDegrees(i, e.target.value)} />{t.meta?.note && <div className="small faint">{t.meta.note}{t.institutions_text ? ` · สถาบันตามเล่ม: ${t.institutions_text}` : ""}</div>}</td>
                <td>{t.meta?.source?.page ?? "–"}</td>
                <td><button className="btn xs ghost" onClick={() => del(i)}>ลบ</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && <Note kind="warn">ไม่พบตารางอาจารย์ในข้อ 11–12</Note>}
    </div>
  );
}

function ApprEditor({ data, onChange, pick }: { data: ApprData; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const rows = data.approvals ?? [];
  const setField = (k: keyof ApprData, v: unknown) => { const c = structuredClone(data); (c as unknown as Record<string, unknown>)[k] = v; onChange(c as unknown as Record<string, unknown>); };
  const setRow = (i: number, f: "level" | "meeting_no" | "resolution", v: string) => { const c = structuredClone(data); c.approvals[i][f] = v || (f === "meeting_no" ? null : "") as never; onChange(c as unknown as Record<string, unknown>); };
  const setDate = (i: number, v: string) => { const c = structuredClone(data); c.approvals[i].date = v ? { text: v, iso: null } : null; c.approvals[i].pending = !v && !c.approvals[i].meeting_no; onChange(c as unknown as Record<string, unknown>); };
  const addRow = (level: string) => { const c = structuredClone(data); c.approvals.push({ level_key: "other", level, meeting_no: null, date: null, resolution: "เห็นชอบ", pending: true }); onChange(c as unknown as Record<string, unknown>); };
  const delRow = (i: number) => { const c = structuredClone(data); c.approvals.splice(i, 1); onChange(c as unknown as Record<string, unknown>); };
  const num = (v: unknown) => (v == null ? "" : String(v));
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row small faint">มติ {rows.filter((r) => !r.pending).length} ระดับ · <Pill kind="warn">เล่มเว้นว่าง {rows.filter((r) => r.pending).length}</Pill> คลิกชื่อระดับเพื่อเปิดหน้าต้นฉบับ</div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 10 }}>
        <div className="field card pad" style={{ padding: 10, background: "var(--surface-2)" }}>
          <label onClick={() => pick(data.meta?.status)} style={{ cursor: "pointer" }}>สถานภาพ {data.meta?.status && <ConfPill meta={data.meta.status} />}</label>
          <select className="inp" value={data.status ?? ""} onChange={(e) => setField("status", e.target.value || null)}><option value="">– ไม่ระบุ –</option><option value="ใหม่">หลักสูตรใหม่</option><option value="ปรับปรุง">หลักสูตรปรับปรุง</option></select>
        </div>
        <div className="field card pad" style={{ padding: 10, background: "var(--surface-2)" }}>
          <label>เริ่มใช้ ภาค / ปีการศึกษา</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="inp" style={{ width: 70 }} value={num(data.start_semester)} onChange={(e) => setField("start_semester", e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null)} />
            <input className="inp" value={num(data.start_year)} onChange={(e) => setField("start_year", e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null)} />
          </div>
        </div>
        <div className="field card pad" style={{ padding: 10, background: "var(--surface-2)", gridColumn: "1 / -1" }}>
          <label>ปรับปรุงจากหลักสูตร (ฉบับเดิม) · พ.ศ.</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="inp" value={data.previous_program ?? ""} onChange={(e) => setField("previous_program", e.target.value || null)} />
            <input className="inp" style={{ width: 90 }} value={num(data.previous_year)} onChange={(e) => setField("previous_year", e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null)} />
          </div>
        </div>
      </div>
      <div className="between"><b>มติอนุมัติ/เห็นชอบ</b><button className="btn xs" onClick={() => addRow("อว. รับทราบความเห็นชอบหลักสูตร")}>+ เพิ่มระดับ</button></div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>ระดับ</th><th>ครั้งที่</th><th>วันที่ประชุม</th><th>มติ</th><th>หน้า</th><th></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.level_key + i} className={r.pending ? "low" : ""}>
                <td onClick={() => pick(r.meta)} style={{ cursor: "pointer" }}><input className="cell" style={{ minWidth: 220 }} value={r.level} onChange={(e) => setRow(i, "level", e.target.value)} onClick={(e) => e.stopPropagation()} /></td>
                <td><input className="cell" style={{ minWidth: 80 }} value={r.meeting_no ?? ""} placeholder="เช่น 6/2569" onChange={(e) => setRow(i, "meeting_no", e.target.value)} /></td>
                <td><input className="cell" style={{ minWidth: 150 }} value={r.date?.text ?? ""} placeholder="11 สิงหาคม 2569" onChange={(e) => setDate(i, e.target.value)} /></td>
                <td><input className="cell" style={{ minWidth: 90 }} value={r.resolution ?? ""} onChange={(e) => setRow(i, "resolution", e.target.value)} /></td>
                <td>{r.meta?.source?.page ?? "–"}{r.pending && <span className="small faint"> · เล่มเว้นว่าง</span>}</td>
                <td><button className="btn xs ghost" onClick={() => delRow(i)}>ลบ</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(data.missing_levels ?? []).length > 0 && <Note kind="warn">ยังไม่มีมติ: {data.missing_levels.join(" · ")} · กรอกเมื่อได้รับหนังสือ</Note>}
    </div>
  );
}

function KsecEditor({ data, onChange, pick }: { data: { plos: KsecPlo[] }; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const plos = data.plos ?? [];
  const set = (pi: number, ii: number, f: keyof KsecItem, v: string) => { const c = structuredClone(data); (c.plos[pi].items[ii] as unknown as Record<string, unknown>)[f] = v || null; onChange(c); };
  const add = (pi: number) => { const c = structuredClone(data); c.plos[pi].items.push({ code: "", category: "K", subtype: null, text: "" }); onChange(c); };
  const del = (pi: number, ii: number) => { const c = structuredClone(data); c.plos[pi].items.splice(ii, 1); onChange(c); };
  const total = plos.reduce((n, p) => n + (p.items?.length ?? 0), 0);
  const odd = plos.reduce((n, p) => n + p.items.filter((it) => it.meta?.note).length, 0);
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row small faint">KSEC {total} รายการใน {plos.length} PLO · <Pill kind="warn">อยู่ผิดคอลัมน์ด้าน {odd}</Pill> คลิกหัว PLO เพื่อเปิดหน้าต้นฉบับ · รหัสใช้รูปแบบ K1-1 (เล่มที่เขียน K1.1 ถูกแปลงให้)</div>
      {plos.length === 0 && <Note kind="warn">ไม่พบตาราง PLO × ด้าน K/S/E/C ในหมวดที่ 3 · เพิ่มด้วยมือได้ใน R1</Note>}
      {plos.map((p, pi) => (
        <div key={p.code + (p.plan ?? "") + pi} className="card pad stack" style={{ gap: 8, background: "var(--surface-2)" }}>
          <div className="between" style={{ cursor: "pointer" }} onClick={() => pick(p.meta)}>
            <div><b>{p.code}</b> {p.plan && <Pill kind="info">{p.plan}</Pill>} {p.group && <Pill kind="grey">{p.group}</Pill>} <span className="small faint">· {p.items.length} รายการ · หน้า {p.meta?.source?.page ?? "–"}</span><div className="small">{p.text}</div></div>
            <button className="btn xs" onClick={(e) => { e.stopPropagation(); add(pi); }}>+ เพิ่มรายการ</button>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>รหัส</th><th>ด้าน</th><th>ประเภท</th><th>รายละเอียด</th><th>หน้า</th><th></th></tr></thead>
              <tbody>
                {p.items.map((it, ii) => (
                  <tr key={it.code + ii} className={it.meta?.note ? "low" : ""} title={it.meta?.note ?? ""}>
                    <td><input className="cell" style={{ minWidth: 80 }} value={it.code} onChange={(e) => set(pi, ii, "code", e.target.value)} /></td>
                    <td>
                      <select className="cell" value={it.category} onChange={(e) => set(pi, ii, "category", e.target.value)}>
                        {["K", "S", "E", "C"].map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </td>
                    <td>
                      <select className="cell" value={it.subtype ?? ""} onChange={(e) => set(pi, ii, "subtype", e.target.value)}>
                        <option value="">–</option><option value="ทั่วไป">ทั่วไป</option><option value="ลักษณะเฉพาะ">ลักษณะเฉพาะ</option>
                      </select>
                    </td>
                    <td><input className="cell" style={{ minWidth: 320 }} value={it.text} onChange={(e) => set(pi, ii, "text", e.target.value)} /></td>
                    <td>{it.meta?.source?.page ?? "–"}</td>
                    <td><button className="btn xs ghost" onClick={() => del(pi, ii)}>ลบ</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function MappingEditor({ data, onChange, pick }: { data: MapData; onChange: (d: Record<string, unknown>) => void; pick: (m?: Meta | null) => void }) {
  const plos = data.plo_codes ?? [];
  const rows = data.rows ?? [];
  const kcols = data.ksec_columns ?? [];
  const krows = data.ksec_rows ?? [];
  const setCodes = (i: number, col: string, text: string) => {
    const c = structuredClone(data);
    const r = c.ksec_rows![i];
    r.by_column[col] = text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    r.ksec_codes = (c.ksec_columns ?? []).flatMap((k) => r.by_column[k] ?? []);
    r.plos = Array.from(new Set((c.ksec_columns ?? []).filter((k) => (r.by_column[k] ?? []).length > 0).map((k) => "PLO" + k.slice(1))));
    onChange(c);
  };
  const toggle = (i: number, plo: string) => {
    const c = structuredClone(data);
    const set = new Set(c.rows[i].plos);
    if (set.has(plo)) set.delete(plo); else set.add(plo);
    c.rows[i].plos = plos.filter((p) => set.has(p));
    onChange(c);
  };
  const flagged = rows.map((r, i) => ({ r, head: r.group && (i === 0 || rows[i - 1].group !== r.group) ? r.group : null }));
  return (
    <>
      <div className="row small faint">รายวิชา {rows.length} × PLO {plos.length} · คลิกช่องเพื่อสลับ ● · คลิกชื่อวิชาเพื่อเปิดหน้าต้นฉบับ</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>รายวิชา</th>{plos.map((p) => <th key={p} className="c">{p}</th>)}<th>หน้า</th></tr></thead>
          <tbody>
            {flagged.map(({ r, head }, i) => {
              return (
                <Fragment key={r.course_code + i}>
                  {head && <tr><td colSpan={plos.length + 2} style={{ background: "var(--surface-2)", fontWeight: 600 }}>{head}</td></tr>}
                  <tr className={`click ${r.plos.length === 0 ? "low" : ""}`}>
                    <td onClick={() => pick(r.meta)}>{r.course_code} <span className="small faint">{r.course_name}</span></td>
                    {plos.map((p) => (
                      <td key={p} className="c" onClick={() => toggle(i, p)} style={{ cursor: "pointer", fontSize: 16 }}>{r.plos.includes(p) ? "●" : <span style={{ color: "var(--line-2)" }}>·</span>}</td>
                    ))}
                    <td>{r.meta?.source?.page ?? "–"}</td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {kcols.length > 0 && (
        <>
          <div className="row small faint" style={{ marginTop: 10 }}><b>4.2 รายวิชา × KSEC</b> · รายวิชา {krows.length} · พิมพ์รหัสคั่นด้วยช่องว่างหรือจุลภาค (เช่น K1-1 K1-2)</div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>รายวิชา</th>{kcols.map((k) => <th key={k} className="c">{k}</th>)}<th>หน้า</th></tr></thead>
              <tbody>
                {krows.map((r, i) => (
                  <tr key={r.course_code + i} className="click">
                    <td onClick={() => pick(r.meta)} style={{ whiteSpace: "nowrap" }}>{r.course_code} <span className="small faint">{r.course_name}</span></td>
                    {kcols.map((k) => (
                      <td key={k}><input className="cell" style={{ minWidth: 64, fontSize: 12 }} value={(r.by_column?.[k] ?? []).join(" ")} onChange={(e) => setCodes(i, k, e.target.value)} /></td>
                    ))}
                    <td>{r.meta?.source?.page ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function ChecksView({ checks, go }: { checks: Check[]; go: (t: string) => void }) {
  const kind: Record<Check["status"], "ok" | "warn" | "red" | "info"> = { pass: "ok", warn: "warn", fail: "red", info: "info" };
  const label: Record<Check["status"], string> = { pass: "ผ่าน", warn: "ควรตรวจ", fail: "พบปัญหา", info: "ข้อมูล" };
  const n = (s: Check["status"]) => checks.filter((c) => c.status === s).length;
  return (
    <section className="card pad stack">
      <div className="between">
        <h2 className="h2">AI ตรวจความสอดคล้องของเล่มหลักสูตร</h2>
        <span className="row">
          <Pill kind="ok">ผ่าน {n("pass")}</Pill><Pill kind="warn">ควรตรวจ {n("warn")}</Pill><Pill kind="red">พบปัญหา {n("fail")}</Pill><Pill kind="info">ข้อมูล {n("info")}</Pill>
        </span>
      </div>
      <div className="small faint">ตรวจด้วยกฎในโค้ด (หน่วยกิตรวม หน่วยกิตกลุ่มย่อย รหัสซ้ำ ฟิลด์ครบ) ไม่ใช่ความเห็นของ AI</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>ผลการตรวจ</th><th>รายละเอียด</th><th>ส่วน</th><th></th></tr></thead>
          <tbody>
            {checks.map((c) => (
              <tr key={c.key}>
                <td><Pill kind={kind[c.status]}>{label[c.status]}</Pill></td>
                <td>{c.message}</td>
                <td className="small">{PART_LABELS[c.part]?.[0] ?? c.part}</td>
                <td><button className="btn xs" onClick={() => go(c.part)}>ไปที่ส่วน</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note kind="info">หัวข้อในเล่มที่ไม่นำเข้าเป็นฟิลด์ (ปรัชญา คุณสมบัติผู้เข้าศึกษา งบประมาณ หมวด 5–8 ภาคผนวก) ถูกเก็บไว้ใน Markdown ทั้งเล่ม ดูได้ที่ Preview</Note>
    </section>
  );
}
