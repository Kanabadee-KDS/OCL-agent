"use client";

// qa-preview (mock · US-M4-08): R10 of one curriculum (?cid=) or of every curriculum of the
// round the account may see, ฉบับร่าง until every item has a result, printable to A4.
import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { qaApi, type QaDetail } from "@/lib/api";
import { Note } from "@/components/ui";
import { BackLink } from "@/components/kit";
import { R10 } from "@/components/qa";

export default function QaPreviewPage() {
  return <Suspense fallback={<div className="card pad">กำลังโหลด…</div>}><Preview /></Suspense>;
}

function Preview() {
  const { rid } = useParams<{ rid: string }>();
  const cid = useSearchParams().get("cid");
  const [docs, setDocs] = useState<(QaDetail & { complete: boolean })[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { qaApi.preview(Number(rid), cid ? Number(cid) : undefined).then(setDocs).catch((e) => setErr((e as Error).message)); }, [rid, cid]);
  return (
    <>
      <div className="between no-print">
        <BackLink href={cid ? `/qa/${rid}/${cid}` : "/qa"}>กลับ</BackLink>
        <span className="row">{docs && <span className="small faint">{docs.length} หลักสูตร · สมบูรณ์ {docs.filter((d) => d.complete).length}</span>}<button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button></span>
      </div>
      {err && <Note kind="warn">{err}</Note>}
      {!docs && !err && <div className="card pad">กำลังโหลด…</div>}
      {docs?.map((d) => <R10 key={d.curriculum.id} d={d} />)}
    </>
  );
}
