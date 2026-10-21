"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, PART_LABELS, type Check, type Job, type Meta, type Part } from "@/lib/api";
import { ConfPill, Ic, Markdown, Note, PageHead, Pill, Steps } from "@/components/ui";

const ORDER = ["info", "teachers", "plan", "plo", "ksec", "structure", "modules", "courses", "mapping", "appr"];
type Tab = string; // part key | "check" | "preview"

type Node = { number: string; level: number; name: string; credits: number | null; children: Node[]; meta?: Meta; plan?: boolean };
type Plo = { code: string; text: string; sub_plos: { code: string; text: string; meta?: Meta }[]; meta?: Meta };
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
  const [tab, setTab] = useState<Tab>("structure");
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
          ["2-course_structure.md", "4-plos.md", "3-courses_list.md"].map((n) => api.fileText(id, `extract/md/${n}`).then((t) => [n, t] as const)),
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
          <div className="small faint" style={{ padding: "8px 10px 2px" }}>ยืนยันแล้ว {okN}/{total} ส่วน (POC 3 ส่วน)</div>
        </nav>

        <div className="stack" style={{ minWidth: 0 }}>
          {tab === "check" && <ChecksView checks={checks} go={setTab} />}
          {tab === "preview" && (
            <section className="stack">
              {["2-course_structure.md", "4-plos.md", "3-courses_list.md"].map((n) => (
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
                  {tab === "structure" && data && <StructureEditor data={data as { total_credits: number | null; tree: Node[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "plo" && data && <PloEditor data={data as { plos: Plo[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} />}
                  {tab === "courses" && data && (
                    <CoursesEditor data={data as { courses: Course[] }} onChange={(d) => { setData(d); setDirty(true); }} pick={(m) => pick(m)} open={openDesc} setOpen={setOpenDesc} />
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
  if (key === "structure") return metaPage(((data.tree as Node[]) ?? [])[0]?.meta) ?? metaPage((data.meta as { total_credits?: Meta })?.total_credits);
  if (key === "plo") return metaPage(((data.plos as Plo[]) ?? [])[0]?.meta);
  if (key === "courses") return metaPage(((data.courses as Course[]) ?? [])[0]?.meta);
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
