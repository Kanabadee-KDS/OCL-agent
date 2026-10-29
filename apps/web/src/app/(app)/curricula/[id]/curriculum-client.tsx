"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { curricula, fmtTime, PART_LABELS, STATUS_KIND, type CurriculumDetail } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";

const STEPS: [string, string][] = [["import", "ร่างนำเข้าหลักสูตร"], ["review", "คณะตรวจสอบ"], ["verified", "ตรวจสอบสำเร็จ"], ["published", "เผยแพร่แล้ว"]];
const ACTION_TH: Record<string, string> = { create: "เพิ่มหลักสูตร", edit: "แก้ไขข้อมูล", submit: "ส่งให้คณะตรวจสอบ", return: "ส่งคืนเป็นร่าง", check: "ติ๊กตรวจสอบหมวด", verify: "ตรวจสอบสำเร็จ", publish: "เปิดเผยแพร่", unpublish: "ปิดการเผยแพร่" };

export function CurriculumClient() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<CurriculumDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => curricula.get(id).then(setD).catch((e) => setErr((e as Error).message)), [id]);
  useEffect(() => { void load(); }, [load]);

  async function act(action: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setErr(null);
    try {
      setD(await curricula.transition(id, { action, note: note || undefined, ...extra }));
      setNote("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!d) return <>{err ? <Note kind="warn">{err}</Note> : <div className="card pad">กำลังโหลด…</div>}</>;
  const stepIdx = STEPS.findIndex(([k]) => k === d.status);
  const checked = d.faculty_checked ?? {};
  const bothChecked = Boolean(checked["3"] && checked["4"]);
  const sentNote = [...d.events].reverse().find((e) => e.action === "submit" && e.note);
  // who acts at each step comes from the approval settings (flow `curriculum`), via the API
  const canSubmit = d.allowed.submit;
  const canVerify = d.allowed.review;
  const canPublish = d.allowed.publish;
  const stepWho = (i: number) => d.flow.steps[i]?.position || d.flow.steps[i]?.label || "";
  const locked = d.status === "verified" || d.status === "published";
  return (
    <>
      <Link href="/curricula" className="link-btn small" style={{ color: "var(--red-ink)" }}><Ic name="back" size={14} /> กลับไปรายการคู่มือหลักสูตร</Link>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "คู่มือหลักสูตร", d.name_th ?? ""]}
        title={d.name_th ?? "คู่มือหลักสูตร"}
        sub={<>{d.level ?? "–"} · {d.faculty ?? "–"} · เริ่มใช้ {d.start_year ?? "–"} · รหัส สกอ. {d.program_code ?? "–"} · <Pill kind={STATUS_KIND[d.status]}>{d.status_th}</Pill>{d.review_due_at && d.status === "review" && <> · กำหนดตรวจภายใน {d.review_due_at}</>}</>}
        actions={
          <>
            <Link href={`/curricula/${d.id}/preview`} className="btn"><Ic name="eye" size={16} /> Preview แบบเล่ม / PDF</Link>
            <Link href={`/curricula/${d.id}/edit`} className="btn primary"><Ic name="edit" size={16} /> {d.editable.length ? "กรอก/แก้ข้อมูลคู่มือ" : "ดูข้อมูลคู่มือ"}</Link>
            {d.job_id && <Link href={`/import/${d.job_id}`} className="btn"><Ic name="eye" size={16} /> เปิดข้อมูลที่นำเข้า (10 ส่วน)</Link>}
            {d.job_id && <Link href={`/import/${d.job_id}/done`} className="btn"><Ic name="chart" size={16} /> สรุปผลการนำเข้า</Link>}
          </>
        }
      />
      <div className="steps">
        {STEPS.map(([k, label], i) => (
          <div key={k} className={`step ${i < stepIdx ? "done" : i === stepIdx ? "cur" : ""}`}><span className="n">{i < stepIdx ? "✓" : i + 1}</span><span>{label}</span></div>
        ))}
      </div>
      {err && <Note kind="warn">{err}</Note>}
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr)" }}>
        <section className="card pad stack">
          <h2 className="h2">ขั้นตอนถัดไป</h2>
          {d.status === "import" && (
            <>
              <div className="small"><>{d.job_id ? "ร่างจากการนำเข้าด้วย AI" : "ร่างที่เพิ่มเอง"} · ผู้เตรียมร่างกรอกและแก้ทุกหมวดที่ <Link href={`/curricula/${d.id}/edit`}>ข้อมูลคู่มือ</Link></> แล้วส่งให้คณะตรวจสอบหมวด 3–4</div>
              <textarea className="inp" rows={2} style={{ height: "auto", padding: 8 }} placeholder="หมายเหตุถึงคณะ (ไม่บังคับ)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div><button className="btn primary" disabled={!canSubmit || busy} onClick={() => act("submit")}>ส่งให้คณะตรวจสอบ</button>{!canSubmit && <span className="small faint"> · ขั้นนี้ไม่ใช่ของบทบาทคุณ (ดูการตั้งค่าการอนุมัติ)</span>}</div>
            </>
          )}
          {d.status === "review" && (
            <>
              <div className="small">ผู้ตรวจสอบระดับส่วนงานตรวจหมวด 3 (PLO · KSEC) และหมวด 4 (Curriculum Mapping) แก้ได้เฉพาะ 2 หมวดนี้ ส่วนอื่นดูอย่างเดียว</div>
              {sentNote && <Note kind="info">หมายเหตุจากส่วนกลาง ({sentNote.by}): {sentNote.note}</Note>}
              {[["3", "หมวด 3 PLO / KSEC", `/curricula/${d.id}/edit`], ["4", "หมวด 4 Curriculum Mapping", `/curricula/${d.id}/edit`]].map(([s, label, href]) => (
                <label key={s} className="row card pad" style={{ padding: 10, gap: 10, cursor: canVerify ? "pointer" : "default", background: checked[s] ? "var(--ok-soft, #eef7ee)" : "var(--surface-2)" }}>
                  <input type="checkbox" checked={Boolean(checked[s])} disabled={!canVerify || busy} onChange={(e) => act("check", { section: s, checked: e.target.checked })} />
                  <span style={{ flex: 1 }}>{label} <span className="small faint">· ตรวจสอบหมวดนี้แล้ว</span></span>
                  {href && <Link href={href} className="btn xs" onClick={(e) => e.stopPropagation()}>เปิดตรวจ</Link>}
                </label>
              ))}
              <textarea className="inp" rows={2} style={{ height: "auto", padding: 8 }} placeholder="หมายเหตุ (จำเป็นเมื่อส่งคืน)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="row">
                <button className="btn primary" disabled={!canVerify || !bothChecked || busy} onClick={() => act("verify")} title={bothChecked ? "" : "ต้องติ๊กครบ 2 หมวด"}>ตรวจสอบสำเร็จ</button>
                <button className="btn" disabled={!(canVerify || canSubmit) || busy || !note.trim()} onClick={() => act("return")}>ส่งคืนส่วนกลาง</button>
              </div>
            </>
          )}
          {locked && (
            <>
              <Note kind={d.status === "published" ? "ok" : "info"}>ข้อมูลถูกล็อกตั้งแต่ตรวจสอบสำเร็จ ({fmtTime(d.verified_at ?? null)}) การแก้ไขต้องผ่าน สมอ.08 ที่อนุมัติแล้ว (อยู่ใน R2)</Note>
              <div className="row">
                {d.status === "verified" && <button className="btn primary" disabled={!canPublish || busy} onClick={() => act("publish")}>เปิดเผยแพร่</button>}
                {d.status === "published" && <button className="btn" disabled={!canPublish || busy} onClick={() => act("unpublish")}>ปิดการเผยแพร่</button>}
                {!canPublish && <span className="small faint">{stepWho(2)} · ทำได้เฉพาะผู้ดำเนินการขั้นที่ 3 ตามการตั้งค่าการอนุมัติ</span>}
              </div>
            </>
          )}
        </section>
        <section className="card pad stack">
          <h2 className="h2">ข้อมูลคู่มือหลักสูตร</h2>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>หมวด</th><th>แก้ล่าสุด</th><th></th></tr></thead>
              <tbody>
                {Object.entries(d.sections).map(([n, s]) => (
                  <tr key={n}>
                    <td className="small">{s.label}</td>
                    <td className="small">{s.updated_at ? `${fmtTime(s.updated_at)} · ${({ import: "จากการนำเข้า", system: "แปลงจากข้อมูลเดิม" } as Record<string, string>)[s.updated_by ?? ""] ?? s.updated_by}` : "–"}</td>
                    <td>{d.editable.includes(n) ? <Pill kind="info">คุณแก้ได้</Pill> : <Pill kind="grey">ดูอย่างเดียว</Pill>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="small faint">ผลตรวจความสอดคล้อง: <Pill kind="ok">ผ่าน {d.checks.pass}</Pill> <Pill kind="warn">ควรตรวจ {d.checks.warn}</Pill> <Pill kind="red">พบปัญหา {d.checks.fail}</Pill></div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>ส่วน</th><th>จำนวน</th><th>ยืนยัน</th></tr></thead>
              <tbody>
                {Object.entries(d.parts).map(([k, p]) => (
                  <tr key={k}><td className="small">{PART_LABELS[k]?.[0] ?? k}</td><td className="num">{p.count ?? "–"}</td><td className="small">{p.confirmed_at ? <Pill kind="ok">ยืนยันแล้ว</Pill> : <Pill kind="grey">ร่าง</Pill>}{p.edited ? " แก้ไขแล้ว" : ""}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <section className="card pad stack">
        <h2 className="h2">ประวัติการดำเนินการ</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>วันเวลา</th><th>ผู้ดำเนินการ</th><th>การดำเนินการ</th><th>สถานะ</th><th>หมายเหตุ</th></tr></thead>
            <tbody>
              {d.job_id && <tr><td className="small num">{fmtTime(d.finalized_at)}</td><td className="small">นำเข้าด้วย AI</td><td>บันทึกเข้าระบบ (ร่างนำเข้าหลักสูตร)</td><td className="small">import</td><td className="small">งาน {d.job_id}</td></tr>}
              {d.events.map((e, i) => (
                <tr key={i}><td className="small num">{fmtTime(e.ts)}</td><td className="small">{e.by}</td><td>{ACTION_TH[e.action] ?? e.action}</td><td className="small">{e.from_status} → {e.to_status}</td><td className="small">{e.note ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
