"use client";

// course-master (mock · US-M1-18, CUR23): the central course database. A course shows as
// รหัส-Version; changing what a book prints about it can be kept as a new Version, so the
// curricula that use the old one keep it (FS-3 Q2 ก). Used courses cannot be deleted.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { coursesApi, type CourseDetail, type CourseFields, type CourseList, type CourseRow } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Field, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";

const ST_KIND: Record<string, "ok" | "warn" | "grey"> = { "ใช้งาน": "ok", "ร่างรายวิชา": "warn", "ไม่ใช้งาน": "grey" };
const V_KIND: Record<string, "ok" | "warn" | "grey"> = { "ใหม่": "ok", "ปรับปรุง": "warn", "เดิม": "grey" };
const EMPTY: CourseFields = {
  code_th: "", code_en: "", name_th: "", name_en: "", transcript_th: "", transcript_en: "", credit_text: "", course_type: "", module: "",
  unit: "", major: "", reg_no: "", telebank: "", status: "ร่างรายวิชา", note: "", description_th: "", description_en: "",
};

export default function CoursesPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const toast = useToast();
  const [d, setD] = useState<CourseList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ type: "", unit: "", status: "" });
  const [edit, setEdit] = useState<CourseDetail | "new" | null>(null);
  const load = () => coursesApi.list().then(setD).catch((e) => setErr((e as Error).message));
  useEffect(() => { coursesApi.list().then(setD).catch((e) => setErr((e as Error).message)); }, []);

  const rows = useMemo(() => (d?.items ?? []).filter((c) => (!f.type || c.course_type === f.type) && (!f.unit || c.unit === f.unit) && (!f.status || c.status === f.status)), [d, f]);
  const columns: Column<CourseRow>[] = [
    { key: "code", label: "รหัสวิชา (ไทย / อังกฤษ)", sort: (c) => c.code_th, render: (c) => <><b className="num">{c.label}</b><div className="small faint num">{c.code_en ? `${c.code_en}-${c.latest}` : ""}</div></> },
    { key: "name", label: "ชื่อวิชา", sort: (c) => c.name_th, render: (c) => <div style={{ minWidth: 200 }}>{c.name_th}<div className="small faint">{c.name_en}</div></div> },
    { key: "cr", label: "หน่วยกิต", render: (c) => <span className="num small">{c.credit_text ?? c.credits ?? "–"}</span> },
    { key: "type", label: "ประเภท / ชุดวิชา", render: (c) => <span className="small">{c.course_type ?? <span className="faint">ไม่ระบุ</span>}<div className="faint">{c.module}</div></span> },
    { key: "unit", label: "หน่วยงานเจ้าของวิชา", render: (c) => <span className="small">{c.unit ?? "–"}</span> },
    { key: "ver", label: "Version", sort: (c) => c.latest, render: (c) => <><b className="num">v{c.latest}</b> <Pill kind={V_KIND[c.kind] ?? "grey"}>{c.kind}</Pill></> },
    { key: "used", label: "ใช้ในหลักสูตร", sort: (c) => c.used_in.length, render: (c) => <span className="num small">{c.used_in.length || "–"}</span> },
    { key: "st", label: "สถานะ", render: (c) => <Pill kind={ST_KIND[c.status] ?? "grey"}>{c.status}</Pill> },
    { key: "go", label: "", render: (c) => <button type="button" className="btn xs" onClick={() => coursesApi.get(c.code_th).then(setEdit).catch((e) => toast((e as Error).message, "err"))}>{canMenu(perms, "c5", "edit") ? "แก้ไข" : "ดู"}</button> },
  ];

  function exportCsv() {
    const head = ["รหัสวิชา", "รหัสวิชา (อังกฤษ)", "Version", "ชื่อวิชา (ไทย)", "ชื่อวิชา (อังกฤษ)", "หน่วยกิต", "ประเภท", "ชุดวิชา", "หน่วยงานเจ้าของวิชา", "สถานะ", "ใช้ในหลักสูตร"];
    const body = rows.map((c) => [c.code_th, c.code_en, c.latest, c.name_th, c.name_en, c.credit_text, c.course_type, c.module, c.unit, c.status, c.used_in.length]);
    const url = URL.createObjectURL(new Blob([toCsv(head, body)], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: "courses.csv" }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHead crumb={["บริหารข้อมูลหลักสูตร", "ข้อมูลหลัก (Master)"]} title="บริหารรายวิชา"
        sub="ฐานข้อมูลรายวิชากลาง (ฟิลด์ตามแบบฟอร์มเดิม CUR23) คู่มือหลักสูตรหมวดที่ 4 เลือกรายวิชาจากที่นี่ แต่ละรายวิชาเก็บประวัติ Version (ใหม่/เดิม/ปรับปรุง)"
        actions={<>
          <button type="button" className="btn" disabled={!rows.length} onClick={exportCsv}>ส่งออก CSV</button>
          {canMenu(perms, "c5", "add") && <button type="button" className="btn primary" onClick={() => setEdit("new")}>เพิ่มรายวิชา</button>}
        </>} />
      {err && <Note kind="warn">{err}</Note>}
      <KpiRow>
        <Kpi label="รายวิชาทั้งหมด" value={d?.counts.all ?? "–"} on={!f.status} onClick={() => setF((x) => ({ ...x, status: "" }))} />
        {(d?.options.statuses ?? []).map((s) => <Kpi key={s} label={s} value={d?.counts[s] ?? 0} on={f.status === s} onClick={() => setF((x) => ({ ...x, status: x.status === s ? "" : s }))} />)}
      </KpiRow>
      <DataTable rows={rows} columns={columns} rowKey={(c) => c.code_th} search={q} unit="รายวิชา" empty={d ? "ไม่พบรายวิชาตามเงื่อนไข" : "กำลังโหลด…"}
        searchText={(c) => `${c.code_th} ${c.code_en ?? ""} ${c.name_th ?? ""} ${c.name_en ?? ""}`}
        toolbar={<Filters>
          <SearchBox value={q} onChange={setQ} placeholder="ค้นหารหัสหรือชื่อรายวิชา (ไทย/อังกฤษ)" />
          <SelectFilter label="ประเภทรายวิชา" value={f.type} options={d?.options.types ?? []} onChange={(v) => setF((x) => ({ ...x, type: v }))} />
          <SelectFilter label="หน่วยงานเจ้าของวิชา" value={f.unit} options={d?.options.units ?? []} onChange={(v) => setF((x) => ({ ...x, unit: v }))} />
        </Filters>} />
      {edit && d && (
        <CourseForm course={edit === "new" ? null : edit} options={d.options} canEdit={canMenu(perms, "c5", edit === "new" ? "add" : "edit")} canDelete={canMenu(perms, "c5", "delete")}
          onClose={() => setEdit(null)}
          onSaved={(msg) => { setEdit(null); toast(msg); load(); }} />
      )}
    </>
  );
}

function CourseForm({ course, options, canEdit, canDelete, onClose, onSaved }: {
  course: CourseDetail | null; options: CourseList["options"]; canEdit: boolean; canDelete: boolean; onClose: () => void; onSaved: (msg: string) => void;
}) {
  const toast = useToast();
  const [v, setV] = useState<CourseFields>(() => (course ? Object.fromEntries(Object.keys(EMPTY).map((k) => [k, (course as unknown as Record<string, unknown>)[k] ?? ""])) as CourseFields : EMPTY));
  const [newVersion, setNewVersion] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof CourseFields) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const inp = (k: keyof CourseFields, label: string, req = false, extra: object = {}) => (
    <Field label={<>{req && <b style={{ color: "var(--red)" }}>* </b>}{label}</>}>{(id) => <input id={id} className="inp" disabled={!canEdit || (k === "code_th" && !!course)} value={v[k] ?? ""} onChange={set(k)} {...extra} />}</Field>
  );
  const sel = (k: keyof CourseFields, label: string, opts: string[], req = false) => (
    <Field label={<>{req && <b style={{ color: "var(--red)" }}>* </b>}{label}</>}>{(id) => (
      <select id={id} className="inp" disabled={!canEdit} value={v[k] ?? ""} onChange={set(k)}>
        <option value="">— เลือก —</option>{opts.map((o) => <option key={o}>{o}</option>)}
      </select>
    )}</Field>
  );

  async function save() {
    setBusy(true);
    try {
      if (course) await coursesApi.update(course.code_th, { ...v, new_version: newVersion });
      else await coursesApi.create(v);
      onSaved(`บันทึกรายวิชา ${v.code_th}${newVersion ? " เป็น Version ใหม่" : ""} แล้ว`);
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  async function remove() {
    if (!course || !window.confirm(`ลบรายวิชา ${course.code_th}?`)) return;
    try { await coursesApi.remove(course.code_th); onSaved(`ลบรายวิชา ${course.code_th} แล้ว`); } catch (e) { toast((e as Error).message, "err"); }
  }

  return (
    <Modal open size="xl" title={course ? `กำหนดข้อมูลรายวิชา › ${canEdit ? "แก้ไข" : "ดู"} ${course.label}` : "กำหนดข้อมูลรายวิชา › เพิ่มข้อมูล"} onClose={onClose}
      foot={<>
        {course && canDelete && <button type="button" className="btn" style={{ marginRight: "auto" }} disabled={!!course.used_in.length} title={course.used_in.length ? "ถูกใช้ในหลักสูตร ลบไม่ได้ ให้ตั้งสถานะ ไม่ใช้งาน แทน" : undefined} onClick={remove}>ลบ</button>}
        <button type="button" className="btn" onClick={onClose}>ยกเลิก</button>
        {canEdit && <button type="button" className="btn primary" disabled={busy} onClick={save}>{busy ? "กำลังบันทึก…" : "บันทึก"}</button>}
      </>}>
      <div className="stack">
        <div className="form-grid">
          {inp("code_th", "รหัสวิชา (ไทย)", true)}{inp("code_en", "รหัสวิชา (อังกฤษ)", true)}
          {inp("name_th", "ชื่อวิชา (ไทย)", true)}{inp("name_en", "ชื่อวิชา (อังกฤษ)", true)}
          {inp("transcript_th", `ชื่อวิชา Transcript (ไทย) ${(v.transcript_th ?? "").length}/40`, true, { maxLength: 40 })}
          {inp("transcript_en", `ชื่อวิชา Transcript (อังกฤษ) ${(v.transcript_en ?? "").length}/40`, true, { maxLength: 40 })}
          {sel("course_type", "ประเภทรายวิชา", options.types, true)}{inp("credit_text", "จำนวนหน่วยกิต x(บรรยาย-ปฏิบัติ-ศึกษาด้วยตนเอง)", true, { placeholder: "เช่น 3(2-2-5)" })}
          {inp("module", "ชุดวิชา")}{sel("unit", "หน่วยงานเจ้าของวิชา", options.units)}
          {inp("major", "สาขาวิชาที่ดูแล")}{inp("reg_no", "เลขทะเบียนวิชาทบวง")}{inp("telebank", "รหัสวิชาตัวเลข (Telebank)")}
          {sel("status", "สถานะการใช้งาน", options.statuses, true)}
        </div>
        <Field label="คำอธิบายรายวิชา (ไทย)" full>{(id) => <textarea id={id} className="inp" rows={4} style={{ height: "auto", padding: 8 }} disabled={!canEdit} value={v.description_th ?? ""} onChange={set("description_th")} />}</Field>
        <Field label="คำอธิบายรายวิชา (อังกฤษ)" full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} disabled={!canEdit} value={v.description_en ?? ""} onChange={set("description_en")} />}</Field>
        <Field label="หมายเหตุ" full>{(id) => <textarea id={id} className="inp" rows={2} style={{ height: "auto", padding: 8 }} disabled={!canEdit} value={v.note ?? ""} onChange={set("note")} />}</Field>
        {course && (
          <>
            {canEdit && (
              <label className="row" style={{ gap: 8 }}>
                <input type="checkbox" checked={newVersion} onChange={(e) => setNewVersion(e.target.checked)} />
                <span>บันทึกเป็น Version ใหม่ (v{course.latest + 1} ปรับปรุง) · หลักสูตรที่ใช้ v{course.latest} อยู่คง Version เดิมจนกว่าจะปรับผ่าน สมอ.08</span>
              </label>
            )}
            <b>ประวัติ Version</b>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Version</th><th>ประเภท</th><th>ปี</th><th>ชื่อวิชา · หน่วยกิต</th><th>คำอธิบาย</th><th>ที่มา</th></tr></thead>
                <tbody>{course.versions.map((x) => <tr key={x.version}><td className="num"><b>v{x.version}</b></td><td><Pill kind={V_KIND[x.kind] ?? "grey"}>{x.kind}</Pill></td><td className="num">{x.year}</td><td className="small">{x.name_th} · {x.credit_text}</td><td className="small" style={{ maxWidth: 320 }}>{x.description_th}</td><td className="small faint">{x.source}</td></tr>)}</tbody>
              </table>
            </div>
            <b>ใช้ในหลักสูตร ({course.used_in.length})</b>
            {course.used_in.length ? (
              <div className="row" style={{ gap: 6 }}>{course.used_in.map((u) => <Link key={u.draft_id} className="pill p-info" href={`/curricula/${u.draft_id}`}>{u.name_th} · v{u.version ?? "?"}</Link>)}</div>
            ) : <span className="small faint">ยังไม่ถูกใช้ในหลักสูตร</span>}
          </>
        )}
      </div>
    </Modal>
  );
}
