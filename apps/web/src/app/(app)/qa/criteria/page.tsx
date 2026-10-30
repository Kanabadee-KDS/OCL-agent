"use client";

// qa-criteria (mock · US-M4-02): the items of each set of the announcement (พ.ศ. 2548 / 2558
// / 2565), by level, with the data the system shows for each and what it computes. Editing
// does not change a round already opened (its criteria were copied into it).
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { qaApi, type QaCriteria, type QaCriterion } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { Note, PageHead, Pill } from "@/components/ui";
import { Field, Modal, Seg, Tabs, useToast } from "@/components/kit";

type Body = Omit<QaCriterion, "id" | "updated_at">;

export default function QaCriteriaPage() {
  const { data: session } = useSession();
  const canEdit = canMenu(session?.user?.perms, "q2", "edit");
  const toast = useToast();
  const [d, setD] = useState<QaCriteria | null>(null);
  const [set, setSet] = useState("2565");
  const [lv, setLv] = useState<"" | "all" | "grad">("");
  const [edit, setEdit] = useState<{ id: number | null; body: Body } | null>(null);
  useEffect(() => { qaApi.criteria().then(setD).catch((e) => toast((e as Error).message, "err")); }, [toast]);
  const rows = (d?.items ?? []).filter((i) => String(i.set_year) === set && (!lv || i.level === lv));
  async function save() {
    if (!edit) return;
    try { setD(await qaApi.saveCriterion(edit.id, edit.body)); setEdit(null); toast("บันทึกเกณฑ์แล้ว"); } catch (e) { toast((e as Error).message, "err"); }
  }
  const b = edit?.body;
  const patch = (x: Partial<Body>) => edit && setEdit({ ...edit, body: { ...edit.body, ...x } });
  return (
    <>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตั้งค่าการประเมิน"]} title="เกณฑ์และข้อคำถาม"
        sub="องค์ประกอบที่ 1 ตัวบ่งชี้ 1.1 การบริหารจัดการหลักสูตรตามเกณฑ์มาตรฐาน · แก้ได้เมื่อประกาศเปลี่ยน รอบที่เปิดแล้วใช้เกณฑ์ที่คัดลอกไว้ตอนเปิด"
        actions={canEdit && <button type="button" className="btn primary" onClick={() => setEdit({ id: null, body: { set_year: Number(set), no: rows.length + 1, title: "", detail: "", sources: [], level: "all", rule: "none", active: true } })}>เพิ่มข้อ</button>} />
      {set !== "2565" && <Note kind="warn">ชุดนี้ใช้โครง 10 ข้อเดียวกับชุด 2565 ไว้ก่อน [สมมติ] แก้ข้อความเมื่อได้ประกาศฉบับทางการ</Note>}
      <div className="between">
        <Tabs items={(d?.sets ?? [2548, 2558, 2565]).map((y) => [String(y), `เกณฑ์ พ.ศ. ${y}`] as const)} value={set} onChange={setSet} />
        <Seg items={[["", "ทุกข้อ"], ["all", "ทุกระดับ"], ["grad", "บัณฑิตศึกษา"]] as const} value={lv} onChange={setLv} />
      </div>
      <section className="card">
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ข้อ</th><th>เกณฑ์</th><th>ระดับ</th><th>แหล่งข้อมูลที่ระบบแสดง</th><th>ระบบคำนวณ</th><th /></tr></thead>
          <tbody>
            {rows.map((i) => (
              <tr key={i.id} style={{ opacity: i.active ? 1 : 0.55 }}>
                <td className="num"><b>{i.no}</b></td>
                <td><b>{i.title}</b><div className="small faint">{i.detail}</div></td>
                <td><Pill kind={i.level === "grad" ? "info" : "grey"}>{d?.levels[i.level]}</Pill></td>
                <td><div className="row" style={{ gap: 4 }}>{i.sources.map((s) => <Pill key={s}>{s}</Pill>)}</div></td>
                <td className="small">{i.rule === "none" ? <span className="faint">ผู้ประเมินพิจารณา</span> : d?.rules[i.rule]}</td>
                <td>{canEdit && <button type="button" className="btn xs" onClick={() => setEdit({ id: i.id, body: { set_year: i.set_year, no: i.no, title: i.title, detail: i.detail, sources: i.sources, level: i.level, rule: i.rule, active: i.active } })}>แก้ไข</button>}</td>
              </tr>
            ))}
            {d && !rows.length && <tr><td colSpan={6} className="empty">ไม่มีเกณฑ์</td></tr>}
          </tbody></table></div>
      </section>
      {edit && b && (
        <Modal open size="lg" title={edit.id ? `แก้ไขข้อ ${b.no} (พ.ศ. ${b.set_year})` : "เพิ่มข้อ"} onClose={() => setEdit(null)}
          foot={<><button type="button" className="btn" onClick={() => setEdit(null)}>ยกเลิก</button><button type="button" className="btn primary" onClick={save}>บันทึก</button></>}>
          <div className="stack">
            <div className="form-grid">
              <Field label="ชุดเกณฑ์">{(id) => <select id={id} className="inp" value={b.set_year} onChange={(e) => patch({ set_year: Number(e.target.value) })}>{(d?.sets ?? []).map((y) => <option key={y} value={y}>พ.ศ. {y}</option>)}</select>}</Field>
              <Field label="ข้อที่">{(id) => <input id={id} className="inp num" value={b.no} onChange={(e) => patch({ no: Number(e.target.value.replace(/\D/g, "")) || 0 })} />}</Field>
            </div>
            <Field label="ชื่อเกณฑ์ *" full>{(id) => <input id={id} className="inp" value={b.title} onChange={(e) => patch({ title: e.target.value })} />}</Field>
            <Field label="รายละเอียด" full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={b.detail ?? ""} onChange={(e) => patch({ detail: e.target.value })} />}</Field>
            <Field label="แหล่งข้อมูล (คั่นด้วย ,)" full>{(id) => <input id={id} className="inp" value={b.sources.join(", ")} onChange={(e) => patch({ sources: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />}</Field>
            <div className="form-grid">
              <Field label="ระดับ">{(id) => <select id={id} className="inp" value={b.level} onChange={(e) => patch({ level: e.target.value as Body["level"] })}>{Object.entries(d?.levels ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</Field>
              <Field label="ระบบคำนวณ">{(id) => <select id={id} className="inp" value={b.rule} onChange={(e) => patch({ rule: e.target.value })}>{Object.entries(d?.rules ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</Field>
            </div>
            <label className="check"><input type="checkbox" checked={b.active} onChange={(e) => patch({ active: e.target.checked })} /> ใช้งาน</label>
          </div>
        </Modal>
      )}
    </>
  );
}
