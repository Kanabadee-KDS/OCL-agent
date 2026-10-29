"use client";

// All import jobs (the /import page shows only the latest few): filter, search, sort, open, summary.
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmtTime, hasSummary, JOB_STATUS_TH as STATUS_TH, providerLabel, type Job } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";
import { BackLink, DataTable, Filters, Kpi, KpiRow, SearchBox, SelectFilter, type Column } from "@/components/kit";

// KPI cards group the three "running" states into one
const GROUPS: { key: string; label: string; sub: string; match: (s: Job["status"]) => boolean }[] = [
  { key: "running", label: "กำลังทำงาน", sub: "รอคิว · แปลงไฟล์ · AI กำลังสกัด", match: (s) => s === "queued" || s === "ingesting" || s === "extracting" },
  { key: "review", label: "รอตรวจสอบ", sub: "สกัดแล้ว รอยืนยันทีละส่วน", match: (s) => s === "review" },
  { key: "done", label: "บันทึกแล้ว", sub: "เป็นคู่มือหลักสูตรแล้ว", match: (s) => s === "done" },
  { key: "failed", label: "ล้มเหลว", sub: "ดูเหตุผลในหน้างาน", match: (s) => s === "failed" },
];
const PROVIDERS = ["ollama", "gemini", "none"].map((p) => [p, providerLabel(p)] as [string, string]);

const COLUMNS: Column<Job>[] = [
  { key: "created", label: "เริ่มเมื่อ", sort: (j) => j.created_at, render: (j) => <span className="small num">{fmtTime(j.created_at)}</span> },
  {
    key: "file", label: "ไฟล์ / เลขงาน", sort: (j) => j.filename,
    render: (j) => (
      <div style={{ maxWidth: 360 }}>
        <Link href={`/import/${j.id}`} style={{ fontWeight: 600, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.filename}</Link>
        <span className="t2 num">งาน {j.id}{j.counts.ingest?.pages ? ` · ${j.counts.ingest.pages} หน้า` : ""}</span>
      </div>
    ),
  },
  { key: "provider", label: "วิธีอ่าน", render: (j) => <span className="small">{providerLabel(j.provider)}</span> },
  { key: "status", label: "สถานะ", render: (j) => <Pill kind={STATUS_TH[j.status][1]}>{STATUS_TH[j.status][0]}</Pill> },
  {
    key: "confirmed", label: "ยืนยัน", align: "right", sort: (j) => (hasSummary(j) ? j.confirmed_count : null),
    render: (j) => <span className="num">{hasSummary(j) ? `${j.confirmed_count}/${j.parts_total}` : "–"}</span>,
  },
  {
    key: "time", label: "เวลา", align: "right", sort: (j) => j.timings?.total ?? null,
    render: (j) => <span className="small num">{j.timings?.total != null ? `${j.timings.total} s` : "–"}</span>,
  },
  { key: "llm", label: "LLM", render: (j) => <span className="small">{j.llm ? `${j.llm.calls} คำขอ · ${j.llm.prompt_tokens}/${j.llm.completion_tokens} tok` : "–"}</span> },
  {
    key: "act", label: "",
    render: (j) => (
      <div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
        <Link href={`/import/${j.id}`} className="btn xs">เปิด</Link>
        {hasSummary(j) && <Link href={`/import/${j.id}/done`} className="btn xs">สรุป</Link>}
      </div>
    ),
  },
];

const searchText = (j: Job) => `${j.filename} ${j.id}`;
const filterValue = (j: Job, k: string) => (k === "group" ? GROUPS.find((g) => g.match(j.status))?.key : k === "provider" ? j.provider : undefined);

export default function ImportHistoryPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ group: "", provider: "" });
  useEffect(() => { api.list().then(setJobs).catch((e) => setErr((e as Error).message)); }, []);
  const set = (k: keyof typeof f) => (v: string) => setF((o) => ({ ...o, [k]: v }));

  return (
    <>
      <BackLink href="/import">กลับไปหน้าอัปโหลด</BackLink>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "นำเข้าข้อมูลเล่มหลักสูตรด้วย AI", "ประวัติการนำเข้า"]}
        title="ประวัติการนำเข้าทั้งหมด"
        sub="ทุกงานที่อัปโหลด เรียงจากใหม่ไปเก่า · คลิกชื่อไฟล์เพื่อเปิดหน้าตรวจ · ปุ่ม “สรุป” ดูเวลา การใช้ LLM และส่วนที่ยืนยัน"
        actions={<Link href="/import" className="btn primary"><Ic name="upload" size={17} /> นำเข้าเล่มใหม่</Link>}
      />
      {err && <Note kind="warn">{err}</Note>}
      {!jobs && !err && <div className="card pad">กำลังโหลด…</div>}
      {jobs && (
        <>
          <KpiRow>
            {GROUPS.map((g) => (
              <Kpi key={g.key} label={g.label} value={jobs.filter((j) => g.match(j.status)).length} sub={g.sub}
                on={f.group === g.key} onClick={() => set("group")(f.group === g.key ? "" : g.key)} />
            ))}
          </KpiRow>
          <Filters>
            <SearchBox value={q} onChange={setQ} placeholder="ค้นหาชื่อไฟล์หรือเลขงาน" />
            <SelectFilter label="สถานะ" value={f.group} options={GROUPS.map((g) => [g.key, g.label] as [string, string])} onChange={set("group")} />
            <SelectFilter label="วิธีอ่าน" value={f.provider} options={PROVIDERS} onChange={set("provider")} />
          </Filters>
          <DataTable
            rows={jobs}
            columns={COLUMNS}
            rowKey={(j) => j.id}
            search={q}
            searchText={searchText}
            filters={f}
            filterValue={filterValue}
            unit="งาน"
            empty={jobs.length === 0 ? "ยังไม่มีงานนำเข้า" : "ไม่มีงานที่ตรงกับตัวกรอง"}
          />
        </>
      )}
    </>
  );
}
