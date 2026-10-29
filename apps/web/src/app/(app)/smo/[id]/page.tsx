"use client";

// smo-new / smo-view (mock · US-M1-09 10): one สมอ.08 request. While it is a draft or sent
// back, its creator (or central) fills the form: items 1–3 of the form, the kinds of change,
// the teacher list of the whole book or one แขนง with a live comparison, reasons, attachments.
// Once sent, whoever holds the current step approves it or sends it back; after the last step
// the API replaces หมวด 0.2 of the curriculum (FS-3 Q3 ก).
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { personsApi, smoApi, usersApi, type PersonPick, type SmoDetail, type Staff } from "@/lib/api";
import { SMO_KIND, changes, inScope, type Change, type Teacher } from "@/lib/smo";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Field, Modal, Timeline, useToast, type Step } from "@/components/kit";

const LEVELS = ["ตรี", "โท", "เอก"];
const CH_KIND: Record<Change["change"], "ok" | "warn" | "red"> = { "เพิ่ม": "ok", "แก้ไข": "warn", "นำออก": "red" };

export default function SmoPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [d, setD] = useState<SmoDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState<{ types: string[]; scope: SmoDetail["scope"]; fields: Record<string, string>; after: Teacher[]; details: Record<string, string>; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [act, setAct] = useState<"approve" | "return" | null>(null);
  const [note, setNote] = useState("");

  const fill = (x: SmoDetail) => {
    setD(x);
    setForm({ types: x.types, scope: x.scope, fields: x.fields, after: (x.teachers.after ?? []) as Teacher[], details: x.details, reason: x.reason ?? "" });
  };
  useEffect(() => { smoApi.get(id).then(fill).catch((e) => setErr((e as Error).message)); }, [id]);

  const before = useMemo(() => (d?.teachers.before ?? []) as Teacher[], [d]);
  const branches = useMemo(() => [...new Set(before.map((t) => t.group).filter(Boolean) as string[])].sort(), [before]);
  const live = useMemo(() => {
    if (!form) return [];
    const mine = form.after.filter((t) => inScope(t, form.scope));
    return changes(before.filter((t) => inScope(t, form.scope)), mine);
  }, [before, form]);

  async function run(fn: () => Promise<SmoDetail>, msg: string) {
    setBusy(true);
    try { fill(await fn()); toast(msg); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  const save = () => run(() => smoApi.save(id, form!), "บันทึกร่าง สมอ.08 แล้ว");
  const submit = () => run(async () => { await smoApi.save(id, form!); return smoApi.act(id, "submit"); }, "ส่งคำขอเข้าสู่ขั้นตอนอนุมัติแล้ว");

  if (err) return <><BackLink href="/smo">กลับไปรายการ สมอ.08</BackLink><Note kind="warn">{err}</Note></>;
  if (!d || !form) return <div className="card pad">กำลังโหลด…</div>;
  const edit = d.can_edit;
  const setF = (k: string, v: string) => setForm((x) => x && { ...x, fields: { ...x.fields, [k]: v } });
  const scoped = form.after.map((t, i) => [t, i] as const).filter(([t]) => inScope(t, form.scope));
  const setT = (i: number, p: Partial<Teacher>) => setForm((x) => x && { ...x, after: x.after.map((t, k) => (k === i ? { ...t, ...p } : t)) });
  const addT = (t: Teacher) => setForm((x) => x && { ...x, after: [...x.after, { ...t, group: x.scope.kind === "child" ? x.scope.branch : t.group }] });
  const shownChanges = edit ? live : d.changes;

  const timeline: Step[] = d.steps.map((s, i) => {
    const done = d.status === "approved" || i < d.step;
    const ev = [...d.events].reverse().find((e) => e.step === i && ["submit", "approve", "return"].includes(e.action));
    return {
      title: `${i + 1}. ${s.position || s.label}${s.position ? ` (${s.label})` : ""}`,
      detail: ev ? `${ev.action === "return" ? "ส่งคืนแก้ไข" : "ดำเนินการแล้ว"} · ${ev.by} · ${ev.ts.slice(0, 16).replace("T", " ")}${ev.note ? ` · "${ev.note}"` : ""}` : i === d.step && d.status === "pending" ? "รอดำเนินการ" : undefined,
      state: done ? "done" : i === d.step && d.status === "returned" ? "rej" : i === d.step && d.status === "pending" ? "cur" : undefined,
    };
  });

  return (
    <>
      <BackLink href="/smo">กลับไปรายการ สมอ.08</BackLink>
      <PageHead crumb={["บริหารข้อมูลหลักสูตร", "สมอ.08"]} title={`คำขอ ${d.id}`}
        sub={<><Pill kind={SMO_KIND[d.status]}>{d.status_th}</Pill> · {d.curriculum.name_th} · {d.status === "pending" ? `ขั้นตอนปัจจุบัน: ${d.step_label}` : d.step_label}</>}
        actions={<>
          <Link className="btn" href={`/smo/${d.id}/print`}>Preview แบบ สมอ.08</Link>
          {edit && <button type="button" className="btn" disabled={busy} onClick={save}>บันทึกร่าง</button>}
          {edit && <button type="button" className="btn primary" disabled={busy} onClick={submit}>ส่งขออนุมัติ</button>}
          {d.can_act && <button type="button" className="btn" disabled={busy} onClick={() => { setAct("return"); setNote(""); }}>ส่งคืนแก้ไข</button>}
          {d.can_act && <button type="button" className="btn primary" disabled={busy} onClick={() => { setAct("approve"); setNote(""); }}>อนุมัติขั้นตอนนี้</button>}
        </>} />
      {d.status === "returned" && <Note kind="warn">ส่งคืนแก้ไข: {[...d.events].reverse().find((e) => e.action === "return")?.note}</Note>}
      <div className="dash-grid">
        <div className="stack">
          <section className="card pad stack">
            <h2 className="h2">ข้อมูลหลักสูตร</h2>
            <div className="form-grid">
              <Field label="หลักสูตร" pulled="คู่มือหลักสูตร">{(fid) => <input id={fid} className="inp" disabled value={d.curriculum.name_th ?? ""} />}</Field>
              <Field label="ฉบับปี พ.ศ." pulled="SUPREME">{(fid) => <input id={fid} className="inp" disabled value={String(d.curriculum.edition_year ?? "")} />}</Field>
              <Field label="คณะ" pulled="SUPREME">{(fid) => <input id={fid} className="inp" disabled value={d.curriculum.faculty ?? ""} />}</Field>
              <Field label="1. สป.อว. รับทราบ/รับรองการเปิดสอนเมื่อวันที่">{(fid) => <input id={fid} className="inp" disabled={!edit} placeholder="[วัน เดือน ปี]" value={form.fields.ack_date ?? ""} onChange={(e) => setF("ack_date", e.target.value)} />}</Field>
              <Field label="2. สภามหาวิทยาลัยอนุมัติการปรับปรุงแก้ไข ครั้งที่ / วันที่">{(fid) => <input id={fid} className="inp" disabled={!edit} placeholder="[ครั้งที่ / วันที่]" value={form.fields.council ?? ""} onChange={(e) => setF("council", e.target.value)} />}</Field>
              <Field label="3. เริ่มใช้กับนิสิตรุ่นปีการศึกษา (ภาค/ปี)">{(fid) => (
                <div className="row" style={{ flexWrap: "nowrap" }}>
                  <select id={fid} className="inp" disabled={!edit} value={form.fields.start_term ?? ""} onChange={(e) => setF("start_term", e.target.value)}><option value="">— ภาค —</option><option>ภาคเรียนที่ 1</option><option>ภาคเรียนที่ 2</option></select>
                  <input className="inp" aria-label="ปีการศึกษา" disabled={!edit} placeholder="2570" value={form.fields.start_year ?? ""} onChange={(e) => setF("start_year", e.target.value)} />
                </div>
              )}</Field>
            </div>
          </section>
          <section className="card pad stack">
            <h2 className="h2">4. รายละเอียดการปรับปรุงแก้ไข</h2>
            <div className="row" style={{ gap: 14 }}>
              {Object.entries({ teacher: "อาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร", course: "รายวิชา", plan: "แผนการศึกษา", other: "อื่น ๆ" }).map(([k, l]) => (
                <label key={k} className="row" style={{ gap: 6 }}><input type="checkbox" disabled={!edit} checked={form.types.includes(k)} onChange={(e) => setForm((x) => x && { ...x, types: e.target.checked ? [...x.types, k] : x.types.filter((t) => t !== k) })} /> {l}</label>
              ))}
            </div>
            {form.types.includes("teacher") && (
              <div className="card pad stack" style={{ background: "var(--surface-2)" }}>
                <div className="row" style={{ gap: 12 }}>
                  <b className="small">ขอบเขตการแก้ไข</b>
                  <div className="seg">
                    <button type="button" className={form.scope.kind === "mother" ? "on" : ""} disabled={!edit} onClick={() => setForm((x) => x && { ...x, scope: { kind: "mother" } })}>เล่มแม่ (ทั้งหลักสูตร)</button>
                    <button type="button" className={form.scope.kind === "child" ? "on" : ""} disabled={!edit || !branches.length} title={branches.length ? undefined : "หลักสูตรนี้ไม่มีแขนงในหมวด 0.2"} onClick={() => setForm((x) => x && { ...x, scope: { kind: "child", branch: branches[0] } })}>เล่มลูก (เฉพาะแขนง)</button>
                  </div>
                  {form.scope.kind === "child" && <select className="inp" style={{ maxWidth: 240 }} aria-label="แขนงวิชา" disabled={!edit} value={form.scope.branch} onChange={(e) => setForm((x) => x && { ...x, scope: { kind: "child", branch: e.target.value } })}>{branches.map((b) => <option key={b}>{b}</option>)}</select>}
                </div>
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead><tr><th>ชื่อ-นามสกุล</th><th>ตำแหน่ง</th><th>คุณวุฒิ</th><th>ผู้รับผิดชอบ</th><th>ประธาน</th>{edit && <th />}</tr></thead>
                    <tbody>
                      {scoped.map(([t, i]) => (
                        <tr key={i}>
                          <td><input className="inp" aria-label={`อาจารย์ ${i + 1}: ชื่อ`} disabled={!edit} value={t.name ?? ""} onChange={(e) => setT(i, { name: e.target.value })} /><span className="small faint">{t.pid ?? t.xid ?? ""}</span></td>
                          <td><input className="inp" aria-label={`อาจารย์ ${i + 1}: ตำแหน่ง`} disabled={!edit} value={t.rank ?? ""} onChange={(e) => setT(i, { rank: e.target.value })} /></td>
                          <td><select className="inp" aria-label={`อาจารย์ ${i + 1}: คุณวุฒิ`} disabled={!edit} value={t.highest_level ?? ""} onChange={(e) => setT(i, { highest_level: e.target.value || null })}><option value="">—</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></td>
                          <td><input type="checkbox" aria-label={`อาจารย์ ${i + 1}: ผู้รับผิดชอบ`} disabled={!edit} checked={!!t.responsible} onChange={(e) => setT(i, { responsible: e.target.checked })} /></td>
                          <td><input type="radio" name="smo-chair" aria-label={`อาจารย์ ${i + 1}: ประธาน`} disabled={!edit} checked={!!t.chair} onChange={() => setForm((x) => x && { ...x, after: x.after.map((y, k) => ({ ...y, chair: k === i })) })} /></td>
                          {edit && <td><button type="button" className="btn xs" onClick={() => setForm((x) => x && { ...x, after: x.after.filter((_, k) => k !== i) })}>นำออก</button></td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {edit && <AddTeacher onAdd={addT} />}
              </div>
            )}
            <b>Preview เทียบเดิม/ใหม่ ({shownChanges.length} รายการ)</b>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>การเปลี่ยนแปลง</th><th>เดิม</th><th>ใหม่</th></tr></thead>
                <tbody>
                  {shownChanges.map((c, i) => <tr key={i}><td><Pill kind={CH_KIND[c.change]}>{c.change}</Pill></td><td className="small">{who(c.before)}</td><td className="small">{who(c.after)}</td></tr>)}
                  {!shownChanges.length && <tr><td colSpan={3} className="small faint">ยังไม่มีการเปลี่ยนแปลงรายชื่ออาจารย์</td></tr>}
                </tbody>
              </table>
            </div>
            {(["course", "plan", "other"] as const).filter((k) => form.types.includes(k)).map((k) => (
              <Field key={k} full label={`รายละเอียดการแก้ไข${{ course: "รายวิชา", plan: "แผนการศึกษา", other: "อื่น ๆ" }[k]}`}>{(fid) => <textarea id={fid} className="inp" rows={3} style={{ height: "auto", padding: 8 }} disabled={!edit} value={form.details[k] ?? ""} onChange={(e) => setForm((x) => x && { ...x, details: { ...x.details, [k]: e.target.value } })} />}</Field>
            ))}
            {form.types.includes("course") && <Note kind="info">การแก้ข้อมูลรายวิชาจริง (รหัส ชื่อ หน่วยกิต คำอธิบาย) ทำที่เมนู บริหารรายวิชา ส่วนนี้บันทึกรายละเอียดเป็นข้อความประกอบคำขอ</Note>}
            <Field full label="เหตุผลในการปรับปรุงแก้ไข">{(fid) => <textarea id={fid} className="inp" rows={3} style={{ height: "auto", padding: 8 }} disabled={!edit} placeholder="[เหตุผล]" value={form.reason} onChange={(e) => setForm((x) => x && { ...x, reason: e.target.value })} />}</Field>
            <b>เอกสารแนบ</b>
            <div className="row" style={{ gap: 6 }}>
              {d.files.map((f) => <a key={f.id} className="pill p-grey" href={smoApi.fileUrl(d.id, f.id)} target="_blank" rel="noreferrer">{f.name}</a>)}
              {!d.files.length && <span className="small faint">ยังไม่มีเอกสารแนบ</span>}
            </div>
            {edit && (
              <label className="btn sm" style={{ alignSelf: "flex-start" }}>
                แนบไฟล์ (มติสภาฯ, สมอ.08 ฉบับลงนาม · PDF/Word/รูป ≤ 20 MB)
                <input type="file" hidden accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => smoApi.upload(d.id, f), `แนบไฟล์ ${f.name} แล้ว`); e.target.value = ""; }} />
              </label>
            )}
          </section>
        </div>
        <section className="card pad stack">
          <h2 className="h2">ขั้นตอนการอนุมัติ</h2>
          <Timeline steps={timeline} />
          <span className="small faint">ผู้สร้างคำขอ {d.created_by} · สร้าง {d.created_at.slice(0, 10)} · อนุมัติครบแล้ว ระบบปรับรายชื่ออาจารย์ในหมวด 0.2 ของคู่มือให้เอง</span>
          <Link className="small" href={`/curricula/${d.curriculum.id}`}>เปิดคู่มือหลักสูตร</Link>
        </section>
      </div>
      {act && (
        <Modal open title={act === "approve" ? "อนุมัติขั้นตอนนี้" : "ส่งคืนแก้ไข"} onClose={() => setAct(null)}
          foot={<><button type="button" className="btn" onClick={() => setAct(null)}>ยกเลิก</button><button type="button" className="btn primary" disabled={busy || (act === "return" && !note.trim())} onClick={() => { const a = act; setAct(null); run(() => smoApi.act(d.id, a, note), a === "approve" ? (d.step === d.steps_total - 1 ? "อนุมัติครบทุกขั้นตอน ระบบปรับข้อมูลคู่มือหลักสูตรแล้ว" : "อนุมัติแล้ว ส่งต่อขั้นตอนถัดไป") : "ส่งคืนแก้ไขแล้ว"); }}>{act === "approve" ? "อนุมัติ" : "ส่งคืน"}</button></>}>
          <div className="stack">
            <span className="small">{d.step_label}</span>
            <Field label={act === "approve" ? "ความเห็น (ไม่บังคับ)" : "เหตุผล *"} full>{(fid) => <textarea id={fid} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          </div>
        </Modal>
      )}
    </>
  );
}

const who = (t: Teacher | null) => (t ? `${t.name ?? ""}${t.rank ? ` · ${t.rank}` : ""}${t.highest_level ? ` · ${t.highest_level}` : ""}${t.responsible ? " (ผู้รับผิดชอบ)" : ""}` : "–");

function AddTeacher({ onAdd }: { onAdd: (t: Teacher) => void }) {
  const [q, setQ] = useState("");
  const [staff, setStaff] = useState<Staff[]>([]);
  const [ext, setExt] = useState<PersonPick[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => {
      usersApi.staff(q).then((r) => setStaff(r.items)).catch(() => setStaff([]));
      personsApi.search(q).then(setExt).catch(() => setExt([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  const on = q.trim().length >= 2;
  return (
    <div className="stack" style={{ gap: 4 }}>
      <input className="inp" style={{ maxWidth: 360 }} aria-label="เพิ่มอาจารย์" placeholder="เพิ่มอาจารย์: พิมพ์ชื่อ (HURIS หรือทะเบียนบุคคลภายนอก)" value={q} onChange={(e) => setQ(e.target.value)} />
      {on && staff.map((s) => <button key={s.pid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => { onAdd({ name: `${s.title_short ?? ""}${s.name_th}`, rank: s.title_short, pid: s.pid, responsible: false }); setQ(""); }}><b>{s.title_short}{s.name_th}</b> <span className="small faint">HURIS {s.pid} · {s.faculty}</span></button>)}
      {on && ext.map((x) => <button key={x.xid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => { onAdd({ name: x.name, rank: x.rank, xid: x.xid, highest_level: x.highest_level, responsible: false }); setQ(""); }}><b>{x.name}</b> <span className="small faint">บุคคลภายนอก {x.xid} · {x.org}</span></button>)}
    </div>
  );
}
