"use client";

// Preview ก่อนบันทึก (US-M1-15 · FS-3f): the 10 extracted parts as Markdown, laid out like a
// book and printed to A4 by the browser (app.css .book), Markdown edited by hand included.
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Job } from "@/lib/api";
import { Markdown, Note } from "@/components/ui";
import { BackLink } from "@/components/kit";

const FILES = ["1-program_info.md", "8-teachers.md", "9-admission_plan.md", "2-course_structure.md", "4-plos.md", "4b-ksec.md", "3b-modules.md", "3-courses_list.md", "5-curriculum_mapping.md", "7-approval.md"];

export default function ImportPrint() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [md, setMd] = useState<string[] | null>(null);
  const [at] = useState(() => new Date());
  useEffect(() => {
    api.get(id).then(setJob).catch(() => setJob(null));
    Promise.all(FILES.map((n) => api.fileText(id, `extract/md/${n}`))).then(setMd).catch(() => setMd([]));
  }, [id]);
  if (!md) return <div className="card pad">กำลังโหลด…</div>;
  const stamp = at.toLocaleString("th-TH", { dateStyle: "long", timeStyle: "short" });
  return (
    <>
      <div className="between no-print">
        <BackLink href={`/import/${id}`}>กลับไปหน้าตรวจ</BackLink>
        <button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button>
      </div>
      <div className="no-print"><Note kind="info">ข้อมูลที่สกัดได้ล่าสุด (รวมการแก้ที่บันทึกร่างแล้ว) ก่อนบันทึกเข้าระบบ · ส่วนที่ยังไม่ยืนยันอาจเปลี่ยนได้</Note></div>
      <article className="book" aria-label="Preview ข้อมูลที่สกัดได้">
        <table className="book-frame">
          <thead><tr><td><div className="book-run"><span>ข้อมูลที่สกัดจาก {job?.filename ?? id} · ยืนยันแล้ว {job?.confirmed_count ?? 0}/{job?.parts.length ?? 10} ส่วน</span><span>ส่งออก {stamp}</span></div></td></tr></thead>
          <tbody><tr><td>
            {md.map((t, i) => <section key={FILES[i]} style={i ? undefined : { breakBefore: "auto" }}><Markdown text={t} /></section>)}
          </td></tr></tbody>
        </table>
      </article>
    </>
  );
}
