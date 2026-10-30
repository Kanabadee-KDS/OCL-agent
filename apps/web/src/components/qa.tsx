"use client";

// Shared pieces of the curriculum assessment (FS-6): the round picker, a result pill, and the
// report R10 of one curriculum (qa-preview · US-M4-08), printable to A4.
import { useEffect, useState } from "react";
import { fmtTime, qaApi, type QaDetail, type QaRound } from "@/lib/api";
import { RESULT_KIND, RESULT_TH, pickRound } from "@/lib/qa";
import { Pill } from "@/components/ui";

/** The rounds (newest first) and the one chosen, kept for the session. */
export function useRound(): [QaRound[] | null, number | null, (id: number) => void, string | null, () => void] {
  const [rounds, setRounds] = useState<QaRound[] | null>(null);
  const [rid, setRid] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => qaApi.rounds().then((r) => {
    setRounds(r);
    let kept: number | null = null;
    try { kept = Number(window.sessionStorage.getItem("qa-round")) || null; } catch { /* private mode */ }
    setRid((x) => pickRound(r, x ?? kept));
  }).catch((e) => setErr(`โหลดรอบการประเมินไม่ได้: ${(e as Error).message}`));
  useEffect(() => { load(); }, []);
  const pick = (id: number) => { setRid(id); try { window.sessionStorage.setItem("qa-round", String(id)); } catch { /* private mode */ } };
  return [rounds, rid, pick, err, load];
}

export function RoundSelect({ rounds, rid, onChange }: { rounds: QaRound[]; rid: number | null; onChange: (id: number) => void }) {
  return (
    <select className="inp" style={{ maxWidth: 320 }} aria-label="รอบการประเมิน" value={rid ?? ""} onChange={(e) => onChange(Number(e.target.value))}>
      {rounds.map((r) => <option key={r.id} value={r.id}>{r.name} · {r.status_th}</option>)}
    </select>
  );
}

export function ResultPill({ r }: { r: string | null | undefined }) {
  const k = r ?? "none";
  return <Pill kind={RESULT_KIND[k] ?? "grey"}>{RESULT_TH[k] ?? k}</Pill>;
}

/** R10 (BRD 05): ฉบับร่าง until every item has a result, with the two signatures. */
export function R10({ d }: { d: QaDetail & { complete: boolean } }) {
  const ok = d.final === "pass";
  return (
    <article className="book" aria-label={`รายงานผลการตรวจสอบ ${d.curriculum.name_th}`} style={{ marginBottom: 16 }}>
      <table className="book-frame">
        <thead><tr><td><div className="book-run"><span>รายงานผลการตรวจสอบหลักสูตร (R10) · {d.round.name}</span><span>{d.complete ? "ฉบับสมบูรณ์" : "ฉบับร่าง"}</span></div></td></tr></thead>
        <tbody><tr><td>
          <header className="book-title">
            <h1>รายงานผลการประเมินองค์ประกอบที่ 1 ตัวบ่งชี้ 1.1</h1>
            <div>{d.curriculum.name_th} · {d.curriculum.faculty}</div>
            <div>เกณฑ์มาตรฐานหลักสูตร พ.ศ. {d.set_year} · ระดับ{d.curriculum.level}</div>
            {!d.complete && <div style={{ color: "#B42318", fontWeight: 700 }}>ฉบับร่าง · ยังประเมินไม่ครบทุกข้อ</div>}
          </header>
          <table>
            <thead><tr><th style={{ width: 40 }}>ข้อ</th><th>เกณฑ์</th><th style={{ width: 110 }}>ผลการประเมิน</th><th>หมายเหตุ</th></tr></thead>
            <tbody>
              {d.items.map((i) => (
                <tr key={i.no}>
                  <td className="r">{i.no}</td>
                  <td>{i.title}</td>
                  <td>{!i.applies ? "ไม่เกี่ยวข้อง" : RESULT_TH[i.result?.result ?? "none"]}</td>
                  <td>{[i.note, i.result?.note].filter(Boolean).join(" · ") || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p><b>สรุปผล:</b> {d.final === "pending" ? "รอพิจารณา" : ok ? "ได้มาตรฐาน" : "ไม่ได้มาตรฐาน"}</p>
          <p style={{ fontSize: 12 }}>ข้อมูลหลักฐาน ณ วันที่ HURIS {d.dates.huris ?? "–"} · SUPREME {d.dates.supreme ?? "–"} · คู่มือหลักสูตร {fmtTime(d.dates.curriculum)} · ผู้ประเมิน {d.evaluators.map((e) => e.name).join(", ") || "–"}</p>
          <div style={{ display: "flex", justifyContent: "space-around", marginTop: 40, textAlign: "center", fontSize: 13 }}>
            <div>ลงชื่อ ....................................................<div>ประธานอาจารย์ผู้รับผิดชอบหลักสูตร</div></div>
            <div>ลงชื่อ ....................................................<div>คณบดี{d.curriculum.faculty ?? ""}</div></div>
          </div>
        </td></tr></tbody>
      </table>
    </article>
  );
}
