"use client";

// st-courses (mock · US-M1-20): one group of the structure (หมวด 4): its path, level, credits,
// the module text, and its courses (รหัส-Version); add from the central course database (FS-3a)
// or create one there as a ร่างรายวิชา, take one out. Saves หมวด 4 at once.
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { courseCatalog, coursesApi, curricula, curriculumForm, type CatalogCourse, type CurriculumDetail } from "@/lib/api";
import { coursesOf, findNode, type Course, type Node } from "@/lib/curriculum";
import { getPath, setPath } from "@/lib/form";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Field, Modal, SearchBox, useToast } from "@/components/kit";

export default function GroupPage() {
  const { id, number } = useParams<{ id: string; number: string }>();
  const node = decodeURIComponent(number);
  const toast = useToast();
  const [d, setD] = useState<CurriculumDetail | null>(null);
  const [s4, setS4] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [pick, setPick] = useState(false);
  const [create, setCreate] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => Promise.all([curricula.get(id), curriculumForm.sections(id)]).then(([dd, ss]) => { setD(dd); setS4(ss["4"]?.data ?? {}); });
  useEffect(() => { Promise.all([curricula.get(id), curriculumForm.sections(id)]).then(([dd, ss]) => { setD(dd); setS4(ss["4"]?.data ?? {}); }).catch((e) => setErr((e as Error).message)); }, [id]);

  const tree = useMemo(() => ((s4 && getPath(s4, "structure.tree")) as Node[] | undefined) ?? [], [s4]);
  const courses = useMemo(() => ((s4 && getPath(s4, "courses.courses")) as Course[] | undefined) ?? [], [s4]);
  const found = findNode(tree, node);
  const mine = found ? coursesOf(courses, found.node) : [];
  const shown = mine.filter((c) => !q || `${c.code_th}${c.code_en ?? ""}${c.name_th}`.replace(/\s/g, "").toLowerCase().includes(q.replace(/\s/g, "").toLowerCase()));
  const editable = !!d?.editable.includes("4") && !d?.limited["4"];

  async function saveCourses(next: Course[], msg: string) {
    if (!s4) return;
    setBusy(true);
    try {
      await curriculumForm.save(id, "4", setPath(setPath(s4, "courses.courses", next), "courses.count", next.length));
      await load();
      toast(msg);
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  if (err) return <><BackLink href={`/curricula/${id}/edit`}>กลับไปหมวด 4</BackLink><Note kind="warn">{err}</Note></>;
  if (!d || !s4) return <div className="card pad">กำลังโหลด…</div>;
  if (!found) return <><BackLink href={`/curricula/${id}/edit`}>กลับไปหมวด 4</BackLink><Note kind="warn">ไม่พบกลุ่ม {node} ในโครงสร้าง</Note></>;
  const g = found.node;
  const add = (c: Course) => saveCourses([...courses, { ...c, node: g.number, group: g.name }], `เพิ่ม ${c.code_th} แล้ว`);
  return (
    <>
      <BackLink href={`/curricula/${id}/edit`}>กลับไปหมวด 4</BackLink>
      <PageHead
        crumb={["หมวดที่ 4", ...found.path.map((p) => p.name), g.name]}
        title={g.name}
        sub={<>Level {g.level ?? found.path.length + 1} · หน่วยกิต {g.credits ?? "–"} · {d.name_th}{g.module && <> · <Pill kind="info">ชุดวิชา</Pill></>}</>}
        actions={editable && (
          <>
            {busy && <span className="small faint" role="status">กำลังบันทึก…</span>}
            <button type="button" className="btn" disabled={busy} onClick={() => setPick(true)}>เลือกรายวิชาจากฐานข้อมูลกลาง</button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => setCreate(true)}>สร้างรายวิชาใหม่</button>
          </>
        )}
      />
      {g.module && g.description && <Note kind="info">{g.description}</Note>}
      {!editable && <Note kind="info">ดูอย่างเดียว · เพิ่ม/นำรายวิชาออกได้เมื่อคู่มือเป็นร่าง โดยผู้เตรียมร่าง</Note>}
      {(g.children ?? []).length > 0 && <Note kind="info">กลุ่มนี้มีกลุ่มย่อย {(g.children ?? []).map((c) => c.name).join(" · ")} · รายวิชาอยู่ที่กลุ่มย่อย</Note>}
      <section className="card pad stack">
        <SearchBox value={q} onChange={setQ} placeholder="ค้นรหัสหรือชื่อรายวิชาในกลุ่ม" />
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>รหัส</th><th>ชื่อรายวิชา</th><th>หน่วยกิต</th>{editable && <th />}</tr></thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.code_th}>
                  <td className="num">{c.code_th}{c.version ? `-${c.version}` : ""}{c.code_en && <div className="small faint">{c.code_en}{c.version ? `-${c.version}` : ""}</div>}</td>
                  <td>{c.name_th}<div className="small faint">{c.name_en}</div></td>
                  <td className="small">{c.credit_text ?? c.credits}</td>
                  {editable && <td><button type="button" className="btn xs" disabled={busy} onClick={() => saveCourses(courses.filter((x) => x !== c), `นำ ${c.code_th} ออกแล้ว`)}>นำออก</button></td>}
                </tr>
              ))}
              {!shown.length && <tr><td colSpan={4} className="small faint">{mine.length ? "ไม่พบรายวิชาตามคำค้น" : "ยังไม่มีรายวิชาในกลุ่มนี้"}</td></tr>}
            </tbody>
          </table>
        </div>
        <span className="small faint">รายวิชา {mine.length} วิชา · รหัส-เลข Version ตามฐานข้อมูลรายวิชากลาง · ไม่มีเลข = ยังไม่ผูกกับฐาน</span>
      </section>
      {pick && <PickCourse draftId={id} have={courses} onClose={() => setPick(false)} onPick={(c) => { setPick(false); add(c); }} />}
      {create && <CreateCourse draftId={id} have={courses} onClose={() => setCreate(false)} onCreate={(c) => { setCreate(false); add(c); }} onUseExisting={() => { setCreate(false); setPick(true); }} />}
    </>
  );
}

function PickCourse({ draftId, have, onClose, onPick }: { draftId: string; have: Course[]; onClose: () => void; onPick: (c: Course) => void }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<CatalogCourse[] | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { courseCatalog(q, draftId).then(setItems).catch(() => setItems([])); }, 250);
    return () => clearTimeout(t);
  }, [q, draftId]);
  const shown = (items ?? []).filter((c) => !have.some((h) => h.code_th === c.code_th));
  return (
    <Modal open size="lg" title="เลือกรายวิชาจากฐานข้อมูลกลาง" onClose={onClose}>
      <div className="stack">
        <SearchBox value={q} onChange={setQ} placeholder="ค้นรหัสหรือชื่อรายวิชา" />
        {shown.map((c) => (
          <button key={c.code_th} type="button" className="card" style={{ padding: "8px 12px", textAlign: "left", cursor: "pointer" }} onClick={() => onPick({ code_th: c.code_th, code_en: c.code_en, name_th: c.name_th ?? undefined, name_en: c.name_en, credits: c.credits, credit_text: c.credit_text, description_th: c.description_th, description_en: c.description_en, version: c.version })}>
            <b>{c.code_th}-{c.version}</b> {c.name_th} <span className="small faint">{c.credit_text ?? c.credits} · {c.course_type ?? "ไม่ระบุประเภท"} · {c.unit ?? "ไม่ระบุหน่วยงาน"}</span>
          </button>
        ))}
        {!items && <span className="small faint" role="status">กำลังค้น…</span>}
        {items && !shown.length && <span className="small faint">ไม่พบรายวิชาที่ยังไม่อยู่ในหลักสูตรนี้</span>}
        <span className="small faint">เฉพาะรายวิชาสถานะ ใช้งาน ใน Version ล่าสุด · แก้หรือเพิ่มรายวิชาที่เมนู บริหารรายวิชา</span>
      </div>
    </Modal>
  );
}

function CreateCourse({ draftId, have, onClose, onCreate, onUseExisting }: { draftId: string; have: Course[]; onClose: () => void; onCreate: (c: Course) => void; onUseExisting: () => void }) {
  const [c, setC] = useState({ code_th: "", name_th: "", code_en: "", name_en: "", credit_text: "" });
  const [clash, setClash] = useState<string | null>(null);
  async function submit() {
    const code = c.code_th.trim();
    if (have.some((h) => h.code_th === code)) { setClash(`${code} อยู่ในหลักสูตรนี้แล้ว`); return; }
    try {
      // a ร่างรายวิชา in the central database (FS-3a); a code already there is refused (409)
      const made = await coursesApi.newFor(draftId, { code_th: code, name_th: c.name_th.trim(), code_en: c.code_en || null, name_en: c.name_en || null, credit_text: c.credit_text || null });
      onCreate({ ...made, name_th: made.name_th ?? undefined });
    } catch (e) { setClash((e as Error).message); }
  }
  const set = (k: keyof typeof c) => (e: { target: { value: string } }) => { setClash(null); setC((o) => ({ ...o, [k]: e.target.value })); };
  return (
    <Modal open title="สร้างรายวิชาใหม่" onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" disabled={!c.code_th.trim() || !c.name_th.trim()} onClick={submit}>สร้างและเพิ่มในกลุ่ม</button></>}>
      <div className="form-grid">
        <Field label="รหัสรายวิชา *">{(fid) => <input id={fid} className="inp" value={c.code_th} onChange={set("code_th")} placeholder="เช่น ทวพ211" />}</Field>
        <Field label="ชื่อรายวิชา (ไทย) *">{(fid) => <input id={fid} className="inp" value={c.name_th} onChange={set("name_th")} />}</Field>
        <Field label="รหัส (อังกฤษ)">{(fid) => <input id={fid} className="inp" value={c.code_en} onChange={set("code_en")} />}</Field>
        <Field label="ชื่อรายวิชา (อังกฤษ)">{(fid) => <input id={fid} className="inp" value={c.name_en} onChange={set("name_en")} />}</Field>
        <Field label="หน่วยกิต">{(fid) => <input id={fid} className="inp" value={c.credit_text} onChange={set("credit_text")} placeholder="เช่น 3(2-2-5)" />}</Field>
      </div>
      {clash && <Note kind="warn">{clash}{clash.includes("เลือกจากรายการ") && <> · <button type="button" className="link-btn" onClick={onUseExisting}>เลือกจากรายการ</button></>}</Note>}
    </Modal>
  );
}
