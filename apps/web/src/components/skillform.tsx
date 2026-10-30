"use client";

// The form of one skill (skill-db, and เพิ่มเอง of skill-cur): code, side, names, definition,
// scope, tools, sources and the rubric of the five levels.
import type { SkillBody } from "@/lib/api";
import { CATS, CAT_EN, type Cat } from "@/lib/skills";
import { Check, Field, Modal } from "@/components/kit";

const TOOLS: [string, string][] = [["rubric", "Scoring rubrics"], ["self", "Self-Assessment (5 ระดับ)"]];
const SOURCES: [string, string][] = [["course", "รายวิชา"], ["coop", "สหกิจศึกษา/ฝึกงาน"], ["activity", "กิจกรรมเสริมหลักสูตร"]];

export function SkillForm({ edit, cats, central, readOnly, onChange, onClose, onSave, lockScope }: {
  edit: { body: SkillBody; create: boolean }; cats: readonly string[]; central: boolean; readOnly?: boolean; lockScope?: boolean;
  onChange: (b: SkillBody) => void; onClose: () => void; onSave: () => void;
}) {
  const b = edit.body;
  const set = (patch: Partial<SkillBody>) => onChange({ ...b, ...patch });
  const flip = (k: "tools" | "sources", v: string, on: boolean) => set({ [k]: on ? [...b[k], v] : b[k].filter((x) => x !== v) });
  return (
    <Modal open size="lg" title={edit.create ? "เพิ่ม Skill" : `Skill ${b.code}`} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ปิด</button>{!readOnly && <button type="button" className="btn primary" onClick={onSave}>{edit.create ? "เพิ่ม Skill" : "บันทึก"}</button>}</>}>
      <fieldset disabled={readOnly} className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="form-grid">
          <Field label="รหัส *">{(id) => <input id={id} className="inp" placeholder="เช่น SS4" disabled={!edit.create} value={b.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} />}</Field>
          <Field label="ด้าน *">{(id) => <select id={id} className="inp" value={b.cat} onChange={(e) => set({ cat: e.target.value as Cat })}>{CATS.filter((c) => cats.includes(c) || c === b.cat).map((c) => <option key={c} value={c}>{c} · {CAT_EN[c]}</option>)}</select>}</Field>
        </div>
        <Field label="ชื่อทักษะ (ไทย) *" full>{(id) => <input id={id} className="inp" value={b.name_th} onChange={(e) => set({ name_th: e.target.value })} />}</Field>
        <Field label="ชื่อทักษะ (อังกฤษ) · แสดงบนเอกสาร Transcript" full>{(id) => <input id={id} className="inp" value={b.name_en ?? ""} onChange={(e) => set({ name_en: e.target.value })} />}</Field>
        <Field label="นิยามเชิงปฏิบัติการ (แสดงด้านหลังเอกสาร)" full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={b.definition ?? ""} onChange={(e) => set({ definition: e.target.value })} />}</Field>
        {!lockScope && <div className="field"><span className="lbl">ขอบเขตการใช้</span>
          <label className="check"><input type="radio" disabled={!central} checked={b.scope === "central"} onChange={() => set({ scope: "central" })} /> ส่วนกลาง มศว (ทุกหลักสูตรต้องประเมิน)</label>
          <label className="check"><input type="radio" checked={b.scope === "program"} onChange={() => set({ scope: "program" })} /> หลักสูตรกำหนดเอง</label></div>}
        <div className="field"><span className="lbl">รูปแบบผลการประเมิน</span><span className="small">คะแนน 0–5 · ใช้เกณฑ์ระดับความเชี่ยวชาญ (รวม Ethics ซึ่งออกเอกสารเป็น S/U)</span></div>
        <div className="field"><span className="lbl">เครื่องมือประเมิน</span><div className="row">{TOOLS.map(([k, l]) => <Check key={k} checked={b.tools.includes(k)} onChange={(v) => flip("tools", k, v)}>{l}</Check>)}</div></div>
        <div className="field"><span className="lbl">แหล่งที่มาของการประเมิน</span><div className="row">{SOURCES.map(([k, l]) => <Check key={k} checked={b.sources.includes(k)} onChange={(v) => flip("sources", k, v)}>{l}</Check>)}</div></div>
        <div className="field"><span className="lbl">Rubric (คำอธิบายพฤติกรรมแต่ละระดับ)</span>
          {[0, 1, 2, 3, 4].map((i) => <input key={i} className="inp" aria-label={`Rubric ระดับ ${i + 1}`} placeholder={`ระดับ ${i + 1}`} value={b.rubric[i] ?? ""} onChange={(e) => set({ rubric: [0, 1, 2, 3, 4].map((k) => (k === i ? e.target.value : b.rubric[k] ?? "")) })} style={{ marginBottom: 4 }} />)}</div>
      </fieldset>
    </Modal>
  );
}
