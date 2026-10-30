// The public check of a Skill Transcript (BR-M3-05 · US-M3-09): whoever scans the QR or types
// the number sees the name, curriculum, date issued and the state of the digital signature,
// without signing in. Each check is counted (R09). Outside (app), so no session is needed.
import { INTERNAL_API_BASE } from "@/auth";
import { fmtTime, type TranscriptCheck } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function VerifyPage({ params }: { params: Promise<{ no: string }> }) {
  const { no } = await params;
  let d: TranscriptCheck | null = null;
  let error: string | null = null;
  try {
    const r = await fetch(`${INTERNAL_API_BASE}/api/public/transcripts/${encodeURIComponent(no)}`, { cache: "no-store" });
    if (r.ok) d = (await r.json()) as TranscriptCheck;
    else error = r.status === 404 ? "ไม่พบเอกสารเลขที่นี้" : "ตรวจสอบไม่สำเร็จ ลองใหม่ภายหลัง";
  } catch {
    error = "ตรวจสอบไม่สำเร็จ ลองใหม่ภายหลัง";
  }
  return (
    <main style={{ maxWidth: 560, margin: "40px auto", padding: "0 16px" }}>
      <section className="card pad stack">
        <div className="row" style={{ gap: 10 }}><span className="av" style={{ background: "var(--red)", color: "#fff" }}>มศว</span><div><b>ตรวจสอบเอกสาร Skill Transcript</b><div className="small faint">มหาวิทยาลัยศรีนครินทรวิโรฒ</div></div></div>
        <div className="small">เลขที่ <b className="num">{decodeURIComponent(no)}</b></div>
        {error && <div className="note warn">{error}</div>}
        {d && (
          <>
            <div className={`note ${d.signature.valid ? "ok" : "warn"}`}>
              {d.signature.valid ? "เอกสารนี้ออกโดยระบบ และข้อมูลตรงกับที่ลงนามไว้" : "ข้อมูลของเอกสารไม่ตรงกับที่ลงนามไว้ โปรดติดต่อมหาวิทยาลัย"}
              {d.signature.sample && " · ลายมือชื่อดิจิทัลเป็นบริการตัวอย่าง ยังไม่มีผลทางกฎหมาย"}
            </div>
            <table className="tbl">
              <tbody>
                <tr><th style={{ width: "36%" }}>ชื่อ-สกุล</th><td>{d.name_th}</td></tr>
                <tr><th>รหัสนิสิต</th><td className="num">{d.sid}</td></tr>
                <tr><th>หลักสูตร</th><td>{d.program}{d.curriculum ? <div className="small faint">{d.curriculum}</div> : null}</td></tr>
                <tr><th>คณะ</th><td>{d.faculty}</td></tr>
                <tr><th>วันที่ออก</th><td>{fmtTime(d.issued_at)}</td></tr>
                <tr><th>ผู้ลงนาม</th><td>{d.signer.name_th} · {d.signer.position}</td></tr>
                <tr><th>ตรวจสอบแล้ว</th><td className="num">{d.checks} ครั้ง</td></tr>
              </tbody>
            </table>
          </>
        )}
      </section>
    </main>
  );
}
