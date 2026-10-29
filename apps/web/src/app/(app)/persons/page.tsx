"use client";

// ext-person (mock · US-M1-19): the register of people outside HURIS whom curricula list as
// teachers. A curriculum picks them in หมวด 0.2; an edit here reaches every curriculum that
// lists them. People in use cannot be deleted (set ไม่ใช้งาน). The ID number shows masked in
// the list and in full only in the form.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { personsApi, type Person, type PersonFields, type PersonList } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Field, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";

const EMPTY: PersonFields = {
  kind: "ผู้ทรงคุณวุฒิภายนอก", title_full: "", title_short: "", position: "", name_th: "", name_en: "", national_id: "", org: "",
  email: "", tel: "", education: [["ปริญญาตรี", "", "", "", "ไทย", ""]], works: [], active: true,
};

export default function PersonsPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const toast = useToast();
  const [d, setD] = useState<PersonList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [st, setSt] = useState<"" | "on" | "off">("");
  const [edit, setEdit] = useState<Person | "new" | null>(null);
  const load = () => personsApi.list().then(setD).catch((e) => setErr((e as Error).message));
  useEffect(() => { personsApi.list().then(setD).catch((e) => setErr((e as Error).message)); }, []);

  const rows = useMemo(() => (d?.items ?? []).filter((x) => (!kind || x.kind === kind) && (!st || (st === "on") === x.active)), [d, kind, st]);
  const columns: Column<Person>[] = [
    { key: "name", label: "ชื่อ-นามสกุล", sort: (x) => x.name_th, render: (x) => <div style={{ minWidth: 180, opacity: x.active ? 1 : 0.6 }}><b>{x.title_short}{x.name_th}</b><div className="small faint">{x.name_en} · {x.position}</div></div> },
    { key: "org", label: "หน่วยงาน/สังกัด", render: (x) => <span className="small">{x.org}</span> },
    { key: "kind", label: "ประเภท", render: (x) => <Pill>{x.kind}</Pill> },
    { key: "edu", label: "คุณวุฒิสูงสุด", render: (x) => { const e = [...x.education].sort((a, b) => (d?.options.levels.indexOf(b[0]) ?? 0) - (d?.options.levels.indexOf(a[0]) ?? 0))[0]; return <span className="small">{e ? `${e[1]} (${e[2]}), ${e[5]}` : "–"}</span>; } },
    { key: "works", label: "ผลงาน", render: (x) => <span className="num">{x.works.length}</span> },
    { key: "used", label: "ใช้ในหลักสูตร", render: (x) => (x.used_in.length ? <div className="row" style={{ gap: 4 }}>{x.used_in.map((u) => <Link key={u.draft_id} className="pill p-info" href={`/curricula/${u.draft_id}`}>{u.name_th}</Link>)}</div> : <span className="small faint">ยังไม่ถูกใช้</span>) },
    { key: "st", label: "สถานะ", render: (x) => <Pill kind={x.active ? "ok" : "grey"}>{x.active ? "ใช้งาน" : "ไม่ใช้งาน"}</Pill> },
    { key: "go", label: "", render: (x) => <button type="button" className="btn xs" onClick={() => personsApi.get(x.id).then(setEdit).catch((e) => toast((e as Error).message, "err"))}>{canMenu(perms, "c4", "edit") ? "แก้ไข" : "ดู"}</button> },
  ];

  return (
    <>
      <PageHead crumb={["บริหารข้อมูลหลักสูตร", "ข้อมูลหลัก (Master)"]} title="บริหารบุคคลภายนอก"
        sub="ทะเบียนกลางของบุคคลภายนอก (ไม่มีข้อมูลใน HURIS) ใช้เลือกเป็นอาจารย์ในคู่มือหลักสูตร บันทึกประวัติการศึกษาและผลงานที่นี่ที่เดียว แล้วทุกหลักสูตรดึงไปใช้"
        actions={canMenu(perms, "c4", "add") && <button type="button" className="btn primary" onClick={() => setEdit("new")}>เพิ่มบุคคลภายนอก</button>} />
      {err && <Note kind="warn">{err}</Note>}
      <KpiRow>
        <Kpi label="บุคคลภายนอกทั้งหมด" value={d?.counts.all ?? "–"} sub="ในทะเบียน" />
        <Kpi label="ใช้งาน" value={d?.counts.active ?? "–"} sub="เลือกได้ในคู่มือหลักสูตร" />
        <Kpi label="ถูกใช้ในหลักสูตร" value={d?.counts.used ?? "–"} sub="มีชื่ออยู่ในหลักสูตรอย่างน้อย 1 หลักสูตร" />
      </KpiRow>
      <DataTable rows={rows} columns={columns} rowKey={(x) => x.id} search={q} unit="คน" empty={d ? "ไม่พบข้อมูลตามเงื่อนไข" : "กำลังโหลด…"}
        searchText={(x) => `${x.name_th} ${x.name_en ?? ""} ${x.org ?? ""}`}
        toolbar={<Filters>
          <SearchBox value={q} onChange={setQ} placeholder="ค้นหาชื่อหรือหน่วยงาน" />
          <SelectFilter label="ประเภท" value={kind} options={d?.options.kinds ?? []} onChange={setKind} />
          <SelectFilter label="สถานะ" value={st} options={[["on", "ใช้งาน"], ["off", "ไม่ใช้งาน"]]} onChange={(v) => setSt(v as "" | "on" | "off")} />
        </Filters>} />
      <span className="small faint">แก้ไขข้อมูลที่นี่แล้วจะอัปเดตไปทุกหลักสูตรที่เลือกบุคคลนี้ · บุคคลที่ถูกใช้ในหลักสูตรลบไม่ได้ ให้ตั้งเป็น &ldquo;ไม่ใช้งาน&rdquo; แทน</span>
      {edit && d && (
        <PersonForm person={edit === "new" ? null : edit} options={d.options} canEdit={canMenu(perms, "c4", edit === "new" ? "add" : "edit")} canDelete={canMenu(perms, "c4", "delete")}
          onClose={() => setEdit(null)} onSaved={(m) => { setEdit(null); toast(m); load(); }} />
      )}
    </>
  );
}

function PersonForm({ person, options, canEdit, canDelete, onClose, onSaved }: {
  person: Person | null; options: PersonList["options"]; canEdit: boolean; canDelete: boolean; onClose: () => void; onSaved: (m: string) => void;
}) {
  const toast = useToast();
  const [v, setV] = useState<PersonFields>(() => (person ? { ...EMPTY, ...person, education: person.education.map((e) => [...e]), works: person.works.map((w) => ({ ...w })) } : EMPTY));
  const [busy, setBusy] = useState(false);
  const set = (k: keyof PersonFields) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const inp = (k: keyof PersonFields, label: string, req = false, ph = "") => (
    <Field label={<>{req && <b style={{ color: "var(--red)" }}>* </b>}{label}</>}>{(id) => <input id={id} className="inp" disabled={!canEdit} placeholder={ph} value={String(v[k] ?? "")} onChange={set(k)} />}</Field>
  );
  const setEdu = (i: number, j: number, val: string) => setV((x) => ({ ...x, education: x.education.map((e, k) => (k === i ? e.map((c, m) => (m === j ? val : c)) : e)) }));
  const setWork = (i: number, p: Partial<PersonFields["works"][number]>) => setV((x) => ({ ...x, works: x.works.map((w, k) => (k === i ? { ...w, ...p } : w)) }));

  async function save() {
    setBusy(true);
    try {
      const r = await personsApi.save(person?.id ?? null, v);
      onSaved(`บันทึกบุคคลภายนอกแล้ว${r.used_in.length ? ` · อัปเดตใน ${r.used_in.length} หลักสูตร` : ""}`);
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  async function remove() {
    if (!person || !window.confirm(`ลบ ${person.title_short ?? ""}${person.name_th}?`)) return;
    try { await personsApi.remove(person.id); onSaved("ลบแล้ว"); } catch (e) { toast((e as Error).message, "err"); }
  }

  return (
    <Modal open size="xl" title={`${person ? (canEdit ? "แก้ไข" : "ดู") : "เพิ่ม"}บุคคลภายนอก${person ? ` ${person.id}` : ""}`} onClose={onClose}
      foot={<>
        {person && canDelete && <button type="button" className="btn" style={{ marginRight: "auto" }} disabled={!!person.used_in.length} title={person.used_in.length ? "ถูกใช้ในหลักสูตร ลบไม่ได้" : undefined} onClick={remove}>ลบ</button>}
        <button type="button" className="btn" onClick={onClose}>ยกเลิก</button>
        {canEdit && <button type="button" className="btn primary" disabled={busy} onClick={save}>{busy ? "กำลังบันทึก…" : "บันทึก"}</button>}
      </>}>
      <div className="stack">
        <div className="form-grid">
          <Field label={<><b style={{ color: "var(--red)" }}>* </b>ประเภทบุคคลภายนอก</>}>{(id) => <select id={id} className="inp" disabled={!canEdit} value={v.kind} onChange={set("kind")}>{options.kinds.map((k) => <option key={k}>{k}</option>)}</select>}</Field>
          {inp("org", "หน่วยงาน/สังกัด", true)}
          {inp("title_full", "คำนำหน้าชื่อ (แบบยาว)", true, "เช่น รองศาสตราจารย์ ดร.")}{inp("title_short", "คำนำหน้าชื่อ (แบบสั้น)", false, "เช่น รศ.ดร.")}
          {inp("name_th", "ชื่อ-นามสกุล (ไทย)", true)}{inp("name_en", "ชื่อ-นามสกุล (อังกฤษ)", true)}
          {inp("position", "ตำแหน่ง/ตำแหน่งทางวิชาการ")}{inp("national_id", "เลขประจำตัวประชาชน", true, "x-xxxx-xxxxx-xx-x")}
          {inp("email", "อีเมล")}{inp("tel", "โทรศัพท์")}
        </div>
        <div className="between"><b>ประวัติการศึกษา</b>{canEdit && <button type="button" className="btn xs" onClick={() => setV((x) => ({ ...x, education: [...x.education, ["ปริญญาโท", "", "", "", "ไทย", ""]] }))}>เพิ่มวุฒิ</button>}</div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ระดับ</th><th>วุฒิ</th><th>สาขาวิชา</th><th>สถาบัน</th><th>ประเทศ</th><th>ปีที่จบ</th>{canEdit && <th />}</tr></thead>
            <tbody>
              {v.education.map((e, i) => (
                <tr key={i}>
                  <td><select className="inp" aria-label={`วุฒิ ${i + 1}: ระดับ`} disabled={!canEdit} value={e[0]} onChange={(x) => setEdu(i, 0, x.target.value)}>{options.levels.map((l) => <option key={l}>{l}</option>)}</select></td>
                  {[1, 2, 3, 4, 5].map((j) => <td key={j}><input className="inp" aria-label={`วุฒิ ${i + 1}: ช่อง ${j}`} disabled={!canEdit} value={e[j] ?? ""} onChange={(x) => setEdu(i, j, x.target.value)} /></td>)}
                  {canEdit && <td><button type="button" className="btn xs" onClick={() => setV((x) => ({ ...x, education: x.education.filter((_, k) => k !== i) }))}>ลบ</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="between"><b>ผลงาน</b>{canEdit && <button type="button" className="btn xs" onClick={() => setV((x) => ({ ...x, works: [...x.works, { title: "", type: "ผลงานวิชาการ", year: "" }] }))}>เพิ่มผลงาน</button>}</div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ชื่อผลงาน</th><th>ประเภท</th><th>ปี</th>{canEdit && <th />}</tr></thead>
            <tbody>
              {v.works.map((w, i) => (
                <tr key={i}>
                  <td><input className="inp" aria-label={`ผลงาน ${i + 1}: ชื่อ`} disabled={!canEdit} value={w.title} onChange={(x) => setWork(i, { title: x.target.value })} /></td>
                  <td><select className="inp" aria-label={`ผลงาน ${i + 1}: ประเภท`} disabled={!canEdit} value={w.type} onChange={(x) => setWork(i, { type: x.target.value })}>{options.work_types.map((t) => <option key={t}>{t}</option>)}</select></td>
                  <td><input className="inp" style={{ width: 90 }} aria-label={`ผลงาน ${i + 1}: ปี`} disabled={!canEdit} value={w.year ?? ""} onChange={(x) => setWork(i, { year: x.target.value })} /></td>
                  {canEdit && <td><button type="button" className="btn xs" onClick={() => setV((x) => ({ ...x, works: x.works.filter((_, k) => k !== i) }))}>ลบ</button></td>}
                </tr>
              ))}
              {!v.works.length && <tr><td colSpan={4} className="small faint">ยังไม่มีผลงาน</td></tr>}
            </tbody>
          </table>
        </div>
        <label className="row" style={{ gap: 8 }}><input type="checkbox" disabled={!canEdit} checked={v.active} onChange={(e) => setV((x) => ({ ...x, active: e.target.checked }))} /> ใช้งาน (ไม่ติ๊ก = ไม่แสดงให้เลือกในคู่มือหลักสูตร)</label>
        {person && person.used_in.length > 0 && <Note kind="info">ใช้ใน {person.used_in.map((u) => u.name_th).join(" · ")} · บันทึกแล้วชื่อ ตำแหน่ง และคุณวุฒิสูงสุดในหลักสูตรเหล่านี้เปลี่ยนตาม</Note>}
      </div>
    </Modal>
  );
}
