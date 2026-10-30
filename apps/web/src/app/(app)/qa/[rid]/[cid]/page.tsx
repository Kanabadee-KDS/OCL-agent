"use client";

// qa-check-detail (mock · US-M4-04 05 06): each item of the curriculum's set, its evidence from
// the คู่มือ, HURIS and the SUPREME timetable with the date of the data (read-only, BR-M4-02),
// what the system computes from it (FS-6 Q2 ก), the recorder's note, and the evaluator's
// result. Recorder: บันทึก → ส่งยืนยันข้อมูล · confirmer: ยืนยัน (locks) / ส่งคืนพร้อมเหตุผล ·
// evaluator: ผ่าน / ไม่ผ่าน / รอพิจารณา per item, or ส่งคืนผู้บันทึก with a reason.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fmtTime, qaApi, type QaDetail, type QaResult } from "@/lib/api";
import { DATA_KIND } from "@/lib/qa";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Field, Modal, useToast } from "@/components/kit";
import { ResultPill } from "@/components/qa";

const ACT: Record<string, string> = { save: "บันทึก", send: "ส่งยืนยันข้อมูล", confirm: "ยืนยันข้อมูล", return: "ส่งคืนแก้ไข", evaluate: "บันทึกผลประเมิน", "eval-return": "ผู้ประเมินส่งคืน", assign: "กำหนดผู้บันทึก" };

export default function QaDetailPage() {
  const { rid, cid } = useParams<{ rid: string; cid: string }>();
  const r = Number(rid), c = Number(cid);
  const toast = useToast();
  const [d, setD] = useState<QaDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [res, setRes] = useState<Record<string, { result: QaResult | ""; note: string }>>({});
  const [ask, setAsk] = useState<null | "return" | "eval-return">(null);
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const fill = (x: QaDetail) => {
    setD(x);
    setNotes(Object.fromEntries(x.items.map((i) => [String(i.no), i.note])));
    setRes(Object.fromEntries(x.items.filter((i) => i.applies).map((i) => [String(i.no), { result: i.result?.result ?? "", note: i.result?.note ?? "" }])));
  };
  useEffect(() => { qaApi.detail(r, c).then(fill).catch((e) => setErr((e as Error).message)); }, [r, c]);
  const dirtyNotes = useMemo(() => !!d && d.items.some((i) => (notes[String(i.no)] ?? "") !== i.note), [d, notes]);
  const changed = useMemo(() => Object.fromEntries(Object.entries(res).filter(([n, v]) => v.result && (v.result !== d?.items.find((i) => String(i.no) === n)?.result?.result || v.note !== (d?.items.find((i) => String(i.no) === n)?.result?.note ?? ""))) as [string, { result: QaResult; note: string }][]), [res, d]);
  async function run(fn: () => Promise<QaDetail>, msg: string) {
    setBusy(true); // one request at a time: a second save must not overtake the first
    try { fill(await fn()); toast(msg); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  if (err) return <><BackLink href="/qa">กลับไปรายการ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const lastReturn = [...d.events].reverse().find((e) => e.action === "return" || e.action === "eval-return");
  return (
    <>
      <BackLink href="/qa">กลับไปรายการหลักสูตร</BackLink>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตรวจสอบข้อมูลองค์ประกอบที่ 1"]} title={d.curriculum.name_th}
        sub={<>{d.round.name} · เกณฑ์ พ.ศ. {d.set_year} · {d.curriculum.level} · <Pill kind={DATA_KIND[d.status]}>{d.status_th}</Pill> · ผลประเมิน <ResultPill r={d.final} /></>}
        actions={<>
          <Link className="btn" href={`/qa/${r}/preview?cid=${c}`}>Preview</Link>
          {d.can_note && <button type="button" className="btn" disabled={busy || !dirtyNotes} onClick={() => run(() => qaApi.saveNotes(r, c, notes), "บันทึกแล้ว")}>{dirtyNotes ? "บันทึก" : "บันทึกแล้ว"}</button>}
          {d.can_note && <button type="button" className="btn primary" disabled={busy} onClick={() => run(async () => { if (dirtyNotes) await qaApi.saveNotes(r, c, notes); return qaApi.send(r, c); }, "ส่งยืนยันข้อมูลแล้ว")}>ส่งยืนยันข้อมูล</button>}
          {d.can_confirm && <><button type="button" className="btn" onClick={() => { setAsk("return"); setWhy(""); }}>ส่งคืนแก้ไข</button><button type="button" className="btn primary" disabled={busy} onClick={() => run(() => qaApi.confirm(r, c, true, ""), "ยืนยันข้อมูลแล้ว ส่งต่อผู้ประเมิน")}>ยืนยันข้อมูล</button></>}
          {d.can_evaluate && <><button type="button" className="btn" onClick={() => { setAsk("eval-return"); setWhy(""); }}>ส่งคืนผู้บันทึก</button><button type="button" className="btn primary" disabled={busy || !Object.keys(changed).length} onClick={() => run(() => qaApi.evaluate(r, c, changed), "บันทึกผลประเมินแล้ว")}>บันทึกผลประเมิน</button></>}
        </>} />
      {d.round.status === "closed" && <Note kind="info">รอบนี้ล็อกข้อมูลแล้ว ดูได้อย่างเดียว</Note>}
      {!d.complete && <Note kind="warn">ยังไม่ได้กำหนดผู้บันทึกและผู้ยืนยันครบ จึงยังเปิดให้บันทึกไม่ได้</Note>}
      {d.status === "doing" && lastReturn && <Note kind="warn">{lastReturn.action === "return" ? "ผู้ยืนยัน" : "ผู้ประเมิน"}ส่งคืน: {lastReturn.note}</Note>}
      {!d.can_note && !d.can_confirm && !d.can_evaluate && d.round.status !== "closed" && <Note kind="info">บัญชีนี้ดูได้อย่างเดียวในขั้นนี้ (BR-M4-03)</Note>}
      <div className="small faint">ข้อมูลหลักฐาน ณ วันที่ · HURIS {d.dates.huris ?? "–"} · SUPREME {d.dates.supreme ?? "–"} · คู่มือหลักสูตรแก้ล่าสุด {fmtTime(d.dates.curriculum)} · ผู้บันทึก {d.recorders.map((p) => p.name).join(", ") || "–"} · ผู้ยืนยัน {d.confirmer?.name ?? "–"} · ผู้ประเมิน {d.evaluators.map((e) => e.name).join(", ") || "–"}</div>
      {d.items.map((i) => {
        const n = String(i.no);
        return (
          <section key={n} className="card pad stack" style={{ opacity: i.applies ? 1 : 0.6 }}>
            <div className="between"><h2 className="h2" style={{ margin: 0 }}>ข้อ {i.no} {i.title}</h2>{i.applies ? <ResultPill r={i.result?.result} /> : <Pill>ไม่เกี่ยวข้อง</Pill>}</div>
            <span className="small faint">{i.detail}</span>
            <div className="row" style={{ gap: 4 }}>{i.sources.map((s) => <Pill key={s}>{s}</Pill>)}</div>
            {i.applies && (
              <>
                <div className="note info" style={{ display: "flex", gap: 8, alignItems: "center" }}><b>ผลตามเกณฑ์จากข้อมูล:</b> <ResultPill r={i.evidence.result} /> <span>{i.evidence.text}</span></div>
                {i.evidence.rows && i.evidence.rows.length > 0 && (
                  <div className="tbl-wrap"><table className="tbl"><thead><tr><th>อาจารย์</th><th>คุณวุฒิสูงสุด</th><th>ตำแหน่ง</th><th className="r">ผลงาน 5 ปี</th><th>ผลตามเกณฑ์</th></tr></thead>
                    <tbody>{i.evidence.rows.map((x, k) => <tr key={k}><td>{x.name}<div className="small faint">{x.pid ?? "ยังไม่จับคู่ HURIS"}</div></td><td className="small">{x.degree}</td><td className="small">{x.rank}</td><td className="r num">{x.works ?? "–"}</td><td><ResultPill r={x.result} /></td></tr>)}</tbody></table></div>
                )}
                <Field label="หมายเหตุผู้บันทึก" full>{(id) => <textarea id={id} className="inp" rows={2} style={{ height: "auto", padding: 8 }} disabled={!d.can_note} value={notes[n] ?? ""} onChange={(e) => setNotes((x) => ({ ...x, [n]: e.target.value }))} />}</Field>
                {(d.can_evaluate || i.result) && (
                  <div className="row" style={{ gap: 8, alignItems: "center" }}>
                    <b>ผลการประเมิน</b>
                    {(Object.keys(d.results) as QaResult[]).map((k) => <label key={k} className="check"><input type="radio" name={`r-${n}`} disabled={!d.can_evaluate} checked={res[n]?.result === k} onChange={() => setRes((x) => ({ ...x, [n]: { ...x[n], result: k } }))} /> {d.results[k]}</label>)}
                    <input className="inp" style={{ flex: 1, minWidth: 200 }} aria-label={`หมายเหตุผู้ประเมิน ข้อ ${n}`} placeholder="หมายเหตุผู้ประเมิน" disabled={!d.can_evaluate} value={res[n]?.note ?? ""} onChange={(e) => setRes((x) => ({ ...x, [n]: { ...x[n], note: e.target.value } }))} />
                    {i.result && <span className="small faint">{i.result.by} · {i.result.at}</span>}
                  </div>
                )}
              </>
            )}
          </section>
        );
      })}
      {d.events.length > 0 && <section className="card pad stack"><h2 className="h2">ประวัติ</h2>{d.events.slice(-10).reverse().map((e, k) => <div key={k} className="small">{fmtTime(e.ts)} · {e.by} · {ACT[e.action] ?? e.action}{e.note ? ` · "${e.note}"` : ""}</div>)}</section>}
      {ask && (
        <Modal open title={ask === "return" ? "ส่งคืนแก้ไข" : "ส่งคืนผู้บันทึก"} onClose={() => setAsk(null)}
          foot={<><button type="button" className="btn" onClick={() => setAsk(null)}>ยกเลิก</button><button type="button" className="btn primary" disabled={!why.trim()} onClick={() => { const a = ask; setAsk(null); run(() => (a === "return" ? qaApi.confirm(r, c, false, why) : qaApi.giveBack(r, c, why)), "ส่งคืนแล้ว"); }}>ส่งคืน</button></>}>
          <Field label="เหตุผล *" full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={why} onChange={(e) => setWhy(e.target.value)} />}</Field>
        </Modal>
      )}
    </>
  );
}
