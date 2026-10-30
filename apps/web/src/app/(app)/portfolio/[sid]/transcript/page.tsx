"use client";

// transcript (mock · US-M3-08): the issued document of a student, else the draft (ยังไม่ลงนาม).
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { skillsApi, type TranscriptDoc } from "@/lib/api";
import { Note } from "@/components/ui";
import { BackLink } from "@/components/kit";
import { TranscriptView } from "@/components/skills";

export default function StudentTranscriptPage() {
  const { sid } = useParams<{ sid: string }>();
  const [doc, setDoc] = useState<TranscriptDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { skillsApi.transcript(sid).then(setDoc).catch((e) => setErr((e as Error).message)); }, [sid]);
  return (
    <>
      <div className="between no-print">
        <BackLink href={`/portfolio/${sid}`}>กลับไป Skill Portfolio</BackLink>
        <button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button>
      </div>
      {err && <Note kind="warn">{err}</Note>}
      {doc?.draft && <div className="no-print"><Note kind="info">ยังไม่ออกเอกสาร · แสดงฉบับร่างจากผลที่ยืนยันแล้ว ณ ปัจจุบัน</Note></div>}
      {doc && <TranscriptView doc={doc} />}
    </>
  );
}
