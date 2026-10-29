"use client";

// Preview แบบ สมอ.08 (US-M1-09): the request laid out like the form of สป.อว., printable to A4
// (the book print CSS, app.css .book). [สมมติ: the exact form waits for document A8.]
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { smoApi, type SmoDetail } from "@/lib/api";
import { Note } from "@/components/ui";
import { BackLink } from "@/components/kit";

const name = (t: { name?: unknown; rank?: unknown; highest_level?: unknown } | null) =>
  t ? `${String(t.name ?? "")}${t.rank ? ` (${String(t.rank)})` : ""}${t.highest_level ? ` · คุณวุฒิ${String(t.highest_level)}` : ""}` : "–";

export default function SmoPrint() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<SmoDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { smoApi.get(id).then(setD).catch((e) => setErr((e as Error).message)); }, [id]);
  if (err) return <><BackLink href={`/smo/${id}`}>กลับไปคำขอ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const f = d.fields;
  const title = String(d.curriculum.name_th ?? "").replace(/^หลักสูตร/, "");
  return (
    <>
      <div className="between no-print">
        <BackLink href={`/smo/${d.id}`}>กลับไปคำขอ {d.id}</BackLink>
        <button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button>
      </div>
      <div className="no-print"><Note kind="info">[สมมติ] รูปแบบตามแบบ สมอ.08 ของ สป.อว. ที่เห็นใน mock · แบบฟอร์มฉบับจริงรอเอกสาร A8 จากลูกค้า</Note></div>
      <article className="book" aria-label="Preview แบบ สมอ.08">
        <table className="book-frame">
          <thead><tr><td><div className="book-run"><span>สมอ.08 · {d.id}</span><span>{d.status_th}</span></div></td></tr></thead>
          <tbody><tr><td>
            <header className="book-title">
              <h1>การปรับปรุงแก้ไขหลักสูตร{title}</h1>
              <div>ฉบับปี พ.ศ. {String(d.curriculum.edition_year ?? "–")} · {d.curriculum.faculty} มหาวิทยาลัยศรีนครินทรวิโรฒ</div>
            </header>
            <ol style={{ paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
              <li>หลักสูตรฉบับดังกล่าวนี้ได้รับทราบ/รับรองการเปิดสอนจากสำนักงานปลัดกระทรวงการอุดมศึกษา วิทยาศาสตร์ วิจัยและนวัตกรรม เมื่อวันที่ {f.ack_date || "[วัน เดือน ปี]"}</li>
              <li>สภามหาวิทยาลัยได้อนุมัติการปรับปรุงแก้ไขครั้งนี้แล้ว ในคราวประชุม {f.council || "[ครั้งที่ / วันที่]"}</li>
              <li>หลักสูตรปรับปรุงแก้ไขนี้เริ่มใช้กับนิสิตรุ่นปีการศึกษา {[f.start_term, f.start_year].filter(Boolean).join(" ปีการศึกษา ") || "[ภาค/ปี]"}</li>
              <li>สาระในการปรับปรุงแก้ไข: {d.types_th.join(" · ") || "–"}</li>
            </ol>
            {d.types.includes("teacher") && (
              <>
                <p><b>ขอบเขตการแก้ไข:</b> {d.scope.kind === "child" ? `เล่มลูก · ${d.scope.branch}` : "เล่มแม่ (ทั้งหลักสูตร)"}</p>
                <table>
                  <thead><tr><th style={{ width: "14%" }}>การเปลี่ยนแปลง</th><th>รายชื่ออาจารย์ (เดิม)</th><th>รายชื่ออาจารย์ (ใหม่)</th></tr></thead>
                  <tbody>{d.changes.map((c, i) => <tr key={i}><td>{c.change}</td><td>{name(c.before)}</td><td>{name(c.after)}</td></tr>)}</tbody>
                </table>
              </>
            )}
            {Object.entries(d.details).map(([k, v]) => <p key={k}><b>รายละเอียด{{ course: "รายวิชา", plan: "แผนการศึกษา", other: "อื่น ๆ" }[k] ?? k}:</b> {v}</p>)}
            <p><b>5. เหตุผลในการปรับปรุงแก้ไข:</b> {d.reason || "–"}</p>
            <p className="small" style={{ marginTop: 24 }}>ขั้นตอนอนุมัติ: {d.steps.map((s) => s.position || s.label).join(" → ")} · สถานะ {d.status_th}</p>
          </td></tr></tbody>
        </table>
      </article>
    </>
  );
}
