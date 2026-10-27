"use client";

// All import jobs (the /import page shows only the latest few): filter, search, open, summary.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, fmtTime, hasSummary, JOB_STATUS_TH as STATUS_TH, providerLabel, type Job } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";

// KPI cards group the three "running" states into one
const GROUPS: { key: string; label: string; sub: string; match: (s: Job["status"]) => boolean }[] = [
  { key: "running", label: "กำลังทำงาน", sub: "รอคิว · แปลงไฟล์ · AI กำลังสกัด", match: (s) => s === "queued" || s === "ingesting" || s === "extracting" },
  { key: "review", label: "รอตรวจสอบ", sub: "สกัดแล้ว รอยืนยันทีละส่วน", match: (s) => s === "review" },
  { key: "done", label: "บันทึกแล้ว", sub: "เป็นคู่มือหลักสูตรแล้ว", match: (s) => s === "done" },
  { key: "failed", label: "ล้มเหลว", sub: "ดูเหตุผลในหน้างาน", match: (s) => s === "failed" },
];
const PROVIDERS = [["", "ทุกวิธีอ่าน"], ["ollama", "Local AI · Gemma"], ["gemini", "Cloud AI · Gemini"], ["none", "อ่านด้วยกฎ"]] as const;

export default function ImportHistoryPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [group, setGroup] = useState<string | null>(null);
  const [provider, setProvider] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => { api.list().then(setJobs).catch((e) => setErr((e as Error).message)); }, []);

  const rows = useMemo(() => {
    const g = GROUPS.find((x) => x.key === group);
    const needle = q.trim().toLowerCase();
    return (jobs ?? []).filter(
      (j) =>
        (!g || g.match(j.status)) &&
        (!provider || j.provider === provider) &&
        (!needle || j.filename.toLowerCase().includes(needle) || j.id.includes(needle)),
    );
  }, [jobs, group, provider, q]);

  return (
    <>
      <Link href="/import" className="link-btn small" style={{ color: "var(--red-ink)" }}><Ic name="back" size={14} /> กลับไปหน้าอัปโหลด</Link>
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
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
            {GROUPS.map((g) => (
              <button
                key={g.key}
                className="card kpi"
                style={{ textAlign: "left", cursor: "pointer", borderColor: group === g.key ? "var(--red)" : undefined }}
                onClick={() => setGroup(group === g.key ? null : g.key)}
                aria-pressed={group === g.key}
              >
                <span className="l">{g.label}</span>
                <span className="v num">{jobs.filter((j) => g.match(j.status)).length}</span>
                <span className="small faint">{g.sub}</span>
              </button>
            ))}
          </div>
          <section className="card pad stack">
            <div className="between">
              <div className="row" style={{ flex: 1, minWidth: 0 }}>
                <input
                  className="inp"
                  type="search"
                  placeholder="ค้นหาชื่อไฟล์หรือเลขงาน"
                  aria-label="ค้นหาชื่อไฟล์หรือเลขงาน"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  style={{ maxWidth: 320 }}
                />
                <div className="seg">
                  {PROVIDERS.map(([v, label]) => (
                    <button key={v} type="button" className={provider === v ? "on" : ""} onClick={() => setProvider(v)}>{label}</button>
                  ))}
                </div>
              </div>
              <span className="small faint">{rows.length} จาก {jobs.length} งาน</span>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr><th>เริ่มเมื่อ</th><th>ไฟล์ / เลขงาน</th><th>วิธีอ่าน</th><th>สถานะ</th><th className="r">ยืนยัน</th><th className="r">เวลา</th><th>LLM</th><th></th></tr>
                </thead>
                <tbody>
                  {rows.map((j) => (
                    <tr key={j.id}>
                      <td className="small num">{fmtTime(j.created_at)}</td>
                      <td style={{ maxWidth: 360 }}>
                        <Link href={`/import/${j.id}`} style={{ fontWeight: 600, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.filename}</Link>
                        <span className="t2 num">งาน {j.id}{j.counts.ingest?.pages ? ` · ${j.counts.ingest.pages} หน้า` : ""}</span>
                      </td>
                      <td className="small">{providerLabel(j.provider)}</td>
                      <td><Pill kind={STATUS_TH[j.status][1]}>{STATUS_TH[j.status][0]}</Pill></td>
                      <td className="r num">{hasSummary(j) ? `${j.confirmed_count}/${j.parts_total}` : "–"}</td>
                      <td className="r small num">{j.timings?.total != null ? `${j.timings.total} s` : "–"}</td>
                      <td className="small">{j.llm ? `${j.llm.calls} คำขอ · ${j.llm.prompt_tokens}/${j.llm.completion_tokens} tok` : "–"}</td>
                      <td>
                        <div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
                          <Link href={`/import/${j.id}`} className="btn xs">เปิด</Link>
                          {hasSummary(j) && <Link href={`/import/${j.id}/done`} className="btn xs">สรุป</Link>}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={8} className="small faint">{jobs.length === 0 ? "ยังไม่มีงานนำเข้า" : "ไม่มีงานที่ตรงกับตัวกรอง"}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
