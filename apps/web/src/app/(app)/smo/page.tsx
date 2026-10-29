"use client";

// smo (mock · US-M1-10): สมอ.08 requests by status with the current step of the flow smo08.
// สร้างคำขอ picks a verified or published curriculum in the user's ขอบเขตข้อมูล (US-M1-09).
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { smoApi, type SmoBrief, type SmoOptions } from "@/lib/api";
import { SMO_KIND } from "@/lib/smo";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, DataTable, Field, Modal, SearchBox, Tabs, useToast, type Column } from "@/components/kit";



const COLUMNS: Column<SmoBrief>[] = [
  { key: "id", label: "เลขที่คำขอ", sort: (r) => r.id, render: (r) => <><Link href={`/smo/${r.id}`} style={{ fontWeight: 600 }} className="num">{r.id}</Link><div className="small faint">สร้าง {r.created_at.slice(0, 10)}</div></> },
  { key: "cur", label: "หลักสูตร", render: (r) => <>{r.name_th}<div className="small faint">{r.faculty}</div></> },
  { key: "type", label: "ประเภทการปรับปรุง", render: (r) => <span className="small">{r.types_th.join(" · ") || "–"}</span> },
  { key: "start", label: "เริ่มใช้", render: (r) => <span className="small">{r.start || "–"}</span> },
  {
    key: "step", label: "ขั้นตอนปัจจุบัน",
    render: (r) => <div style={{ minWidth: 160 }}><span className="small">{r.status === "draft" ? "ยังไม่ส่ง" : r.step_label}</span><Bar pct={((r.status === "approved" ? r.steps_total : r.step) / r.steps_total) * 100} color={r.status === "returned" ? "var(--red)" : "var(--ok)"} /></div>,
  },
  { key: "st", label: "สถานะ", render: (r) => <Pill kind={SMO_KIND[r.status]}>{r.status_th}</Pill> },
];

export default function SmoListPage() {
  const router = useRouter();
  const toast = useToast();
  const [d, setD] = useState<{ items: SmoBrief[]; counts: Record<string, number> } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"all" | SmoBrief["status"]>("all");
  const [q, setQ] = useState("");
  const [opts, setOpts] = useState<SmoOptions | null>(null);
  const [pick, setPick] = useState("");
  useEffect(() => { smoApi.list().then(setD).catch((e) => setErr((e as Error).message)); }, []);
  const rows = useMemo(() => (d?.items ?? []).filter((r) => tab === "all" || r.status === tab), [d, tab]);

  async function create() {
    try { const r = await smoApi.create(Number(pick)); router.push(`/smo/${r.id}`); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <PageHead crumb={["บริหารข้อมูลหลักสูตร", "คู่มือหลักสูตร"]} title="งานปรับปรุงแก้ไขหลักสูตร (สมอ.08)"
        sub="คำขอปรับปรุงแก้ไขหลักสูตรที่อนุมัติแล้ว เช่น เปลี่ยนอาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร ปรับคำอธิบายรายวิชา หรือแผนการศึกษา พร้อมขั้นตอนอนุมัติ · คู่มือที่ตรวจสอบสำเร็จแล้วแก้ได้ทางนี้เท่านั้น"
        actions={<button type="button" className="btn primary" onClick={() => smoApi.options().then(setOpts).catch((e) => toast((e as Error).message, "err"))}>สร้างคำขอ สมอ.08</button>} />
      {err && <Note kind="warn">{err}</Note>}
      <DataTable rows={rows} columns={COLUMNS} rowKey={(r) => r.id} search={q} unit="คำขอ" searchText={(r) => `${r.id} ${r.name_th ?? ""}`}
        empty={d ? "ยังไม่มีคำขอในแท็บนี้" : "กำลังโหลด…"} onRowClick={(r) => router.push(`/smo/${r.id}`)}
        toolbar={<div className="between" style={{ gap: 12, flexWrap: "wrap" }}>
          <Tabs label="สถานะคำขอ" value={tab} onChange={setTab} items={[["all", `ทั้งหมด (${d?.items.length ?? 0})`], ["draft", `ร่าง (${d?.counts.draft ?? 0})`], ["pending", `ระหว่างอนุมัติ (${d?.counts.pending ?? 0})`], ["returned", `ส่งคืนแก้ไข (${d?.counts.returned ?? 0})`], ["approved", `อนุมัติแล้ว (${d?.counts.approved ?? 0})`]] as const} />
          <div style={{ flex: 1, maxWidth: 340 }}><SearchBox value={q} onChange={setQ} placeholder="ค้นหาเลขที่หรือหลักสูตร" /></div>
        </div>} />
      {opts && (
        <Modal open title="สร้างคำขอ สมอ.08" onClose={() => setOpts(null)}
          foot={<><button type="button" className="btn" onClick={() => setOpts(null)}>ยกเลิก</button><button type="button" className="btn primary" disabled={!pick} onClick={create}>สร้างร่างคำขอ</button></>}>
          <div className="stack">
            <Field label="หลักสูตร (ตรวจสอบสำเร็จหรือเผยแพร่แล้ว)">{(id) => (
              <select id={id} className="inp" value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">— เลือก —</option>
                {opts.curricula.map((c) => <option key={c.id} value={c.id}>{c.name_th} (พ.ศ. {c.edition_year ?? "–"})</option>)}
              </select>
            )}</Field>
            {!opts.curricula.length && <Note kind="info">ยังไม่มีหลักสูตรที่ตรวจสอบสำเร็จในขอบเขตข้อมูลของบัญชีนี้</Note>}
            <span className="small faint">ขั้นตอนอนุมัติ: {opts.steps.map((s) => s.position || s.label).join(" → ")}</span>
          </div>
        </Modal>
      )}
    </>
  );
}
