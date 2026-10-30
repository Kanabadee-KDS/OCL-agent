"use client";

// plan-assign / rep-assign (mock · US-M2-01 02): who records the plan and the report of each
// course or module offered in a term (several people, "= แผน" copies the plan's list), when
// recording is open, copy from the previous term, e-mail the recorders, export the list.
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { fmtTime, m2Api, type M2Doc, type M2Item, type M2Items, type M2Term } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Field, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";
import { StaffPicker, TermSelect, useTerm } from "@/components/m2";

export default function AssignPage() {
  const { data: session } = useSession();
  const canEdit = canMenu(session?.user?.perms, "p1", "edit");
  const toast = useToast();
  const [terms, slug, setSlug, termErr] = useTerm();
  const [d, setD] = useState<M2Items | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ kind: "", state: "", unit: "" });
  const [pick, setPick] = useState<{ item: M2Item; doc: M2Doc } | null>(null);
  const [settings, setSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = () => slug && m2Api.items(slug).then(setD).catch((e) => toast((e as Error).message, "err"));
  useEffect(() => { if (slug) m2Api.items(slug).then(setD).catch((e) => toast((e as Error).message, "err")); }, [slug, toast]);

  const items = useMemo(() => (d?.items ?? []).filter((i) => i.offered), [d]);
  const both = (i: M2Item) => i.assign.plan.length > 0 && i.assign.report.length > 0;
  const rows = items.filter((i) => (!f.kind || i.kind === f.kind) && (!f.unit || i.unit === f.unit)
    && (!f.state || (f.state === "done" ? both(i) : !both(i))));
  async function run<T>(fn: () => Promise<T>, msg: (r: T) => string) {
    setBusy(true);
    try { const r = await fn(); toast(msg(r)); await load(); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  const cell = (i: M2Item, doc: M2Doc) => (
    <div className="row" style={{ gap: 4, flexWrap: "nowrap", alignItems: "flex-start" }}>
      <span className="small" style={{ flex: 1 }}>{i.assign[doc].length ? i.assign[doc].map((p) => p.name).join(", ") : <span className="faint">ยังไม่กำหนด</span>}</span>
      {canEdit && <button type="button" className="btn xs" onClick={() => setPick({ item: i, doc })}>แก้</button>}
      {canEdit && doc === "report" && i.assign.plan.length > 0 && <button type="button" className="btn xs" title="ใช้รายชื่อเดียวกับผู้บันทึกแผน" onClick={() => run(() => m2Api.assign(slug, i.key, "report", i.assign.plan.map((p) => p.pid)), () => `ผู้บันทึกรายงาน ${i.code} = แผน`)}>= แผน</button>}
    </div>
  );
  const columns: Column<M2Item>[] = [
    { key: "code", label: "รายวิชา/ชุดวิชา", sort: (i) => i.code, render: (i) => <><b>{i.kind === "module" ? "ชุดวิชา " : ""}{i.code}</b> {i.kind === "course" && i.name_th}<div className="small faint">{i.kind === "module" ? `${i.courses.join(", ")} · ` : ""}{i.unit}</div></> },
    { key: "plan", label: "ผู้บันทึกแผนการจัดการเรียนรู้", render: (i) => cell(i, "plan") },
    { key: "report", label: "ผู้บันทึกรายงานผล", render: (i) => cell(i, "report") },
    { key: "st", label: "สถานะ", render: (i) => (both(i) ? <Pill kind="ok">ครบ</Pill> : <Pill kind="warn">ยังไม่ครบ</Pill>) },
  ];
  function exportCsv() {
    const head = ["รหัส", "ประเภท", "ชื่อ", "หน่วยงานเจ้าของวิชา", "ผู้บันทึกแผน", "ผู้บันทึกรายงานผล"];
    const body = items.map((i) => [i.code, i.kind === "module" ? "ชุดวิชา" : "รายวิชา", i.name_th, i.unit, i.assign.plan.map((p) => `${p.name} (${p.pid})`).join("; "), i.assign.report.map((p) => `${p.name} (${p.pid})`).join("; ")]);
    const url = URL.createObjectURL(new Blob([toCsv(head, body)], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `assign-${slug}.csv` }).click();
    URL.revokeObjectURL(url);
  }
  const t = d?.term;
  return (
    <>
      <PageHead crumb={["แผนการจัดการเรียนรู้", "กำหนดผู้บันทึก"]} title="กำหนดผู้บันทึกแผนและรายงานผลการจัดการเรียนรู้"
        sub={<>ต่อรายวิชา/ชุดวิชาที่เปิดสอนในภาค · ผู้บันทึกแต่ละช่องเข้าได้เฉพาะหน้าบันทึกของช่องนั้น{d?.synced_at && <> · ตารางสอน SUPREME ดึงล่าสุด {fmtTime(d.synced_at)}</>}</>}
        actions={<>
          {terms && <TermSelect terms={terms} slug={slug} onChange={setSlug} />}
          {canEdit && <button type="button" className="btn" disabled={busy || !slug} onClick={() => run(() => m2Api.sync(slug), (r) => `ดึงตารางสอนแล้ว ${r.items} รายการ`)}>ดึงตารางสอนใหม่</button>}
          {canEdit && <button type="button" className="btn" disabled={busy} onClick={() => run(() => m2Api.copyAssign(slug), (r) => `คัดลอกจากภาค ${r.from} แล้ว ${r.copied} ช่อง`)}>คัดลอกจากภาคก่อน</button>}
          {canEdit && <button type="button" className="btn" disabled={busy} onClick={() => run(() => m2Api.notify(slug), (r) => (r.sent ? `ส่งอีเมลถึงผู้บันทึก ${r.sent} คน` : "วันนี้แจ้งไปแล้ว หรือยังไม่มีผู้บันทึก"))}>แจ้งเตือนทางอีเมล</button>}
          <button type="button" className="btn" disabled={!items.length} onClick={exportCsv}>รายงานการกำหนดสิทธิ์</button>
          {canEdit && <button type="button" className="btn primary" disabled={!t} onClick={() => setSettings(true)}>ช่วงเวลาบันทึก</button>}
        </>} />
      {termErr && <Note kind="warn">{termErr}</Note>}
      {t && <Note kind="info">ภาค {t.term}: เปิดภาค {t.starts_on ?? "–"} ถึง {t.ends_on ?? "–"} · บันทึกแผน {t.plan_open ?? "เปิด"} – {t.plan_close ?? "ไม่กำหนด"} · บันทึกรายงาน {t.report_open ?? "เปิด"} – {t.report_close ?? "ไม่กำหนด"}{!t.set && " · ยังไม่ได้ตั้งค่า (ไม่จำกัดช่วงเวลา)"}</Note>}
      <KpiRow>
        <Kpi label="รายวิชา/ชุดวิชาทั้งหมด" value={items.length} sub={`ชุดวิชา ${items.filter((i) => i.kind === "module").length}`} on={!f.state} onClick={() => setF((x) => ({ ...x, state: "" }))} />
        <Kpi label="ครบทั้ง 2 ช่อง" value={items.filter(both).length} on={f.state === "done"} onClick={() => setF((x) => ({ ...x, state: x.state === "done" ? "" : "done" }))} />
        <Kpi label="กำหนดผู้บันทึกแผนแล้ว" value={items.filter((i) => i.assign.plan.length).length} />
        <Kpi label="กำหนดผู้บันทึกรายงานแล้ว" value={items.filter((i) => i.assign.report.length).length} />
        <Kpi label="ยังไม่ครบ" value={items.filter((i) => !both(i)).length} on={f.state === "todo"} onClick={() => setF((x) => ({ ...x, state: x.state === "todo" ? "" : "todo" }))} />
      </KpiRow>
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.key} search={q} searchText={(i) => `${i.code} ${i.name_th ?? ""} ${i.courses.join(" ")} ${i.assign.plan.map((p) => p.name).join(" ")} ${i.assign.report.map((p) => p.name).join(" ")}`}
        unit="รายการ" empty={d ? "ไม่มีรายการ" : "กำลังโหลด…"}
        toolbar={<Filters>
          <SearchBox value={q} onChange={setQ} placeholder="ค้นรหัส ชื่อวิชา หรือผู้บันทึก" />
          <SelectFilter label="แสดง" value={f.kind} options={[["module", "ตามชุดวิชา"], ["course", "ตามรายวิชา"]]} onChange={(v) => setF((x) => ({ ...x, kind: v }))} />
          <SelectFilter label="หน่วยงาน" value={f.unit} options={[...new Set(items.map((i) => i.unit ?? ""))].filter(Boolean).sort()} onChange={(v) => setF((x) => ({ ...x, unit: v }))} />
        </Filters>} />
      {pick && <StaffPicker title={`${pick.doc === "plan" ? "ผู้บันทึกแผน" : "ผู้บันทึกรายงานผล"} · ${pick.item.code}`} value={pick.item.assign[pick.doc]} onClose={() => setPick(null)}
        onSave={(pids) => { const p = pick; setPick(null); run(() => m2Api.assign(slug, p.item.key, p.doc, pids), () => `บันทึกผู้บันทึก ${p.item.code} แล้ว`); }} />}
      {settings && t && <TermSettings term={t} onClose={() => setSettings(false)} onSaved={() => { setSettings(false); load(); }} />}
    </>
  );
}

function TermSettings({ term, onClose, onSaved }: { term: M2Term; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({ ...term });
  const keys: [keyof M2Term, string][] = [["starts_on", "วันเปิดภาค"], ["ends_on", "วันสุดท้ายของภาค"], ["plan_open", "เปิดบันทึกแผน"], ["plan_close", "ปิดรับแผน"], ["report_open", "เปิดบันทึกรายงาน"], ["report_close", "ปิดรับรายงาน"]];
  async function save() {
    try { await m2Api.saveTerm(term.slug, v); toast("บันทึกช่วงเวลาแล้ว"); onSaved(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <Modal open title={`ช่วงเวลาเปิดให้บันทึก ภาค ${term.term}`} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" onClick={save}>บันทึก</button></>}>
      <div className="stack">
        <div className="form-grid">
          {keys.map(([k, l]) => <Field key={k} label={l}>{(id) => <input id={id} type="date" className="inp" value={String(v[k] ?? "")} onChange={(e) => setV((x) => ({ ...x, [k]: e.target.value || null }))} />}</Field>)}
          <Field label="เป้าหมายความคืบหน้า (%)">{(id) => <input id={id} type="number" className="inp" value={v.target_pct} onChange={(e) => setV((x) => ({ ...x, target_pct: Number(e.target.value) || 70 }))} />}</Field>
        </div>
        <Note kind="info">ถ้าไม่กำหนดวันปิดรับแผน ระบบใช้ 2 สัปดาห์ก่อนวันเปิดภาค (BR-M2-04) · นอกช่วงเวลา ผู้บันทึกเปิดดูได้แต่บันทึกหรือส่งไม่ได้ · ส่งรายงานผลได้หลังวันสุดท้ายของภาค [สมมติ]</Note>
      </div>
    </Modal>
  );
}
