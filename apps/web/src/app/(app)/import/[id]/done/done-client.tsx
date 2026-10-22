"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, fmtTime, PART_LABELS, type Job } from "@/lib/api";
import { Ic, Note, Pill, Steps } from "@/components/ui";

export default function DoneClient() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => { api.get(id).then(setJob).catch(() => setJob(null)); }, [id]);
  if (!job) return <div className="card pad">กำลังโหลด…</div>;
  const parts = job.counts.parts ?? {};
  return (
    <>
      <Steps current={4} />
      <section className="card pad stack" style={{ alignItems: "center", textAlign: "center", padding: "48px 20px" }}>
        <span className="av" style={{ width: 64, height: 64, background: "var(--ok)", color: "#fff" }}><Ic name="check" size={32} width={2.5} /></span>
        <h1 style={{ fontSize: 24, margin: 0 }}>{job.status === "done" ? "บันทึกข้อมูลเข้าระบบแล้ว" : "ยังไม่ได้บันทึก"}</h1>
        <Pill kind="grey">สถานะ: 1. ร่างนำเข้าหลักสูตร</Pill>
        <p className="muted" style={{ margin: 0 }}>
          โครงสร้างหลักสูตร {parts.structure ?? 0} โหนด · PLO {parts.plo ?? 0} · รายวิชา {parts.courses ?? 0} · ยืนยันแล้ว {job.confirmed_count}/{job.parts_total} ส่วน
        </p>
        <div className="small faint">{job.filename} · {fmtTime(job.created_at)} → {fmtTime(job.finished_at)}</div>
        <div className="row" style={{ justifyContent: "center" }}>
          <Link className="btn" href="/import">นำเข้าเล่มอื่น</Link>
          <Link className="btn" href={`/import/${id}`}>เปิดดูข้อมูลที่ยืนยันแล้ว</Link>
          <a className="btn primary" href={api.fileUrl(id, "ingest/book.md")} target="_blank"><Ic name="download" size={16} /> Markdown ทั้งเล่ม</a>
        </div>
      </section>
      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
        <div className="card kpi"><span className="l">เวลาที่ AI ใช้ทั้งหมด</span><span className="v num">{job.timings.total ?? "–"} s</span><span className="small faint">แปลงไฟล์ {job.timings.ingest ?? "–"} s · สกัดรายวิชา {job.timings.courses ?? "–"} s</span></div>
        <div className="card kpi"><span className="l">LLM</span><span className="v num">{job.llm ? `${job.llm.calls} คำขอ` : "ไม่ใช้"}</span><span className="small faint">{job.llm ? `${job.llm.model} · ${job.llm.prompt_tokens}/${job.llm.completion_tokens} tokens · ${job.llm.seconds} s` : "อ่านด้วยกฎอย่างเดียว"}</span></div>
        <div className="card kpi"><span className="l">เล่ม</span><span className="v num">{job.counts.ingest?.pages ?? "–"} หน้า</span><span className="small faint">ตาราง {job.counts.ingest?.tables} · รูป {job.counts.ingest?.images} · หมวด {job.counts.ingest?.chapters.join(",")}</span></div>
      </div>
      <section className="card pad stack">
        <h2 className="h2">ส่วนที่ยืนยัน</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ส่วน</th><th>สถานะ</th><th>ยืนยันเมื่อ</th><th>ไฟล์</th></tr></thead>
            <tbody>
              {job.parts.map((k) => (
                <tr key={k}>
                  <td>{PART_LABELS[k][0]}</td>
                  <td>{job.confirmed[k] ? <Pill kind="ok">ยืนยันแล้ว</Pill> : <Pill kind="grey">บันทึกเป็นร่าง รอตรวจภายหลัง</Pill>}</td>
                  <td className="small">{fmtTime(job.confirmed[k] ?? null)}</td>
                  <td className="row">
                    <a className="btn xs" href={api.fileUrl(id, `extract/${k}.json`)} target="_blank">JSON</a>
                    <a className="btn xs" href={api.fileUrl(id, `extract/md/${{ info: "1-program_info.md", teachers: "8-teachers.md", plan: "9-admission_plan.md", modules: "3b-modules.md", structure: "2-course_structure.md", plo: "4-plos.md", ksec: "4b-ksec.md", courses: "3-courses_list.md", mapping: "5-curriculum_mapping.md", appr: "7-approval.md" }[k] ?? ""}`)} target="_blank">Markdown</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note kind="info">ใน R1 ข้อมูลที่ยืนยันจะถูกเขียนลงคู่มือหลักสูตร (หมวด 3–4) และเปิดให้ &ldquo;ส่งให้คณะตรวจสอบ&rdquo; ตาม workflow ของลูกค้า · POC นี้เก็บเป็นไฟล์ JSON + Markdown ต่อ job</Note>
      </section>
    </>
  );
}
