"use client";

// plan-edit / rep-edit (mock · US-M2-04 05 06): one plan (6 sections) or report (4 sections)
// of a course or module in a term. Fields marked ดึงอัตโนมัติ come from the central courses,
// the HR copy, the SUPREME timetable and the verified curricula (BR-M2-03), and cannot be typed.
// The fields of plan sections 2–6 and report 2–4 follow the mock [สมมติ: until มคอ.3/มคอ.5].
import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fmtTime, m2Api, type M2Doc, type M2DocData } from "@/lib/api";
import { GRADES, STATUS_KIND, gradeRows, pctSum } from "@/lib/m2";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Field, Modal, Pulled, Timeline, useToast, type Step } from "@/components/kit";

type Data = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const PLAN_SECS = ["ข้อมูลทั่วไป", "ความรับผิดชอบต่อผลลัพธ์การเรียนรู้", "กลยุทธ์การสอนและการประเมินผล", "แผนการจัดการเรียนรู้รายสัปดาห์", "ทรัพยากรประกอบการเรียนการสอน", "การประเมินและปรับปรุง"];
const REP_SECS = ["ข้อมูลทั่วไป", "แผนการพัฒนาและประเมินผู้เรียน", "รายงานผลลัพธ์การเรียนรู้ของผู้เรียน", "การประเมินและการวางแผนปรับปรุง"];
const ACT_TH: Record<string, string> = { save: "บันทึก", submit: "ส่งตรวจสอบ", approve: "รับรอง", return: "ส่งคืนแก้ไข", publish: "เผยแพร่", unpublish: "ยกเลิกเผยแพร่", assign: "กำหนดผู้บันทึก" };

const ta = (v: unknown, on: (s: string) => void, ro: boolean, label: string, rows = 3) => (
  <textarea className="inp" aria-label={label} rows={rows} style={{ height: "auto", padding: 8 }} disabled={ro} value={String(v ?? "")} onChange={(e) => on(e.target.value)} />
);

export function DocPage({ doc }: { doc: M2Doc }) {
  const { slug, key } = useParams<{ slug: string; key: string }>();
  const k = decodeURIComponent(key);
  const toast = useToast();
  const [d, setD] = useState<M2DocData | null>(null);
  const [data, setData] = useState<Data>({});
  const [sec, setSec] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [act, setAct] = useState<"approve" | "return" | null>(null);
  const [note, setNote] = useState("");
  const fill = (x: M2DocData) => { setD(x); setData(structuredClone(x.data)); };
  useEffect(() => { m2Api.doc(slug, k, doc).then(fill).catch((e) => setErr((e as Error).message)); }, [slug, k, doc]);
  const dirty = useMemo(() => !!d && JSON.stringify(d.data) !== JSON.stringify(data), [d, data]);

  async function run(fn: () => Promise<M2DocData>, msg: string) {
    setBusy(true);
    try { fill(await fn()); toast(msg); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  if (err) return <><BackLink href={doc === "plan" ? "/plans" : "/reports"}>กลับไปรายการ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const ro = !d.can_edit;
  const it = d.pulled.item;
  const secs = doc === "plan" ? PLAN_SECS : REP_SECS;
  const set = (s: string, f: string, v: unknown) => setData((x) => ({ ...x, [s]: { ...(x[s] ?? {}), [f]: v } }));
  const title = `${it.kind === "module" ? "ชุดวิชา " : ""}${it.code}${it.kind === "course" && it.name_th ? ` ${it.name_th}` : ""}`;
  const timeline: Step[] = [
    { title: "บันทึก", state: d.status === "none" ? "cur" : "done" },
    ...d.steps.map((s, i) => ({ title: `${s.position || s.label}`, detail: s.label, state: (i === 0 ? (["sent", "approved", "published"].includes(d.status) ? "done" : d.status === "returned" ? "rej" : undefined) : ["approved", "published"].includes(d.status) ? "done" : d.status === "sent" ? "cur" : undefined) as Step["state"] })),
    { title: "เผยแพร่ (ส่วนกลาง)", state: d.status === "published" ? "done" : d.status === "approved" ? "cur" : undefined },
  ];
  const body: Record<number, ReactNode> = doc === "plan" ? planBody(d, data, set, setData, ro) : reportBody(d, data, set, ro);
  return (
    <>
      <BackLink href={doc === "plan" ? "/plans" : "/reports"}>กลับไปรายการ{doc === "plan" ? "แผน" : "รายงานผล"}</BackLink>
      <PageHead crumb={["แผนการจัดการเรียนรู้", doc === "plan" ? "บันทึกแผนการจัดการเรียนรู้" : "บันทึกรายงานการจัดการการเรียนรู้"]}
        title={`${d.doc_th}แบบ${it.kind === "module" ? "ชุดวิชา" : "รายวิชา"}`}
        sub={<><b>{title}</b> · <Pill kind={STATUS_KIND[d.status]}>{d.status_th}</Pill> · ภาค {d.term.term}{!d.window.open && <> · <Pill kind="red">นอกช่วงเวลาบันทึก ({d.window.from ?? "…"} – {d.window.to ?? "…"})</Pill></>}</>}
        actions={<>
          {d.status === "none" && d.can_edit && <button type="button" className="btn" disabled={busy} onClick={() => run(() => m2Api.copy(slug, k, doc), "คัดลอกจากภาคก่อนแล้ว")}>คัดลอกจากภาคก่อน</button>}
          <Link className="btn" href={`/${doc === "plan" ? "plans" : "reports"}/${slug}/${encodeURIComponent(k)}/print`}>Preview</Link>
          {d.can_edit && <button type="button" className="btn" disabled={busy || !dirty} onClick={() => run(() => m2Api.save(slug, k, doc, data), "บันทึกแล้ว")}>{dirty ? "บันทึก" : "บันทึกแล้ว"}</button>}
          {d.can_submit && <button type="button" className="btn primary" disabled={busy} onClick={() => run(async () => { if (dirty) await m2Api.save(slug, k, doc, data); return m2Api.submit(slug, k, doc); }, "ส่งตรวจสอบแล้ว")}>ส่งตรวจสอบ</button>}
          {d.can_certify && <><button type="button" className="btn" onClick={() => { setAct("return"); setNote(""); }}>ส่งคืนแก้ไข</button><button type="button" className="btn primary" onClick={() => { setAct("approve"); setNote(""); }}>รับรอง</button></>}
          {d.can_publish && (d.status === "published"
            ? <button type="button" className="btn" disabled={busy} onClick={() => run(() => m2Api.publish(slug, k, doc, false), "ยกเลิกเผยแพร่แล้ว")}>ยกเลิกเผยแพร่</button>
            : <button type="button" className="btn primary" disabled={busy} onClick={() => run(() => m2Api.publish(slug, k, doc, true), "เผยแพร่แล้ว")}>เผยแพร่</button>)}
        </>} />
      {d.status === "returned" && <Note kind="warn">ส่งคืนแก้ไข: {[...d.events].reverse().find((e) => e.action === "return")?.note}</Note>}
      {d.can_edit && d.missing.length > 0 && <Note kind="warn">ก่อนส่งตรวจสอบยังขาด {d.missing.length} รายการ: {d.missing.join(" · ")}</Note>}
      {!d.recorder && d.can_edit && <Note kind="info">บัญชีนี้ไม่ได้เป็นผู้บันทึก แก้ได้ในฐานะส่วนกลาง</Note>}
      <div className="grid" style={{ gridTemplateColumns: "240px minmax(0,1fr)", alignItems: "start" }}>
        <nav className="card pad stack" aria-label="หมวด" style={{ gap: 4, position: "sticky", top: 80 }}>
          {secs.map((s, i) => (
            <button key={s} type="button" className={`nav-item ${sec === i + 1 ? "active" : ""}`} style={{ color: "inherit" }} onClick={() => setSec(i + 1)}>
              <span>หมวด {i + 1} {s}</span>
            </button>
          ))}
          <div className="hr" />
          <Timeline steps={timeline} />
        </nav>
        <div className="stack">
          <section className="card pad stack">{body[sec]}</section>
          <div className="between">
            <button type="button" className="btn" disabled={sec === 1} onClick={() => setSec(sec - 1)}>‹ หมวดก่อนหน้า</button>
            <button type="button" className="btn" disabled={sec === secs.length} onClick={() => setSec(sec + 1)}>หมวดถัดไป ›</button>
          </div>
          {d.events.length > 0 && (
            <section className="card pad stack">
              <h2 className="h2">ประวัติ</h2>
              {d.events.slice(-8).reverse().map((e, i) => <div key={i} className="small">{fmtTime(e.ts)} · {e.by} · {ACT_TH[e.action] ?? e.action}{e.note ? ` · "${e.note}"` : ""}</div>)}
            </section>
          )}
        </div>
      </div>
      {act && (
        <Modal open title={act === "approve" ? "รับรองเอกสาร" : "ส่งคืนแก้ไข"} onClose={() => setAct(null)}
          foot={<><button type="button" className="btn" onClick={() => setAct(null)}>ยกเลิก</button><button type="button" className="btn primary" disabled={busy || (act === "return" && !note.trim())} onClick={() => { const a = act; setAct(null); run(() => m2Api.certify(slug, k, doc, a === "approve", note), a === "approve" ? "รับรองแล้ว" : "ส่งคืนแก้ไขแล้ว"); }}>{act === "approve" ? "รับรอง" : "ส่งคืน"}</button></>}>
          <Field label={act === "approve" ? "ความเห็น (ไม่บังคับ)" : "เหตุผล *"} full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        </Modal>
      )}
    </>
  );
}

function PulledField({ label, src, value }: { label: string; src: string; value: ReactNode }) {
  return <div className="field"><span className="lbl">{label} <Pulled src={src} /></span><div className="inp" style={{ height: "auto", minHeight: 38, padding: "8px 10px", background: "var(--surface-2)" }}>{value || "–"}</div></div>;
}

function header(d: M2DocData) {
  const it = d.pulled.item;
  const c0 = d.pulled.courses[0] ?? {};
  return (
    <div className="form-grid">
      <PulledField label={`ชื่อ${it.kind === "module" ? "ชุดวิชา" : "รายวิชา"} (ไทย)`} src="คู่มือหลักสูตร" value={it.kind === "module" ? it.code : c0.name_th ?? it.name_th} />
      <PulledField label="(อังกฤษ)" src="คู่มือหลักสูตร" value={it.kind === "module" ? "" : c0.name_en} />
      <PulledField label="หน่วยกิต" src="คู่มือหลักสูตร" value={d.pulled.courses.map((c) => `${c.code_th} ${c.credit_text ?? ""}`).join(", ")} />
      <PulledField label="ภาควิชา/คณะ" src="ระบบบุคลากร" value={it.unit} />
      <PulledField label={`อาจารย์ผู้รับผิดชอบ${it.kind === "module" ? "ชุดวิชา" : "รายวิชา"}`} src="งานกำหนดสิทธิ์" value={it.assign.plan.map((p) => p.name).join(", ")} />
      <PulledField label="อาจารย์ผู้สอน" src="ตารางสอน SUPREME" value={d.pulled.teachers.map((p) => p.name).join(", ")} />
    </div>
  );
}

type Setter = (s: string, f: string, v: unknown) => void;

function planBody(d: M2DocData, data: Data, set: Setter, setData: (fn: (x: Data) => Data) => void, ro: boolean): Record<number, ReactNode> {
  const it = d.pulled.item;
  const s1 = data.s1 ?? {}, s3 = data.s3 ?? {}, s4 = data.s4 ?? {}, s5 = data.s5 ?? {}, s6 = data.s6 ?? {};
  const clos: Data[] = s3.clos ?? [];
  const weeks: Data[] = s4.weeks ?? [];
  const lo = it.kind === "module" ? "MLO" : "CLO";
  const setClo = (i: number, f: string, v: unknown) => set("s3", "clos", clos.map((c, k) => (k === i ? { ...c, [f]: v } : c)));
  const setWeek = (i: number, f: string, v: unknown) => set("s4", "weeks", weeks.map((w, k) => (k === i ? { ...w, [f]: v } : w)));
  const inp = (s: string, f: string, label: string, v: Data) => <Field label={label}>{(id) => <input id={id} className="inp" disabled={ro} value={String(v[f] ?? "")} onChange={(e) => set(s, f, e.target.value)} />}</Field>;
  const sel = (s: string, f: string, label: string, v: Data, opts: string[]) => <Field label={label}>{(id) => <select id={id} className="inp" disabled={ro} value={String(v[f] ?? "")} onChange={(e) => set(s, f, e.target.value)}><option value="">— เลือก —</option>{opts.map((o) => <option key={o}>{o}</option>)}</select>}</Field>;
  const sum = pctSum(clos);
  return {
    1: (<>
      <h2 className="h2">หมวดที่ 1 ข้อมูลทั่วไป</h2>
      {header(d)}
      <div className="form-grid">
        {sel("s1", "status_type", "สถานภาพของวิชา *", s1, ["วิชาบังคับ", "วิชาเลือก"])}
        {inp("s1", "hours_week", "จำนวนชั่วโมงที่สอน / สัปดาห์ *", s1)}
        {sel("s1", "mode", "รูปแบบการสอน *", s1, ["ออนไลน์ 100%", "ออนไซต์ 100%", "ผสมผสาน"])}
        {inp("s1", "consult_hours", "ชั่วโมงให้คำปรึกษา / สัปดาห์", s1)}
        {inp("s1", "contact", "ช่องทางการติดต่ออาจารย์ผู้สอน *", s1)}
        {inp("s1", "appeal", "วิธีการ/ช่องทางสำหรับอุทธรณ์ *", s1)}
        <Field label="วันที่จัดทำหรือปรับปรุงครั้งล่าสุด">{(id) => <input id={id} type="date" className="inp" disabled={ro} value={String(s1.updated_on ?? "")} onChange={(e) => set("s1", "updated_on", e.target.value)} />}</Field>
      </div>
    </>),
    2: (<>
      <h2 className="h2">หมวดที่ 2 ความรับผิดชอบต่อผลลัพธ์การเรียนรู้ <Pulled src="คู่มือหลักสูตร" /></h2>
      <Note kind="info">จาก Curriculum Mapping ของคู่มือหลักสูตรที่ตรวจสอบสำเร็จแล้ว (BR-M2-03) แก้ได้ที่คู่มือหลักสูตรเท่านั้น</Note>
      {d.pulled.plos.map((p) => (
        <div key={p.draft_id} className="stack" style={{ gap: 4 }}>
          <b>{p.curriculum}</b>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>รายวิชา</th>{p.plos.map((x) => <th key={x.code} title={x.text}>{x.code}</th>)}</tr></thead>
              <tbody>{p.rows.map((r) => <tr key={r.course_code}><td className="num">{r.course_code}</td>{p.plos.map((x, i) => <td key={x.code} className="small">{Object.entries(r.by_column ?? {}).filter(([col]) => col.endsWith(String(i + 1))).flatMap(([, v]) => v).join(", ") || (r.plos?.includes(x.code) ? "●" : "○")}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </div>
      ))}
      {!d.pulled.plos.length && <span className="small faint">ยังไม่มีคู่มือหลักสูตรที่ตรวจสอบสำเร็จซึ่งมีรายวิชานี้</span>}
    </>),
    3: (<>
      <h2 className="h2">หมวดที่ 3 กลยุทธ์การสอนและการประเมินผลลัพธ์การเรียนรู้</h2>
      <PulledField label={`คำอธิบาย${it.kind === "module" ? "ชุดวิชา" : "รายวิชา"}`} src="คู่มือหลักสูตร" value={d.pulled.courses.map((c) => c.description_th).filter(Boolean).join(" · ")} />
      <div className="between"><b>การวางแผนกลยุทธ์การสอนและการประเมินผลลัพธ์การเรียนรู้ ({lo}) <Pill kind={Math.round(sum) === 100 ? "ok" : "warn"}>ร้อยละรวม {sum}</Pill></b>{!ro && <button type="button" className="btn xs" onClick={() => set("s3", "clos", [...clos, { code: `${lo}${clos.length + 1}`, criteria: "", pct: "", method: "", standard: "", strategy: "" }])}>เพิ่มแถว</button>}</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>{lo}</th><th>พฤติกรรมบ่งชี้</th><th>ร้อยละ</th><th>วิธีการและเครื่องมือประเมิน</th><th>เกณฑ์การบรรลุ</th><th>กลยุทธ์การสอน</th>{!ro && <th />}</tr></thead>
          <tbody>
            {clos.map((c, i) => (
              <tr key={i}>
                <td className="num"><b>{c.code}</b></td>
                {(["criteria", "pct", "method", "standard", "strategy"] as const).map((f) => <td key={f}>{f === "pct" ? <input className="inp num" style={{ width: 64 }} aria-label={`${c.code} ร้อยละ`} disabled={ro} value={String(c.pct ?? "")} onChange={(e) => setClo(i, "pct", e.target.value)} /> : <textarea className="inp" rows={2} style={{ height: "auto", padding: 6, minWidth: 140 }} aria-label={`${c.code} ${f}`} disabled={ro} value={String(c[f] ?? "")} onChange={(e) => setClo(i, f, e.target.value)} />}</td>)}
                {!ro && <td><button type="button" className="btn xs" onClick={() => set("s3", "clos", clos.filter((_, k) => k !== i))}>ลบ</button></td>}
              </tr>
            ))}
            {!clos.length && <tr><td colSpan={7} className="small faint">ยังไม่มี {lo}</td></tr>}
          </tbody>
        </table>
      </div>
      <b>การใช้ Generative AI ในการสอน การมอบหมายงาน และการประเมินผล (ถ้ามี)</b>
      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 10 }}>
        {(["teach", "assign", "assess"] as const).map((f, i) => <Field key={f} label={["1) การสอน", "2) การมอบหมายภาระงาน", "3) การประเมินการเรียนรู้"][i]}>{() => ta(s3.ai?.[f], (v) => set("s3", "ai", { ...(s3.ai ?? {}), [f]: v }), ro, f)}</Field>)}
      </div>
      <b>เกณฑ์การตัดสินผลการเรียน (เกรด)</b>
      <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 8 }}>
        {(s3.grades ?? []).map((g: [string, number, number], i: number) => (
          <div key={g[0]} className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
            <b style={{ width: 28 }}>{g[0]}</b>
            {[1, 2].map((j) => <input key={j} className="inp num" style={{ height: 34 }} aria-label={`${g[0]} ${j === 1 ? "ต่ำสุด" : "สูงสุด"}`} disabled={ro} value={g[j]} onChange={(e) => set("s3", "grades", (s3.grades ?? []).map((x: (string | number)[], k: number) => (k === i ? x.map((y, m) => (m === j ? Number(e.target.value) || 0 : y)) : x)))} />)}
          </div>
        ))}
      </div>
    </>),
    4: (<>
      <h2 className="h2">หมวดที่ 4 แผนการจัดการเรียนรู้รายสัปดาห์</h2>
      {it.kind === "module" && (
        <div className="row" style={{ gap: 8 }}>
          <span className="small">รูปแบบการจัดการเรียนรู้ของชุดวิชา</span>
          <div className="seg">{([["integrate", "บูรณาการทุกรายวิชา"], ["block", "สอนจบทีละรายวิชา (Block)"], ["parallel", "สอนแต่ละรายวิชาขนานกัน"]] as const).map(([v, l]) => <button key={v} type="button" disabled={ro} className={s4.pattern === v ? "on" : ""} onClick={() => set("s4", "pattern", v)}>{l}</button>)}</div>
        </div>
      )}
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>สัปดาห์</th>{it.kind === "module" && s4.pattern !== "integrate" && <th>รายวิชา</th>}<th>หัวข้อ/รายละเอียด</th><th>ผู้สอน</th><th>ชม.</th><th>วิธีการสอน/สื่อ/กิจกรรม</th><th>การมอบหมายงาน</th>{!ro && <th />}</tr></thead>
          <tbody>
            {weeks.map((w, i) => (
              <tr key={i}>
                <td className="num">{w.week ?? i + 1}</td>
                {it.kind === "module" && s4.pattern !== "integrate" && <td><select className="inp" aria-label={`สัปดาห์ ${i + 1} รายวิชา`} disabled={ro} value={String(w.course ?? "")} onChange={(e) => setWeek(i, "course", e.target.value)}><option value="">—</option>{it.courses.map((c) => <option key={c}>{c}</option>)}</select></td>}
                <td><input className="inp" style={{ minWidth: 200 }} aria-label={`สัปดาห์ ${i + 1} หัวข้อ`} disabled={ro} value={String(w.topic ?? "")} onChange={(e) => setWeek(i, "topic", e.target.value)} /></td>
                <td><select className="inp" aria-label={`สัปดาห์ ${i + 1} ผู้สอน`} disabled={ro} value={String(w.teacher ?? "")} onChange={(e) => setWeek(i, "teacher", e.target.value)}><option value="">—</option>{d.pulled.teachers.map((p) => <option key={p.pid} value={p.name}>{p.name}</option>)}</select></td>
                <td><input className="inp num" style={{ width: 56 }} aria-label={`สัปดาห์ ${i + 1} ชั่วโมง`} disabled={ro} value={String(w.hours ?? "")} onChange={(e) => setWeek(i, "hours", e.target.value)} /></td>
                <td><input className="inp" aria-label={`สัปดาห์ ${i + 1} วิธีการสอน`} disabled={ro} value={String(w.method ?? "")} onChange={(e) => setWeek(i, "method", e.target.value)} /></td>
                <td><input className="inp" aria-label={`สัปดาห์ ${i + 1} งาน`} disabled={ro} value={String(w.assignment ?? "")} onChange={(e) => setWeek(i, "assignment", e.target.value)} /></td>
                {!ro && <td><button type="button" className="btn xs" onClick={() => set("s4", "weeks", weeks.filter((_, k) => k !== i))}>ลบ</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!ro && <div className="row" style={{ gap: 6 }}>
        <button type="button" className="btn xs" onClick={() => set("s4", "weeks", [...weeks, { week: weeks.length + 1, topic: "", hours: "" }])}>เพิ่มสัปดาห์</button>
        {!weeks.length && <button type="button" className="btn xs" onClick={() => setData((x) => ({ ...x, s4: { ...(x.s4 ?? {}), weeks: Array.from({ length: 15 }, (_, i) => ({ week: i + 1, topic: "", hours: "" })) } }))}>สร้าง 15 สัปดาห์</button>}
      </div>}
    </>),
    5: (<>
      <h2 className="h2">หมวดที่ 5 ทรัพยากรประกอบการเรียนการสอน</h2>
      <Field label="1. เอกสารประกอบการสอน / ตำรา / หนังสือ *" full>{() => ta(s5.texts, (v) => set("s5", "texts", v), ro, "ตำรา", 4)}</Field>
      <Field label="2. แหล่งข้อมูลแนะนำ" full>{() => ta(s5.sources, (v) => set("s5", "sources", v), ro, "แหล่งข้อมูล")}</Field>
      <Field label="3. ทรัพยากรอื่น ๆ (ถ้ามี)" full>{() => ta(s5.others, (v) => set("s5", "others", v), ro, "ทรัพยากรอื่น", 2)}</Field>
    </>),
    6: (<>
      <h2 className="h2">หมวดที่ 6 การประเมินและปรับปรุงการดำเนินการของ{it.kind === "module" ? "ชุดวิชา" : "รายวิชา"}</h2>
      {([["participation", "วิธีการให้ผู้เรียนมีส่วนร่วมในการประเมินผลการจัดการเรียนรู้"], ["verify_outcome", "วิธีการที่ใช้ตรวจสอบหรือทวนสอบผลลัพธ์การเรียนรู้"], ["verify_quality", "วิธีการที่ใช้ตรวจสอบหรือทวนสอบคุณภาพการจัดการเรียนรู้"], ["appeal_risk", "วิธีการเมื่อผู้เรียนมีข้ออุทธรณ์ หรือการป้องกันความเสี่ยงจากการจัดการเรียนรู้"]] as const).map(([f, l], i) => (
        <Field key={f} label={`${i + 1}. ${l} *`} full>{() => ta(s6[f], (v) => set("s6", f, v), ro, l)}</Field>
      ))}
    </>),
  };
}

function reportBody(d: M2DocData, data: Data, set: Setter, ro: boolean): Record<number, ReactNode> {
  const r3 = data.r3 ?? {}, r4 = data.r4 ?? {};
  const g = gradeRows(r3.grades ?? {}, Number(r3.withdrawn) || 0, d.pulled.enrolled);
  const clos = d.plan?.clos ?? [];
  return {
    1: (<>
      <h2 className="h2">หมวดที่ 1 ข้อมูลทั่วไป <Pulled src="แผนการจัดการเรียนรู้" /></h2>
      {header(d)}
      <b>กลุ่มเรียน <Pulled src="ตารางสอน SUPREME" /></b>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>รายวิชา</th><th>กลุ่มเรียน</th><th>ผู้สอน</th><th>วัน-เวลา</th><th>ห้อง</th><th className="r">ลงทะเบียน</th></tr></thead>
          <tbody>{d.pulled.sections.map((s, i) => <tr key={i}><td className="num">{s.course_code}</td><td>{s.section}</td><td className="small">{s.teachers.join(", ")}</td><td className="small">{s.schedule}</td><td className="small">{s.room}</td><td className="r num">{s.enrolled}</td></tr>)}</tbody>
        </table>
      </div>
    </>),
    2: (<>
      <h2 className="h2">หมวดที่ 2 แผนการพัฒนาและประเมินผู้เรียน <Pulled src="แผนการจัดการเรียนรู้ หมวด 3" /></h2>
      {d.plan?.status === "none" && <Note kind="warn">ภาคนี้ยังไม่มีแผนการจัดการเรียนรู้</Note>}
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>CLO/MLO</th><th>พฤติกรรมบ่งชี้</th><th>ร้อยละ</th><th>วิธีการประเมิน</th><th>เกณฑ์การบรรลุ</th></tr></thead>
          <tbody>{clos.map((c, i) => <tr key={i}><td><b>{String(c.code ?? "")}</b></td><td>{String(c.criteria ?? "")}</td><td className="num">{String(c.pct ?? "")}</td><td>{String(c.method ?? "")}</td><td>{String(c.standard ?? "")}</td></tr>)}</tbody>
        </table>
      </div>
    </>),
    3: (<>
      <h2 className="h2">หมวดที่ 3 รายงานผลลัพธ์การเรียนรู้ของผู้เรียน</h2>
      <div className="row" style={{ gap: 18 }}>
        <span>นิสิตที่ลงทะเบียน <b className="num">{d.pulled.enrolled}</b> <Pulled src="ตารางสอน SUPREME" /></span>
        <label className="row" style={{ gap: 6 }}>ถอน (W) <input className="inp num" style={{ width: 70 }} aria-label="จำนวนนิสิตที่ถอน" disabled={ro} value={String(r3.withdrawn ?? 0)} onChange={(e) => set("r3", "withdrawn", Number(e.target.value) || 0)} /></label>
        <span>คงอยู่เมื่อสิ้นสุดภาค <b className="num">{g.remaining}</b></span>
      </div>
      {g.over && <Note kind="warn">จำนวนตามเกรดรวมกับที่ถอน ({g.total + (Number(r3.withdrawn) || 0)}) เกินจำนวนลงทะเบียน ({d.pulled.enrolled})</Note>}
      <b>1. ผลการเรียน (เกรด) · [สมมติ] กรอกจำนวนเองจนกว่าจะมีข้อมูลผลการเรียนจาก SUPREME</b>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>เกรด</th><th className="r">จำนวน</th><th className="r">ร้อยละ</th></tr></thead>
          <tbody>
            {g.rows.map((r) => <tr key={r.grade}><td>{r.grade}</td><td className="r"><input className="inp num" style={{ width: 80 }} aria-label={`จำนวนเกรด ${r.grade}`} disabled={ro} value={String(r3.grades?.[r.grade] ?? 0)} onChange={(e) => set("r3", "grades", { ...Object.fromEntries(GRADES.map((x) => [x, r3.grades?.[x] ?? 0])), [r.grade]: Number(e.target.value) || 0 })} /></td><td className="r num">{r.pct}</td></tr>)}
            <tr><td><b>รวม</b></td><td className="r num"><b>{g.total}</b></td><td className="r num">{g.total ? "100.0" : "–"}</td></tr>
          </tbody>
        </table>
      </div>
      <b>2. ภาพรวมการบรรลุผลลัพธ์การเรียนรู้</b>
      <Field label="2.1 นิสิตบรรลุผลลัพธ์การเรียนรู้ เนื่องจาก *" full>{() => ta(r3.achieved, (v) => set("r3", "achieved", v), ro, "บรรลุ")}</Field>
      <Field label="2.2 นิสิตไม่บรรลุผลลัพธ์การเรียนรู้ เนื่องจาก *" full>{() => ta(r3.not_achieved, (v) => set("r3", "not_achieved", v), ro, "ไม่บรรลุ")}</Field>
    </>),
    4: (<>
      <h2 className="h2">หมวดที่ 4 การประเมินและการวางแผนปรับปรุง</h2>
      <Field label="1. ข้อวิพากษ์สำคัญจากที่ประชุมระดับหลักสูตร/ภาควิชา *" full>{() => ta(r4.critique, (v) => set("r4", "critique", v), ro, "ข้อวิพากษ์")}</Field>
      <Field label="2. ข้อเสนอแผนการปรับปรุงสำหรับภาค/ปีการศึกษาถัดไป *" full>{() => ta(r4.improvement, (v) => set("r4", "improvement", v), ro, "แผนปรับปรุง")}</Field>
    </>),
  };
}

/** Preview: the document as a printable A4 (app.css .book). */
export function DocPrint({ doc }: { doc: M2Doc }) {
  const { slug, key } = useParams<{ slug: string; key: string }>();
  const k = decodeURIComponent(key);
  const [d, setD] = useState<M2DocData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { m2Api.doc(slug, k, doc).then(setD).catch((e) => setErr((e as Error).message)); }, [slug, k, doc]);
  if (err) return <Note kind="warn">{err}</Note>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const it = d.pulled.item;
  const body = doc === "plan" ? planBody(d, d.data, () => {}, () => {}, true) : reportBody(d, d.data, () => {}, true);
  return (
    <>
      <div className="between no-print">
        <BackLink href={`/${doc === "plan" ? "plans" : "reports"}/${slug}/${encodeURIComponent(k)}`}>กลับไปหน้าบันทึก</BackLink>
        <button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button>
      </div>
      <article className="book m2-print" aria-label={`Preview ${d.doc_th}`}>
        <table className="book-frame">
          <thead><tr><td><div className="book-run"><span>{d.doc_th} · {it.kind === "module" ? "ชุดวิชา " : ""}{it.code} · ภาค {d.term.term}</span><span>{d.status_th}</span></div></td></tr></thead>
          <tbody><tr><td>
            <header className="book-title"><h1>{d.doc_th}แบบ{it.kind === "module" ? "ชุดวิชา" : "รายวิชา"}</h1><div>{it.code} {it.kind === "course" ? it.name_th : ""} · {it.unit}</div></header>
            {Object.entries(body).map(([n, b]) => <section key={n} style={{ breakBefore: "auto" }}>{b}</section>)}
          </td></tr></tbody>
        </table>
      </article>
    </>
  );
}
