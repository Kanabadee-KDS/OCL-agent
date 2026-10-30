"use client";

// my-transcript (mock · US-M3-09): the draft until issued; then the number to copy and the
// signed document to print as PDF.
import { useEffect, useState } from "react";
import { skillsApi, type TranscriptDoc } from "@/lib/api";
import { Note, PageHead } from "@/components/ui";
import { useToast } from "@/components/kit";
import { TranscriptView } from "@/components/skills";

export default function MyTranscriptPage() {
  const toast = useToast();
  const [doc, setDoc] = useState<TranscriptDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { skillsApi.myTranscript().then(setDoc).catch((e) => setErr((e as Error).message)); }, []);
  return (
    <>
      <div className="no-print">
        <PageHead crumb={["สำหรับนิสิต"]} title="Skill Transcript ของฉัน" sub="เอกสารจะออกให้เมื่อสำเร็จการศึกษาและผู้มีอำนาจลงนามแล้ว ระหว่างนี้ดูฉบับร่างได้"
          actions={doc && !doc.draft && <>
            <button type="button" className="btn" onClick={() => navigator.clipboard.writeText(doc.no ?? "").then(() => toast("คัดลอกเลขที่เอกสารแล้ว"))}>คัดลอกเลขที่ {doc.no}</button>
            <button type="button" className="btn primary" onClick={() => window.print()}>ดาวน์โหลด PDF</button>
          </>} />
        {err && <Note kind="warn">{err}</Note>}
        {doc?.draft && <Note kind="info">ฉบับร่าง · ยังไม่ลงนาม{doc.readiness.graduated ? "" : " · ออกเอกสารได้เมื่อสำเร็จการศึกษา"}</Note>}
      </div>
      {doc && <TranscriptView doc={doc} />}
    </>
  );
}
