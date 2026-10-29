"use client";

// fac-plo (mock · US-M1-07): the curricula sent to the faculty to check หมวด 3–4, inside the
// user's ขอบเขตข้อมูล (the API filters the list: FS-2e). Opening one leads to the คู่มือ page,
// which is fac-plo-edit: tick หมวด 3 and 4, ตรวจสอบสำเร็จ, or ส่งคืนส่วนกลาง with a note.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { curricula, fmtTime, type CurriculumRow } from "@/lib/api";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Kpi, KpiRow, SearchBox, Tabs, type Column } from "@/components/kit";

type Tab = "todo" | "ready" | "done";
const TAB_OF = (c: CurriculumRow): Tab | null =>
  c.status === "review" ? (c.faculty_checked?.["3"] && c.faculty_checked?.["4"] ? "ready" : "todo")
    : c.status === "verified" || c.status === "published" ? (c.submitted_at ? "done" : null) : null;

const today = () => new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 10); // Thai calendar day

const COLUMNS: Column<CurriculumRow>[] = [
  {
    key: "name", label: "หลักสูตร", sort: (c) => c.name_th,
    render: (c) => <><Link href={`/curricula/${c.id}`} style={{ fontWeight: 600 }}>{c.name_th ?? "(ไม่มีชื่อ)"}</Link><div className="small faint">{c.faculty ?? "–"}</div></>,
  },
  { key: "sent", label: "วันที่ส่ง", sort: (c) => c.submitted_at, render: (c) => <span className="small">{c.submitted_at ? fmtTime(c.submitted_at) : "–"}</span> },
  { key: "by", label: "ผู้ส่ง", render: (c) => <span className="small">{c.submitted_by ?? "–"}</span> },
  {
    key: "due", label: "ครบกำหนด (5 วันทำการ)", sort: (c) => c.review_due_at,
    render: (c) => !c.review_due_at ? "–" : c.status === "review" && c.review_due_at < today()
      ? <Pill kind="red">{c.review_due_at} · เกินกำหนด</Pill> : <span className="small">{c.review_due_at}</span>,
  },
  { key: "s3", label: "หมวด 3", render: (c) => (c.faculty_checked?.["3"] ? <Pill kind="ok">✓ ตรวจแล้ว</Pill> : <Pill kind="grey">ยังไม่ตรวจ</Pill>) },
  { key: "s4", label: "หมวด 4", render: (c) => (c.faculty_checked?.["4"] ? <Pill kind="ok">✓ ตรวจแล้ว</Pill> : <Pill kind="grey">ยังไม่ตรวจ</Pill>) },
  { key: "go", label: "", render: (c) => <Link className="btn xs" href={`/curricula/${c.id}`}>{c.status === "review" ? "ตรวจ" : "ดู"}</Link> },
];

export default function FacultyReviewPage() {
  const [rows, setRows] = useState<CurriculumRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("todo");
  const [q, setQ] = useState("");
  useEffect(() => { curricula.list().then((l) => setRows(l.items)).catch((e) => setErr((e as Error).message)); }, []);
  const by = useMemo(() => {
    const out: Record<Tab, CurriculumRow[]> = { todo: [], ready: [], done: [] };
    for (const c of rows ?? []) { const t = TAB_OF(c); if (t) out[t].push(c); }
    return out;
  }, [rows]);
  const overdue = by.todo.filter((c) => c.review_due_at && c.review_due_at < today()).length;

  return (
    <>
      <PageHead crumb={["บริหารข้อมูลหลักสูตร", "ตรวจสอบและบันทึก PLO โดยคณะ"]} title="ตรวจสอบและบันทึก PLO โดยคณะ"
        sub="หลักสูตรที่ส่วนกลางส่งให้ตรวจหมวด 3 (PLO · KSEC) และหมวด 4 (Curriculum Mapping) ภายใน 5 วันทำการ · เห็นเฉพาะหลักสูตรในขอบเขตข้อมูลของบัญชีนี้" />
      {err && <Note kind="warn">{err}</Note>}
      <KpiRow>
        <Kpi label="รอตรวจ" value={rows ? by.todo.length : "–"} sub={overdue ? `เกินกำหนด ${overdue}` : "ยังไม่ครบ 2 หมวด"} />
        <Kpi label="ครบหมวด 3–4 แล้ว" value={rows ? by.ready.length : "–"} sub="รอกด ตรวจสอบสำเร็จ" />
        <Kpi label="ดำเนินการแล้ว" value={rows ? by.done.length : "–"} sub="ตรวจสอบสำเร็จ/เผยแพร่" />
      </KpiRow>
      <DataTable rows={by[tab]} columns={COLUMNS} rowKey={(c) => c.id} search={q} searchText={(c) => `${c.name_th ?? ""} ${c.faculty ?? ""}`}
        unit="หลักสูตร" empty={rows ? "ไม่มีหลักสูตรในแท็บนี้" : "กำลังโหลด…"}
        toolbar={<div className="stack">
          <Tabs label="สถานะการตรวจ" value={tab} onChange={setTab} items={[["todo", `รอตรวจ (${by.todo.length})`], ["ready", `ครบหมวด 3–4 แล้ว (${by.ready.length})`], ["done", `ดำเนินการแล้ว (${by.done.length})`]] as const} />
          <SearchBox value={q} onChange={setQ} placeholder="ค้นชื่อหลักสูตรหรือคณะ" />
        </div>} />
    </>
  );
}
