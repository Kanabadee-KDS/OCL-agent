"use client";

// skill-cur of one curriculum (US-M3-03): the core is always in and cannot be taken out
// (BR-M3-03), the rest is chosen from the database or added as the curriculum's own skill;
// the set goes to the faculty (flow skill_set, FS-5 Q3 ก). An approved set changes only by
// "ขอแก้ไข (สร้างฉบับใหม่)" for a later cohort.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { skillsApi, type SkillBody, type SkillSetData } from "@/lib/api";
import { CATS, CAT_COLOR, CAT_EN, SET_KIND, type Cat } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Check, Field, Modal, useToast } from "@/components/kit";
import { ApprovalSteps, CertifyModal, Events, SkillTag } from "@/components/skills";
import { SkillForm } from "@/components/skillform";

export default function SkillSetPage() {
  const { id } = useParams<{ id: string }>();
  const cid = Number(id);
  const toast = useToast();
  const [d, setD] = useState<SkillSetData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pick, setPick] = useState<string[]>([]);
  const [cohort, setCohort] = useState("");
  const [own, setOwn] = useState<SkillBody | null>(null);
  const [cert, setCert] = useState(false);
  const [revise, setRevise] = useState<string | null>(null);
  const fill = (x: SkillSetData) => { setD(x); setPick(x.set.skills); setCohort(x.set.cohort_from ? String(x.set.cohort_from) : ""); };
  useEffect(() => { skillsApi.set(cid).then(fill).catch((e) => setErr((e as Error).message)); }, [cid]);
  const dirty = useMemo(() => !!d && (JSON.stringify(d.set.skills) !== JSON.stringify(pick) || String(d.set.cohort_from ?? "") !== cohort), [d, pick, cohort]);
  async function run(fn: () => Promise<SkillSetData>, msg: string) {
    try { fill(await fn()); toast(msg); return true; } catch (e) { toast((e as Error).message, "err"); return false; }
  }
  if (err) return <><BackLink href="/skills/curricula">กลับไปรายการ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const ro = !d.can_edit;
  const core = new Set(d.core);
  const cohortNum = cohort.trim() ? Number(cohort) : null;
  return (
    <>
      <BackLink href="/skills/curricula">กลับไปภาพรวมทุกหลักสูตร</BackLink>
      <PageHead crumb={["Skill Transcript", "กำหนด Skill ตามหลักสูตร"]} title={d.curriculum.name_th}
        sub={<>ชุด Skill ฉบับ {d.set.version} · <Pill kind={SET_KIND[d.set.status]}>{d.set.status_th}</Pill> · {d.curriculum.faculty}{d.set.cohort_from ? ` · ใช้กับนิสิตรหัส ${d.set.cohort_from} ขึ้นไป` : ""}</>}
        actions={<>
          {d.can_edit && <button type="button" className="btn" disabled={!dirty} onClick={() => run(() => skillsApi.saveSet(cid, pick, cohortNum), "บันทึกร่างแล้ว")}>{dirty ? "บันทึกร่าง" : "บันทึกแล้ว"}</button>}
          {d.can_edit && <button type="button" className="btn" onClick={() => setOwn({ code: "", cat: "SS", name_th: "", name_en: "", definition: "", scope: "program", tools: ["rubric", "self"], sources: ["course"], rubric: ["", "", "", "", ""] })}>เพิ่ม Skill ของหลักสูตร</button>}
          {d.can_submit && <button type="button" className="btn primary" onClick={() => run(async () => { if (dirty) await skillsApi.saveSet(cid, pick, cohortNum); return skillsApi.submitSet(cid); }, "ส่งให้คณะอนุมัติแล้ว")}>ส่งอนุมัติ</button>}
          {d.can_certify && <button type="button" className="btn primary" onClick={() => setCert(true)}>อนุมัติ / ส่งคืน</button>}
          {d.can_revise && <button type="button" className="btn" onClick={() => setRevise("")}>ขอแก้ไข (สร้างฉบับใหม่)</button>}
          {d.set.status === "approved" && <Link className="btn" href="/skills/mapping">ไปที่ Skill Mapping</Link>}
        </>} />
      {d.set.status === "returned" && <Note kind="warn">ส่งคืนแก้ไข: {[...d.events].reverse().find((e) => e.action === "return")?.note}</Note>}
      {!d.rights.add && d.set.status !== "approved" && <Note kind="info">บัญชีนี้ไม่มีสิทธิ์ &quot;เพิ่ม Skill ของหลักสูตร&quot; ของหลักสูตรนี้ (กำหนดที่หน้า กำหนดผู้บันทึกแผนการประเมิน Skill)</Note>}
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) 280px", gap: 16, alignItems: "start" }}>
        <section className="card pad stack" style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 8 }}>
            <span>ใช้กับนิสิตรหัส</span>
            <input className="inp num" style={{ width: 80 }} aria-label="รหัสนิสิตรุ่นแรกที่ใช้" placeholder="67" disabled={ro} value={cohort} onChange={(e) => setCohort(e.target.value.replace(/\D/g, "").slice(0, 2))} />
            <span>ขึ้นไป</span>
            <span className="small faint">· เลือก {pick.length} Skill (แกนกลาง {d.core.length})</span>
          </div>
          {CATS.map((c) => {
            const pool = d.pool.filter((s) => s.cat === c);
            if (!pool.length) return null;
            return (
              <div key={c} className="stack" style={{ gap: 6 }}>
                <b style={{ color: CAT_COLOR[c as Cat] }}>{c} · {CAT_EN[c as Cat]}</b>
                <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 6 }}>
                  {pool.map((s) => (
                    <Check key={s.code} disabled={ro || core.has(s.code)} checked={pick.includes(s.code)} onChange={(v) => setPick((x) => (v ? [...x, s.code] : x.filter((y) => y !== s.code)))}>
                      <SkillTag code={s.code} cat={s.cat} /> {s.name_th}{core.has(s.code) && <span className="small faint"> · แกนกลาง</span>}{s.curriculum_id === cid && <span className="small faint"> · เพิ่มเอง</span>}
                    </Check>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
        <aside className="stack">
          <section className="card pad stack"><h2 className="h2">ขั้นตอนอนุมัติ</h2><ApprovalSteps steps={d.steps} status={d.set.status} /></section>
          <section className="card pad stack">
            <h2 className="h2">ฉบับ</h2>
            {d.versions.map((v) => <div key={v.version} className="between small"><span>ฉบับ {v.version}{v.cohort_from ? ` · รหัส ${v.cohort_from}+` : ""} · {v.skills} Skill</span><Pill kind={SET_KIND[v.status]}>{v.status === "approved" ? "อนุมัติแล้ว" : v.status}</Pill></div>)}
            {!d.versions.length && <span className="small faint">ยังไม่บันทึก</span>}
          </section>
        </aside>
      </div>
      <Events events={d.events} />
      {own && <SkillForm edit={{ body: own, create: true }} cats={["SS", "E", "C"]} central={false} lockScope onChange={setOwn} onClose={() => setOwn(null)}
        onSave={() => run(() => skillsApi.addOwn(cid, own), `เพิ่ม ${own.code} ในฐานข้อมูล (ขอบเขตหลักสูตร) และในชุดแล้ว`).then((ok) => ok && setOwn(null))} />}
      {cert && <CertifyModal what="ชุด Skill ของหลักสูตร" onClose={() => setCert(false)} onDone={(ok, note) => { setCert(false); run(() => skillsApi.certifySet(cid, ok, note), ok ? "อนุมัติแล้ว" : "ส่งคืนแก้ไขแล้ว"); }} />}
      {revise !== null && (
        <Modal open title="ขอแก้ไข (สร้างฉบับใหม่)" onClose={() => setRevise(null)} foot={<><button type="button" className="btn" onClick={() => setRevise(null)}>ยกเลิก</button><button type="button" className="btn primary" onClick={() => { const v = revise; setRevise(null); run(() => skillsApi.reviseSet(cid, v ? Number(v) : null), "สร้างฉบับใหม่ (ร่าง) แล้ว"); }}>สร้างฉบับใหม่</button></>}>
          <div className="stack">
            <Field label="ฉบับใหม่ใช้กับนิสิตรหัส (ขึ้นไป)" full>{(fid) => <input id={fid} className="inp num" placeholder="เช่น 68" value={revise} onChange={(e) => setRevise(e.target.value.replace(/\D/g, "").slice(0, 2))} />}</Field>
            <span className="small faint">ฉบับที่อนุมัติแล้วยังใช้กับนิสิตรุ่นก่อนหน้า ฉบับใหม่คัดลอก Skill ปัจจุบันเป็นร่างให้แก้แล้วส่งอนุมัติอีกครั้ง</span>
          </div>
        </Modal>
      )}
    </>
  );
}
