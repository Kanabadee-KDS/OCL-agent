"use client";

// Markdown editor (US-M1-17 · FS-3f): the book as Markdown (whole, per chapter, the 10 parts)
// edited by hand, with a live preview. The original stays; the edit wins on read and the API
// keeps the previous text. A part with nothing extracted already holds a template to fill in.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Markdown, Note } from "@/components/ui";
import { Modal, useToast } from "@/components/kit";

export function MarkdownEditor({ jobId, path, onClose, onSaved }: { jobId: string; path: string; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [text, setText] = useState<string | null>(null);
  const [orig, setOrig] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.fileText(jobId, path).then((t) => { setText(t); setOrig(t); }).catch(() => setText("")); }, [jobId, path]);
  async function save() {
    if (text == null) return;
    setBusy(true);
    try { await api.saveMarkdown(jobId, path, text); toast(`บันทึก ${path} แล้ว`); onSaved(); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  return (
    <Modal open size="xl" title={`แก้ Markdown · ${path}`} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" disabled={busy || text == null || text === orig} onClick={save}>{busy ? "กำลังบันทึก…" : "บันทึก"}</button></>}>
      {text == null ? <div>กำลังโหลด…</div> : (
        <div className="stack">
          <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 12 }}>
            <textarea className="inp" aria-label={`Markdown ${path}`} spellCheck={false} style={{ height: 460, padding: 10, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12.5 }} value={text} onChange={(e) => setText(e.target.value)} />
            <div className="card pad" style={{ height: 460, overflow: "auto" }}><Markdown text={text} /></div>
          </div>
          <Note kind="info">ไฟล์ต้นฉบับยังอยู่ · ฉบับที่แก้ใช้แทนเมื่อเปิดอ่านและ Preview · ข้อความก่อนแก้เก็บในประวัติ · แก้ข้อความ Markdown ไม่เปลี่ยนข้อมูลในฟอร์มของส่วนนั้น</Note>
        </div>
      )}
    </Modal>
  );
}
