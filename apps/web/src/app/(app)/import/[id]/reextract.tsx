"use client";

// สกัดใหม่ (US-M1-12 · FS-3e): the whole book or chosen parts, with a reading method. The book
// is not read again; the parts extracted again lose their edits and must be confirmed again.
import { useEffect, useState } from "react";
import { api, PART_LABELS, type Job } from "@/lib/api";
import { Note } from "@/components/ui";
import { Field, Modal, useToast } from "@/components/kit";

export function ReextractDialog({ job, current, onClose, onStarted }: { job: Job; current: string; onClose: () => void; onStarted: (j: Job) => void }) {
  const toast = useToast();
  const parts = job.parts ?? Object.keys(PART_LABELS);
  const [pick, setPick] = useState<string[]>(parts.includes(current) ? [current] : []);
  const [provider, setProvider] = useState(job.provider ?? "ollama");
  const [gemini, setGemini] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.health().then((h) => setGemini(Boolean(h.gemini_configured))).catch(() => setGemini(false)); }, []);
  const confirmed = pick.filter((k) => job.confirmed?.[k]);

  async function go() {
    setBusy(true);
    try { onStarted(await api.reextract(job.id, pick.length === parts.length ? null : pick, provider)); toast(`เริ่มสกัดใหม่ ${pick.length} ส่วน`); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  return (
    <Modal open size="lg" title="สกัดใหม่" onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" disabled={busy || !pick.length} onClick={go}>เริ่มสกัดใหม่ ({pick.length} ส่วน)</button></>}>
      <div className="stack">
        <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn xs" onClick={() => setPick(parts)}>ทั้งเล่ม</button>
          <button type="button" className="btn xs" onClick={() => setPick(parts.includes(current) ? [current] : [])}>เฉพาะส่วนที่เปิดอยู่</button>
          <button type="button" className="btn xs" onClick={() => setPick([])}>ล้าง</button>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 6 }}>
          {parts.map((k, i) => (
            <label key={k} className="row" style={{ gap: 6 }}>
              <input type="checkbox" checked={pick.includes(k)} onChange={(e) => setPick((x) => (e.target.checked ? [...x, k] : x.filter((y) => y !== k)))} />
              {i + 1}. {PART_LABELS[k]?.[0] ?? k}{job.confirmed?.[k] ? " (ยืนยันแล้ว)" : ""}
            </label>
          ))}
        </div>
        <Field label="วิธีอ่าน">{(id) => (
          <select id={id} className="inp" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="ollama">Local AI (server มศว)</option>
            <option value="gemini" disabled={!gemini}>Cloud AI{gemini ? "" : " (ยังไม่ได้ตั้งค่า)"}</option>
            <option value="none">อ่านด้วยกฎอย่างเดียว</option>
          </select>
        )}</Field>
        <Note kind="warn">ส่วนที่สกัดใหม่จะกลับเป็นค่าที่สกัดได้ การแก้ไขของส่วนนั้นหายและต้องยืนยันใหม่ (ประวัติการแก้ยังเก็บไว้){confirmed.length ? ` · ส่วนที่ยืนยันแล้วในรายการ: ${confirmed.length} ส่วน` : ""} · ส่วนอื่นคงเดิม · ไม่อ่านไฟล์เล่มซ้ำ</Note>
      </div>
    </Modal>
  );
}
