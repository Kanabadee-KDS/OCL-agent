"use client";

// จับคู่ข้อมูลกับระบบ (US-M1-13): หมวด 0.2 teachers → HURIS or the register of external
// persons, หมวด 4 courses → the central database (BR-09). The API only proposes; each row is
// stored when a person ticks it and confirms (no match is saved without a person).
import { useEffect, useState } from "react";
import { matchApi, type MatchData } from "@/lib/api";
import { Note, Pill } from "@/components/ui";
import { Modal, Tabs, useToast } from "@/components/kit";

const C_STATE: Record<string, [string, "ok" | "warn" | "info" | "grey" | "red"]> = {
  linked: ["ผูกแล้ว", "ok"], same: ["ตรงฐานกลาง → ใช้ Version ล่าสุด", "info"], changed: ["เนื้อหาต่าง → Version ถัดไป", "warn"],
  new: ["รหัสใหม่ → Version 1", "warn"], no_code: ["ไม่มีรหัส", "red"],
};

export function MatchDialog({ draftId, onClose, onSaved }: { draftId: string; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [m, setM] = useState<MatchData | null>(null);
  const [tab, setTab] = useState<"t" | "c">("t");
  const [pick, setPick] = useState<Record<number, string>>({}); // index -> "pid:SWU…" | "xid:X…"
  const [quals, setQuals] = useState<Record<number, "huris" | "book">>({});
  // a name 1-2 letters off HURIS (OCR-2a2): the book's spelling stays unless a person picks HURIS's
  const [spell, setSpell] = useState<Record<number, "huris" | "book">>({});
  const [accept, setAccept] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    matchApi.get(draftId).then((x) => {
      setM(x);
      // a single HURIS hit is proposed ticked; several wait for a person to choose
      setPick(Object.fromEntries(x.teachers.filter((t) => t.state === "one").map((t) => [t.index, `pid:${t.candidates![0].pid}`])));
    }).catch((e) => toast((e as Error).message, "err"));
  }, [draftId, toast]);

  async function save() {
    setBusy(true);
    try {
      const r = tab === "t"
        ? await matchApi.teachers(draftId, Object.entries(pick).filter(([, v]) => v).map(([i, v]) => {
          const [kind, id] = v.split(":");
          return { index: Number(i), ...(kind === "pid" ? { pid: id, quals: quals[Number(i)] ?? "huris", name: spell[Number(i)] ?? "book" } : { xid: id }) };
        }))
        : await matchApi.courses(draftId, Object.entries(accept).filter(([, v]) => v).map(([i]) => ({ index: Number(i), accept: true })));
      setM(r); setPick({}); setAccept({}); setSpell({});
      toast(`บันทึกการจับคู่ ${r.matched ?? 0} รายการแล้ว`);
      onSaved();
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }

  const open = (m?.teachers ?? []).filter((t) => t.state !== "linked");
  const openC = (m?.courses ?? []).filter((c) => c.state !== "linked");
  const can = tab === "t" ? m?.editable["0"] : m?.editable["4"];
  const n = tab === "t" ? Object.values(pick).filter(Boolean).length : Object.values(accept).filter(Boolean).length;
  return (
    <Modal open size="xl" title="จับคู่ข้อมูลในเล่มกับระบบ" onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ปิด</button>{can && <button type="button" className="btn primary" disabled={busy || !n} onClick={save}>{busy ? "กำลังบันทึก…" : `ยืนยันการจับคู่ที่เลือก (${n})`}</button>}</>}>
      {!m ? <div>กำลังโหลด…</div> : (
        <div className="stack">
          <Tabs label="จับคู่" value={tab} onChange={setTab} items={[["t", `อาจารย์ → HURIS (ยังไม่ผูก ${open.length})`], ["c", `รายวิชา → ฐานข้อมูลกลาง (ยังไม่ผูก ${openC.length})`]] as const} />
          {!can && <Note kind="info">สถานะนี้แก้{tab === "t" ? "หมวด 0" : "รายวิชาในหมวด 4"}ไม่ได้ ดูผลการจับคู่ได้อย่างเดียว</Note>}
          {tab === "t" ? (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>อาจารย์ในเล่ม</th><th>เสนอจากระบบ</th><th>คุณวุฒิ (BR-05)</th></tr></thead>
                <tbody>
                  {open.map((t) => {
                    const chosen = (t.candidates ?? []).find((c) => pick[t.index] === `pid:${c.pid}`);
                    return (
                      <tr key={t.index}>
                        <td>{t.name}<div className="small faint">{t.rank} · {t.highest_level ?? "ไม่ระบุคุณวุฒิ"}</div></td>
                        <td>
                          <select className="inp" aria-label={`จับคู่ ${t.name}`} disabled={!can} value={pick[t.index] ?? ""} onChange={(e) => setPick((x) => ({ ...x, [t.index]: e.target.value }))}>
                            <option value="">{t.state === "none" ? "— ไม่พบใน HURIS และทะเบียน (เพิ่มที่บริหารบุคคลภายนอก) —" : "— ยังไม่จับคู่ —"}</option>
                            {(t.candidates ?? []).map((c) => <option key={c.pid} value={`pid:${c.pid}`}>HURIS {c.pid} · {c.name} · {c.faculty}</option>)}
                            {(t.externals ?? []).map((x) => <option key={x.xid} value={`xid:${x.xid}`}>บุคคลภายนอก {x.xid} · {x.name} · {x.org}</option>)}
                          </select>
                          {t.state === "many" && <span className="small faint">ชื่อตรงหลายคน ให้เลือก</span>}
                          {t.state === "near" && <span className="small faint">ไม่พบชื่อที่ตรงทุกตัวอักษร มีชื่อใกล้เคียงใน HURIS ให้เลือก</span>}
                          {chosen?.near && (
                            <div className="stack" style={{ gap: 2, marginTop: 4 }}>
                              <span className="small"><Pill kind="warn">สะกดต่าง</Pill> เล่ม: {t.name} · HURIS: {chosen.huris_name}</span>
                              <label className="small"><input type="radio" disabled={!can} checked={(spell[t.index] ?? "book") === "book"} onChange={() => setSpell((x) => ({ ...x, [t.index]: "book" }))} /> คงตัวสะกดตามเล่ม</label>
                              <label className="small"><input type="radio" disabled={!can} checked={spell[t.index] === "huris"} onChange={() => setSpell((x) => ({ ...x, [t.index]: "huris" }))} /> ใช้ตัวสะกดของ HURIS</label>
                            </div>
                          )}
                        </td>
                        <td className="small">
                          {chosen?.differs ? (
                            <div className="stack" style={{ gap: 2 }}>
                              <span><Pill kind="warn">ต่างกัน</Pill> เล่ม: {t.highest_level} · HURIS: {chosen.highest_level}</span>
                              <label><input type="radio" disabled={!can} checked={(quals[t.index] ?? "huris") === "huris"} onChange={() => setQuals((x) => ({ ...x, [t.index]: "huris" }))} /> ใช้ตาม HURIS</label>
                              <label><input type="radio" disabled={!can} checked={quals[t.index] === "book"} onChange={() => setQuals((x) => ({ ...x, [t.index]: "book" }))} /> ยืนยันตามเล่ม (แจ้ง HURIS ปรับปรุง)</label>
                            </div>
                          ) : chosen ? "ตรงกัน" : "–"}
                        </td>
                      </tr>
                    );
                  })}
                  {!open.length && <tr><td colSpan={3} className="small faint">อาจารย์ทุกคนผูกกับ HURIS หรือทะเบียนบุคคลภายนอกแล้ว</td></tr>}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th /><th>รายวิชาในเล่ม</th><th>ผลเทียบฐานกลาง (BR-09)</th><th>ฐานกลางตอนนี้</th></tr></thead>
                <tbody>
                  {openC.map((c) => (
                    <tr key={c.index}>
                      <td><input type="checkbox" aria-label={`ยืนยัน ${c.code_th}`} disabled={!can || c.state === "no_code"} checked={!!accept[c.index]} onChange={(e) => setAccept((x) => ({ ...x, [c.index]: e.target.checked }))} /></td>
                      <td className="small"><b>{c.code_th}</b> {c.name_th} · {c.credit_text}</td>
                      <td><Pill kind={C_STATE[c.state][1]}>{C_STATE[c.state][0]}</Pill>{c.version && c.state !== "no_code" && <span className="small num"> → {c.code_th}-{c.version}</span>}</td>
                      <td className="small">{c.central ? `v${c.central.version} · ${c.central.name_th} · ${c.central.credit_text ?? ""}` : "ไม่มี"}</td>
                    </tr>
                  ))}
                  {!openC.length && <tr><td colSpan={4} className="small faint">รายวิชาทุกวิชาผูกกับฐานข้อมูลกลางแล้ว</td></tr>}
                </tbody>
              </table>
              {can && openC.length > 0 && <button type="button" className="btn xs" style={{ marginTop: 8 }} onClick={() => setAccept(Object.fromEntries(openC.filter((c) => c.state !== "no_code").map((c) => [c.index, true])))}>เลือกทั้งหมด</button>}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
