"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { curricula, fmtTime, STATUS_KIND, type CurriculumList } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";

export default function CurriculaPage() {
  const [data, setData] = useState<CurriculumList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  useEffect(() => { curricula.list().then(setData).catch((e) => setErr((e as Error).message)); }, []);
  const items = (data?.items ?? []).filter((i) => !filter || i.status === filter);
  return (
    <>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "คู่มือหลักสูตร"]}
        title="คู่มือหลักสูตร"
        sub="สถานะของคู่มือหลักสูตรที่นำเข้าจากเล่มด้วย AI: ร่าง → คณะตรวจสอบ (5 วันทำการ แก้ได้เฉพาะหมวด 3–4) → ตรวจสอบสำเร็จ (ล็อก) → เผยแพร่"
        actions={<Link href="/import" className="btn primary"><Ic name="ai" size={17} /> นำเข้าจากเล่มด้วย AI</Link>}
      />
      {err && <Note kind="warn">{err}</Note>}
      {data && (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
            {Object.entries(data.statuses).map(([k, label]) => (
              <button key={k} className={`card kpi ${filter === k ? "on" : ""}`} style={{ textAlign: "left", cursor: "pointer", borderColor: filter === k ? "var(--red)" : undefined }} onClick={() => setFilter(filter === k ? null : k)}>
                <span className="l">{label}</span>
                <span className="v num">{data.counts[k] ?? 0}</span>
                <span className="small faint">{k === "review" ? "กำหนด 5 วันทำการ" : k === "verified" ? "ล็อก แก้ผ่าน สมอ.08" : k === "published" ? "เปิด/ปิดโดยส่วนกลาง" : "จากการนำเข้าด้วย AI"}</span>
              </button>
            ))}
          </div>
          <section className="card pad stack">
            <div className="between"><h2 className="h2">รายการคู่มือหลักสูตร {filter ? `· ${data.statuses[filter]}` : ""}</h2><span className="small faint">{items.length} รายการ</span></div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>หลักสูตร</th><th>ระดับ</th><th>คณะ</th><th>ปีที่เริ่มใช้</th><th>ฉบับ</th><th>สถานะ</th><th>กำหนดตรวจ</th><th>ล่าสุด</th><th></th></tr></thead>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.id} className="click">
                      <td><Link href={`/curricula/${c.id}`} style={{ fontWeight: 600 }}>{c.name_th ?? "(ไม่มีชื่อ)"}</Link><div className="small faint">{c.program_code ?? "ไม่มีรหัส สกอ."} · งาน {c.job_id}</div></td>
                      <td>{c.level ?? "–"}</td>
                      <td className="small">{c.faculty ?? "–"}</td>
                      <td>{c.start_year ?? "–"}</td>
                      <td className="small">{c.revision_type ?? "–"}</td>
                      <td><Pill kind={STATUS_KIND[c.status]}>{c.status_th}</Pill>{c.status === "review" && <div className="small faint">ติ๊กแล้ว {Object.values(c.faculty_checked ?? {}).filter(Boolean).length}/2 หมวด</div>}</td>
                      <td className="small">{c.review_due_at ?? "–"}</td>
                      <td className="small">{c.last_event ? `${fmtTime(c.last_event.ts)} · ${c.last_event.by}` : fmtTime(c.finalized_at)}</td>
                      <td><Link href={`/curricula/${c.id}`} className="btn xs">{c.status === "review" ? "ตรวจสอบ" : c.status === "import" ? "แก้ไขร่าง / ส่งตรวจ" : "ดูรายละเอียด"}</Link></td>
                    </tr>
                  ))}
                  {items.length === 0 && <tr><td colSpan={9} className="small faint">ยังไม่มีคู่มือหลักสูตร{filter ? "ในสถานะนี้" : " · นำเข้าจากเล่มแล้วกด \"บันทึกเข้าระบบ\""}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
