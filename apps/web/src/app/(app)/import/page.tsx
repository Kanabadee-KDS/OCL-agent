"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { can } from "@/lib/perm";
import { api, fmtBytes, fmtTime, hasSummary, JOB_STATUS_TH as STATUS_TH, PART_LABELS, providerLabel, type Job } from "@/lib/api";
import { Ic, Note, PageHead, Pill, Steps } from "@/components/ui";

const ORDER = ["info", "teachers", "plan", "plo", "ksec", "structure", "modules", "courses", "mapping", "appr"];
const POC_PARTS = new Set(ORDER);
const RECENT = 8; // rows on this page; the rest are on /import/history

export default function ImportPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const canWrite = can(session?.user?.roles, "import_write");
  const [provider, setProvider] = useState<"ollama" | "none" | "gemini">("ollama");
  const [target, setTarget] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.list().then(setHistory).catch(() => setHistory([]));
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function start() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const job = await api.create(file, provider, target || undefined);
      router.push(`/import/${job.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  const geminiOn = Boolean(health?.gemini_configured);

  return (
    <>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "นำเข้าข้อมูลเล่มหลักสูตรด้วย AI"]}
        title="นำเข้าข้อมูลเล่มหลักสูตร"
        sub="อัปโหลดไฟล์เล่มหลักสูตร (Word/PDF) AI อ่านและสกัดข้อมูลครบทุกหมวดของคู่มือหลักสูตร (10 ส่วน) ตรวจความสอดคล้องข้ามหมวด แล้วให้ยืนยันทีละส่วนก่อนบันทึก · POC นี้ทำ 4 ส่วน (โครงสร้าง PLO รายวิชา Mapping)"
      />
      <Steps current={0} />
      <div className="split">
        <section className="card pad stack">
          <div className="form-grid">
            <div className="field">
              <label>บันทึกเข้าหลักสูตร</label>
              <select className="inp" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">สร้างหลักสูตรใหม่จากเล่ม</option>
                <option value="pmt">วท.บ. เทคโนโลยีวัสดุพอลิเมอร์ (ปป.67)</option>
              </select>
            </div>
            <div className="field">
              <label>AI ที่ใช้อ่าน</label>
              <div className="seg">
                <button type="button" className={provider === "ollama" ? "on" : ""} onClick={() => setProvider("ollama")}>
                  Local AI · Gemma (server มศว)
                </button>
                <button
                  type="button"
                  className={provider === "gemini" ? "on" : ""}
                  disabled={!geminiOn}
                  title={geminiOn ? "" : "ยังไม่ได้ตั้งค่า API key"}
                  onClick={() => geminiOn && setProvider("gemini")}
                >
                  Cloud AI · Gemini {geminiOn ? "" : "(ปิด)"}
                </button>
                <button type="button" className={provider === "none" ? "on" : ""} onClick={() => setProvider("none")}>
                  อ่านด้วยกฎเท่านั้น (ไม่ใช้ AI)
                </button>
              </div>
            </div>
          </div>

          <div className="field">
            <label>ส่วนที่ AI จะสกัด (เรียงตามลำดับการนำเข้า)</label>
            <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 6 }}>
              {ORDER.map((k, i) => (
                <div key={k} className="row" style={{ flexWrap: "nowrap", opacity: POC_PARTS.has(k) ? 1 : 0.55 }}>
                  <span className="av" style={POC_PARTS.has(k) ? { background: "var(--red)", color: "#fff" } : {}}>{i + 1}</span>
                  <span>
                    <b style={{ fontWeight: 600 }}>{PART_LABELS[k][0]}</b>
                    <span className="small faint" style={{ display: "block" }}>
                      {PART_LABELS[k][1]} {POC_PARTS.has(k) ? "" : "· R1"}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <label
            className="drop"
            style={{ cursor: "pointer", borderColor: drag ? "var(--red)" : undefined }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
          >
            <Ic name="upload" size={30} />
            <b>ลากไฟล์เล่มหลักสูตรมาวางที่นี่</b>
            <span className="small muted">รองรับ .docx และ .pdf ขนาดไม่เกิน 50 MB</span>
            <span className="btn sm">เลือกไฟล์</span>
            <input ref={inputRef} type="file" hidden accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>

          {file && (
            <div className="between card pad" style={{ background: "var(--surface-2)" }}>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <Ic name="file" size={22} />
                <div>
                  <b>{file.name}</b>
                  <div className="small faint">{fmtBytes(file.size)}</div>
                </div>
              </div>
              {!canWrite && <Note kind="info">บทบาทของคุณดูผลการนำเข้าได้ แต่การอัปโหลด/แก้ไข/ยืนยันสงวนไว้สำหรับผู้ดูแลส่วนกลางและผู้ตรวจสอบระดับหลักสูตร</Note>}
              <button className="btn primary" onClick={start} disabled={busy || !canWrite}>
                <Ic name="ai" size={17} /> {busy ? "กำลังส่ง…" : "เริ่มอ่านด้วย AI"}
              </button>
            </div>
          )}
          {err && <Note kind="warn">{err}</Note>}
        </section>

        <section className="card pad stack">
          <div className="between">
            <h2 className="h2">ประวัติการนำเข้า</h2>
            {history.length > 0 && (
              <Link href="/import/history" className="btn xs">ดูทั้งหมด ({history.length})</Link>
            )}
          </div>
          {history.length === 0 && <div className="small faint">ยังไม่มี</div>}
          {history.slice(0, RECENT).map((h) => (
            <div
              key={h.id}
              className="between"
              style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", flexWrap: "nowrap" }}
            >
              <Link href={`/import/${h.id}`} style={{ minWidth: 0, color: "inherit", textDecoration: "none" }}>
                <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.filename}</div>
                <div className="small faint">
                  {fmtTime(h.created_at)} · {providerLabel(h.provider)} · ยืนยันแล้ว {h.confirmed_count}/{h.parts_total}
                </div>
              </Link>
              <div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
                <Pill kind={STATUS_TH[h.status][1]}>{STATUS_TH[h.status][0]}</Pill>
                {hasSummary(h) && (
                  <Link href={`/import/${h.id}/done`} className="btn xs" title="เวลา · LLM · ส่วนที่ยืนยัน">สรุป</Link>
                )}
              </div>
            </div>
          ))}
          {history.length > RECENT && (
            <div className="small faint">แสดง {RECENT} งานล่าสุดจาก {history.length} งาน · <Link href="/import/history">ดูทั้งหมด</Link></div>
          )}
          <Note kind="info">
            <b>AI ช่วยอะไรบ้าง</b>
            <br />สกัดข้อมูล — อ่านหมวด 3–4 ของเล่มแล้ววางลงฟิลด์ พร้อมความมั่นใจและเลขหน้าต้นฉบับทุกค่า
            <br />ตรวจความสอดคล้อง — หน่วยกิตรวม รหัสวิชาซ้ำ หน่วยกิตกลุ่มย่อย ด้วยกฎ ไม่ใช่ความเห็นของ AI
            <br />ชี้จุดที่เล่มขัดแย้งกันเอง — รายชื่อวิชากับคำอธิบายไม่ตรงกัน ระบบระบุหน้าทั้งสองจุด
          </Note>
        </section>
      </div>
    </>
  );
}
