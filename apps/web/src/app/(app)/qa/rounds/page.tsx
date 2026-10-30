"use client";

// qa-rounds (mock · US-M4-01): a round = academic year, dates, the curricula in it, the set of
// criteria of each (from its คู่มือ: BR-M4-05) and its evaluators (group ผู้ประเมินหลักสูตร).
// Copy from an earlier round; open one at a time [สมมติ]; close = locked for good, still
// searchable (BR-M4-04). The criteria are copied into the round when it opens.
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { qaApi, type QaCandidate, type QaEvaluator, type QaRound, type QaRoundDetail } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { DATA_KIND, ROUND_KIND } from "@/lib/qa";
import { Note, PageHead, Pill } from "@/components/ui";
import { Field, Modal, useToast } from "@/components/kit";
import { RoundSelect, useRound } from "@/components/qa";

type Prog = { curriculum_id: number; set_year: number; evaluators: string[] };

export default function QaRoundsPage() {
  const { data: session } = useSession();
  const canEdit = canMenu(session?.user?.perms, "q1", "edit");
  const toast = useToast();
  const [rounds, rid, setRid, err, reload] = useRound();
  const [d, setD] = useState<QaRoundDetail | null>(null);
  const [edit, setEdit] = useState<QaRoundDetail | "new" | null>(null);
  const load = (id: number) => qaApi.round(id).then(setD).catch((e) => toast((e as Error).message, "err"));
  useEffect(() => { if (rid) qaApi.round(rid).then(setD).catch((e) => toast((e as Error).message, "err")); }, [rid, toast]);
  async function act(fn: () => Promise<QaRoundDetail>, msg: string) {
    try { const r = await fn(); toast(msg); reload(); setRid(r.id); load(r.id); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตั้งค่าการประเมิน"]} title="รอบการประเมิน"
        sub="กำหนดปีการศึกษา ช่วงวันที่ประเมิน เกณฑ์ที่ใช้ และหลักสูตรในแต่ละรอบ เมื่อตรวจประเมินครบทุกหลักสูตร ระบบล็อกข้อมูลไม่ให้แก้ไขและเก็บไว้สืบค้นย้อนหลัง"
        actions={canEdit && <button type="button" className="btn primary" onClick={() => setEdit("new")}>เพิ่มรอบการประเมิน</button>} />
      {err && <Note kind="warn">{err}</Note>}
      <section className="card">
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>รอบการประเมิน</th><th>ช่วงวันที่ประเมิน</th><th>เกณฑ์ที่ใช้</th><th className="r">หลักสูตร</th><th className="r">ยืนยันข้อมูลแล้ว</th><th>สถานะ</th><th /></tr></thead>
          <tbody>
            {(rounds ?? []).map((r: QaRound) => (
              <tr key={r.id} style={r.id === rid ? { background: "var(--surface-2)" } : undefined}>
                <td><button type="button" className="link-btn" onClick={() => setRid(r.id)}><b>{r.name}</b></button></td>
                <td className="small">{r.starts_on ?? "–"} – {r.ends_on ?? "–"}</td>
                <td className="small">{r.sets.map((y) => `พ.ศ. ${y}`).join(", ") || "–"}</td>
                <td className="r num">{r.programs}</td><td className="r num">{r.confirmed}</td>
                <td><Pill kind={ROUND_KIND[r.status]}>{r.status_th}</Pill></td>
                <td className="r" style={{ whiteSpace: "nowrap" }}>{canEdit && <>
                  <button type="button" className="btn xs" onClick={() => act(() => qaApi.copyRound(r.id), "คัดลอกเป็นรอบใหม่ (ร่าง) แล้ว")}>คัดลอก</button>{" "}
                  {r.status !== "closed" && <button type="button" className="btn xs" onClick={() => qaApi.round(r.id).then(setEdit)}>แก้ไข</button>}{" "}
                  {r.status === "draft" && <button type="button" className="btn xs primary" onClick={() => act(() => qaApi.openRound(r.id), "เปิดใช้งานรอบแล้ว")}>เปิดใช้งาน</button>}
                  {r.status === "open" && <button type="button" className="btn xs" onClick={() => { if (window.confirm("ปิดรอบแล้วข้อมูลทั้งหมดจะถูกล็อก แก้ไขไม่ได้อีก")) act(() => qaApi.closeRound(r.id), "ปิดรอบและล็อกข้อมูลแล้ว"); }}>ปิดรอบ</button>}
                </>}</td>
              </tr>
            ))}
            {rounds && !rounds.length && <tr><td colSpan={7} className="empty">ยังไม่มีรอบการประเมิน</td></tr>}
          </tbody></table></div>
      </section>
      {d && (
        <section className="card pad stack">
          <div className="between"><h2 className="h2">หลักสูตรใน{d.name}</h2>{rounds && <RoundSelect rounds={rounds} rid={rid} onChange={setRid} />}</div>
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>หลักสูตร</th><th>ระดับ</th><th>เกณฑ์</th><th>ผู้ประเมิน</th><th>สถานะข้อมูล</th></tr></thead>
            <tbody>{d.items.map((i) => <tr key={i.curriculum_id}><td>{i.name_th}<div className="small faint">{i.faculty}</div></td><td className="small">{i.level}</td><td className="small">พ.ศ. {i.set_year}</td>
              <td className="small">{i.evaluators.map((e) => e.name).join(", ") || <span className="faint">ยังไม่มอบหมาย</span>}</td>
              <td><Pill kind={DATA_KIND[i.status]}>{({ none: "ยังไม่บันทึก", doing: "อยู่ระหว่างบันทึก", sent: "ส่งยืนยันแล้ว", confirmed: "ยืนยันข้อมูลแล้ว" })[i.status]}</Pill></td></tr>)}
              {!d.items.length && <tr><td colSpan={5} className="empty">ยังไม่มีหลักสูตรในรอบ</td></tr>}
            </tbody></table></div>
        </section>
      )}
      {edit && <RoundModal round={edit === "new" ? null : edit} onClose={() => setEdit(null)} onSaved={(r) => { setEdit(null); toast("บันทึกรอบการประเมินแล้ว"); reload(); setRid(r.id); load(r.id); }} />}
    </>
  );
}

function RoundModal({ round, onClose, onSaved }: { round: QaRoundDetail | null; onClose: () => void; onSaved: (r: QaRoundDetail) => void }) {
  const toast = useToast();
  const [cands, setCands] = useState<QaCandidate[] | null>(null);
  const [evs, setEvs] = useState<QaEvaluator[]>([]);
  const [year, setYear] = useState(String(round?.year ?? new Date().getFullYear() + 543));
  const [name, setName] = useState(round?.name ?? "");
  const [from, setFrom] = useState(round?.starts_on ?? "");
  const [to, setTo] = useState(round?.ends_on ?? "");
  const [progs, setProgs] = useState<Record<number, Prog>>(() => Object.fromEntries((round?.items ?? []).map((i) => [i.curriculum_id, { curriculum_id: i.curriculum_id, set_year: i.set_year, evaluators: i.evaluators.map((e) => e.email) }])));
  useEffect(() => {
    qaApi.candidates().then((c) => { setCands(c); if (!round) setProgs(Object.fromEntries(c.map((x) => [x.id, { curriculum_id: x.id, set_year: x.set_year, evaluators: [] }]))); }).catch((e) => toast((e as Error).message, "err"));
    qaApi.evaluators().then(setEvs).catch(() => setEvs([]));
  }, [round, toast]);
  const n = useMemo(() => Object.keys(progs).length, [progs]);
  const set = (id: number, patch: Partial<Prog>) => setProgs((x) => ({ ...x, [id]: { ...x[id], ...patch } }));
  async function save() {
    try { onSaved(await qaApi.saveRound(round?.id ?? null, { year: Number(year), name: name || undefined, starts_on: from || null, ends_on: to || null, programs: Object.values(progs) })); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <Modal open size="xl" title={round ? `แก้ไข ${round.name}` : "เพิ่มรอบการประเมิน"} onClose={onClose}
      foot={<><span className="small muted" style={{ marginRight: "auto" }}>{n} หลักสูตร</span><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" onClick={save}>บันทึก</button></>}>
      <div className="stack">
        <div className="form-grid">
          <Field label="ปีการศึกษา (พ.ศ.) *">{(id) => <input id={id} className="inp num" value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, "").slice(0, 4))} />}</Field>
          <Field label="ชื่อรอบ">{(id) => <input id={id} className="inp" placeholder={`รอบการประเมิน ปีการศึกษา ${year}`} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <Field label="เริ่มประเมิน">{(id) => <input id={id} type="date" className="inp" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
          <Field label="สิ้นสุด">{(id) => <input id={id} type="date" className="inp" value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
        </div>
        <b>หลักสูตรในรอบ</b>
        <span className="small faint">เกณฑ์ตั้งต้นจากฟิลด์ &quot;เกณฑ์มาตรฐานหลักสูตร&quot; ในคู่มือ (BR-M4-05) · ผู้ประเมินเลือกจากบัญชีกลุ่มผู้ประเมินหลักสูตร (ภายใน/ภายนอกที่เชิญ)</span>
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ใช้งาน</th><th>หลักสูตร</th><th>เกณฑ์</th><th>ผู้ประเมิน</th></tr></thead>
          <tbody>{(cands ?? []).map((c) => {
            const p = progs[c.id];
            return (
              <tr key={c.id} style={{ verticalAlign: "top" }}>
                <td><input type="checkbox" aria-label={`ใช้ ${c.name_th}`} checked={!!p} onChange={(e) => setProgs((x) => { const y = { ...x }; if (e.target.checked) y[c.id] = { curriculum_id: c.id, set_year: c.set_year, evaluators: [] }; else delete y[c.id]; return y; })} style={{ width: 18, height: 18 }} /></td>
                <td>{c.name_th}<div className="small faint">{c.level} · {c.faculty} · {c.standard ?? "ไม่ระบุเกณฑ์ในคู่มือ"}</div></td>
                <td>{p && <select className="inp" aria-label={`เกณฑ์ ${c.name_th}`} value={p.set_year} onChange={(e) => set(c.id, { set_year: Number(e.target.value) })}>{[2548, 2558, 2565].map((y) => <option key={y} value={y}>พ.ศ. {y}</option>)}</select>}</td>
                <td>{p && <div className="stack" style={{ gap: 2 }}>{evs.map((e) => <label key={e.email} className="check small"><input type="checkbox" checked={p.evaluators.includes(e.email)} onChange={(ev) => set(c.id, { evaluators: ev.target.checked ? [...p.evaluators, e.email] : p.evaluators.filter((x) => x !== e.email) })} /> {e.name || e.email}{e.kind === "external" ? " (ภายนอก)" : ""}</label>)}{!evs.length && <span className="small faint">ยังไม่มีบัญชีผู้ประเมิน (เพิ่มที่หน้าผู้ใช้งาน)</span>}</div>}</td>
              </tr>
            );
          })}</tbody></table></div>
      </div>
    </Modal>
  );
}
