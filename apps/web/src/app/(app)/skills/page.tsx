"use client";

// skill-db (mock · US-M3-01): the skills of four sides (GS / SS / E / C) with their
// definitions, tools, sources and rubric; the five-level table (BR-M3-02) and the Ethics pass
// mark (S/U, FS-5 Q4 ก); the frameworks per level and cohort. Who may add which side comes
// from the tab "สิทธิ์เพิ่ม Skill ในฐานข้อมูล" of skill-assign. Sample list until A7.
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { skillsApi, type SkillBody, type SkillLevel, type SkillRow, type SkillsResp } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { CATS, CAT_COLOR, CAT_EN, CAT_TH, type Cat } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, Modal, SearchBox, SelectFilter, Tabs, useToast, type Column } from "@/components/kit";
import { SkillTag } from "@/components/skills";
import { SkillForm } from "@/components/skillform";

const blank = (cat: Cat): SkillBody => ({ code: "", cat, name_th: "", name_en: "", definition: "", scope: "program", tools: ["rubric", "self"], sources: ["course"], rubric: ["", "", "", "", ""] });

export default function SkillDbPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const toast = useToast();
  const [d, setD] = useState<SkillsResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"list" | "level" | "scope">("list");
  const [cat, setCat] = useState<Cat>("GS");
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("");
  const [edit, setEdit] = useState<{ body: SkillBody; create: boolean } | null>(null);
  const [imp, setImp] = useState(false);
  const load = () => skillsApi.list().then(setD).catch((e) => setErr((e as Error).message));
  useEffect(() => { skillsApi.list().then(setD).catch((e) => setErr((e as Error).message)); }, []);
  const rows = useMemo(() => (d?.items ?? []).filter((s) => s.cat === cat && (!scope || s.scope === scope)), [d, cat, scope]);
  const mayAdd = canMenu(perms, "s1", "add") && (d?.rights.cats.length ?? 0) > 0;
  const mayEdit = (s: SkillRow) => canMenu(perms, "s1", "edit") && !!d?.rights.cats.includes(s.cat) && (s.scope !== "central" || d.rights.central);

  async function save() {
    if (!edit) return;
    try {
      await (edit.create ? skillsApi.add(edit.body) : skillsApi.save(edit.body));
      toast(edit.create ? `เพิ่ม ${edit.body.code} แล้ว` : "บันทึก Skill แล้ว");
      setEdit(null); setCat(edit.body.cat as Cat); load();
    } catch (e) { toast((e as Error).message, "err"); }
  }
  async function toggle(s: SkillRow) {
    try { await skillsApi.active(s.code, !s.active); toast(s.active ? "ปิดการใช้งานแล้ว" : "เปิดใช้งานแล้ว"); load(); } catch (e) { toast((e as Error).message, "err"); }
  }
  const columns: Column<SkillRow>[] = [
    { key: "code", label: "รหัส", sort: (s) => s.code, render: (s) => <SkillTag code={s.code} cat={s.cat} /> },
    { key: "name", label: "ชื่อทักษะ", sort: (s) => s.name_th, render: (s) => <div style={{ opacity: s.active ? 1 : 0.55 }}><b>{s.name_th}</b><div className="small faint">{s.name_en}</div></div> },
    { key: "scope", label: "ขอบเขต", render: (s) => s.scope === "central" ? <Pill kind="red">ส่วนกลาง มศว</Pill> : <Pill kind="info">{s.curriculum ? `หลักสูตร · ${s.curriculum}` : "หลักสูตรกำหนด"}</Pill> },
    { key: "used", label: "ใช้ในชุด Skill", render: (s) => <span className="num">{s.used_in}</span> },
    { key: "st", label: "สถานะ", render: (s) => <Pill kind={s.active ? "ok" : "grey"}>{s.active ? "ใช้งาน" : "ปิดใช้งาน"}</Pill> },
    { key: "go", label: "", render: (s) => <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
      <button type="button" className="btn xs" onClick={() => setEdit({ body: { ...s, name_en: s.name_en ?? "", definition: s.definition ?? "" }, create: false })}>{mayEdit(s) ? "แก้ไข" : "ดู"}</button>
      {mayEdit(s) && <button type="button" className="btn xs" onClick={() => toggle(s)}>{s.active ? "ปิดใช้" : "เปิดใช้"}</button>}
    </div> },
  ];
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ตั้งค่าฐานข้อมูลพื้นฐาน"]} title="บริหารฐานข้อมูล Skill"
        sub="กำหนดรายการทักษะ 4 ด้าน (GS / SS / E / C) นิยามเชิงปฏิบัติการ เครื่องมือประเมิน รูปแบบผล และเกณฑ์ระดับความเชี่ยวชาญ"
        actions={mayAdd && <><button type="button" className="btn" onClick={() => setImp(true)}>นำเข้าจาก Excel</button><button type="button" className="btn primary" onClick={() => setEdit({ body: blank(d?.rights.cats.includes(cat) ? cat : (d!.rights.cats[0] as Cat)), create: true })}>เพิ่ม Skill</button></>} />
      {err && <Note kind="warn">{err}</Note>}
      <Note kind="info">รายการเริ่มต้นเป็นข้อมูลตัวอย่างจาก mock จนกว่าจะได้ฐานข้อมูล Skill ของมหาวิทยาลัย (A7)</Note>
      <Tabs items={[["list", "รายการ Skill"], ["level", "เกณฑ์ระดับความเชี่ยวชาญ"], ["scope", "ระดับการศึกษาและปีที่เข้าศึกษา"]] as const} value={tab} onChange={setTab} />
      {tab === "list" && d && (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 12 }}>
            {CATS.map((k) => (
              <button key={k} type="button" className="card pad" onClick={() => setCat(k)} aria-pressed={k === cat}
                style={{ textAlign: "left", cursor: "pointer", borderColor: k === cat ? CAT_COLOR[k] : undefined, boxShadow: k === cat ? `0 0 0 1px ${CAT_COLOR[k]}` : undefined }}>
                <div className="between"><b style={{ color: CAT_COLOR[k] }}>{k} · {CAT_EN[k]}</b><b className="num" style={{ fontSize: 22 }}>{d.items.filter((s) => s.cat === k).length}</b></div>
                <span className="small faint">{CAT_TH[k]}{k === "SS" ? " · หลักสูตรกำหนด" : ""}</span>
              </button>
            ))}
          </div>
          <DataTable rows={rows} columns={columns} rowKey={(s) => s.code} search={q} unit="Skill" searchText={(s) => `${s.code} ${s.name_th} ${s.name_en ?? ""}`}
            toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นหารหัสหรือชื่อทักษะ" /><SelectFilter label="ขอบเขต" value={scope} options={[["central", "ส่วนกลาง มศว"], ["program", "หลักสูตรกำหนด"]]} onChange={setScope} /></Filters>} />
        </>
      )}
      {tab === "level" && d && <LevelsTab d={d} canEdit={canMenu(perms, "s1", "edit") && d.rights.central} onSaved={load} />}
      {tab === "scope" && d && (
        <section className="card pad stack">
          <h2 className="h2">กำหนดการใช้งานตามระดับการศึกษาและปีที่เข้าศึกษา</h2>
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ระดับการศึกษา</th><th>ใช้กับนิสิตรหัส</th><th>กรอบทักษะ</th><th>สถานะ</th></tr></thead>
            <tbody>{d.settings.frameworks.map((f, i) => <tr key={i}><td>{f.level}</td><td className="num">{f.cohorts}</td><td>{f.frame}</td><td><Pill kind={f.status === "ใช้งาน" ? "ok" : "grey"}>{f.status}</Pill></td></tr>)}</tbody></table></div>
          <span className="small faint">รุ่นนิสิตที่ใช้ชุด Skill ของแต่ละหลักสูตรกำหนดในหน้า &quot;กำหนด Skill ตามหลักสูตร&quot; (แต่ละฉบับระบุรหัสนิสิตที่ใช้)</span>
        </section>
      )}
      {edit && <SkillForm edit={edit} cats={d?.rights.cats ?? []} central={!!d?.rights.central} readOnly={!edit.create && !mayEdit(edit.body as SkillRow)} onChange={(body) => setEdit({ ...edit, body })} onClose={() => setEdit(null)} onSave={save} />}
      {imp && <ImportModal onClose={() => setImp(false)} onDone={() => { setImp(false); load(); }} />}
    </>
  );
}

function LevelsTab({ d, canEdit, onSaved }: { d: SkillsResp; canEdit: boolean; onSaved: () => void }) {
  const toast = useToast();
  const [lv, setLv] = useState<SkillLevel[]>(d.settings.levels);
  const [pass, setPass] = useState(String(d.settings.ethics_pass));
  const setRow = (i: number, k: keyof SkillLevel, v: string) => setLv((x) => x.map((r, j) => (j === i ? { ...r, [k]: k === "min" || k === "max" ? Number(v) : v } : r)));
  async function save() {
    try { await skillsApi.saveSetting("levels", lv); await skillsApi.saveSetting("ethics_pass", Number(pass)); toast("บันทึกเกณฑ์แล้ว"); onSaved(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <section className="card pad stack">
      <div className="between"><h2 className="h2">ระดับความเชี่ยวชาญ คะแนนเฉลี่ย และการแปลความหมาย</h2>{canEdit && <button type="button" className="btn primary sm" onClick={save}>บันทึก</button>}</div>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ระดับ</th><th>คะแนนเฉลี่ยต่ำสุด</th><th>คะแนนเฉลี่ยสูงสุด</th><th>การแปลความหมาย (EN)</th><th>การแปลความหมาย (TH)</th></tr></thead>
        <tbody>{lv.map((r, i) => <tr key={i}><td className="num">{i + 1}</td>
          {(["min", "max", "en", "th"] as const).map((k) => <td key={k}><input className={`inp${k === "min" || k === "max" ? " num" : ""}`} aria-label={`ระดับ ${i + 1} ${k}`} disabled={!canEdit} value={String(r[k])} onChange={(e) => setRow(i, k, e.target.value)} style={{ maxWidth: k === "min" || k === "max" ? 100 : undefined }} /></td>)}</tr>)}</tbody></table></div>
      <div className="row" style={{ gap: 8 }}><span>Ethics ผ่าน (S) เมื่อคะแนนตั้งแต่</span><input className="inp num" style={{ width: 90 }} aria-label="เกณฑ์ผ่าน Ethics" disabled={!canEdit} value={pass} onChange={(e) => setPass(e.target.value)} /><Pill kind="warn">สมมติ · รอเกณฑ์แปลงจากลูกค้า</Pill></div>
      <Note kind="info">คะแนน Skill ของนิสิต = ค่าเฉลี่ยจากทุกรายวิชาที่ประเมิน Skill นั้น เช่น (4.21 + 4.35 + 4.51 + 4.79) / 4 = 4.47 → Proficient</Note>
    </section>
  );
}

function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [out, setOut] = useState<{ added: number; updated: number; errors: { row: number; error: string }[] } | null>(null);
  async function run() {
    if (!file) return;
    try { const r = await skillsApi.importXlsx(file); setOut(r); toast(`นำเข้าแล้ว เพิ่ม ${r.added} แก้ ${r.updated}`); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <Modal open title="นำเข้า Skill จาก Excel" onClose={out ? onDone : onClose}
      foot={<><button type="button" className="btn" onClick={out ? onDone : onClose}>ปิด</button>{!out && <button type="button" className="btn primary" disabled={!file} onClick={run}>นำเข้า</button>}</>}>
      <div className="stack">
        <a className="btn sm" href={skillsApi.templateUrl()} style={{ alignSelf: "flex-start" }}>ดาวน์โหลดแม่แบบ (.xlsx)</a>
        <input type="file" accept=".xlsx" aria-label="ไฟล์ .xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <span className="small faint">รหัสที่มีแล้วจะถูกแก้ตามไฟล์ · ขอบเขต &quot;ส่วนกลาง&quot; ใช้ได้เฉพาะผู้มีสิทธิ์ระดับมหาวิทยาลัย</span>
        {out && <Note kind={out.errors.length ? "warn" : "ok"}>เพิ่ม {out.added} · แก้ {out.updated}{out.errors.length > 0 && <> · ข้าม {out.errors.length} แถว: {out.errors.map((e) => `แถว ${e.row} ${e.error}`).join(" · ")}</>}</Note>}
      </div>
    </Modal>
  );
}
