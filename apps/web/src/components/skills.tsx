"use client";

// Shared pieces of Skill Transcript (FS-5): the term picker, a skill's tag, the approve/return
// dialog, the history, the portfolio of one student (portfolio-detail · me) and the Skill
// Transcript document (transcript · my-transcript), printable to A4 with its QR code.
import { Fragment, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { fmtTime, skillsApi, type Portfolio, type SkillEvent, type SkillFlowStep, type TranscriptDoc } from "@/lib/api";
import { CATS, CAT_COLOR, CAT_EN, CAT_TH, fmt2, type Cat } from "@/lib/skills";
import { Note, Pill } from "@/components/ui";
import { Field, Kpi, KpiRow, Modal, Radar, Timeline, type Step } from "@/components/kit";

/** The terms of the SUPREME timetable (newest first) and the one chosen, kept for the session. */
export function useSkillTerm(): [string[] | null, string, (slug: string) => void, string | null] {
  const [terms, setTerms] = useState<string[] | null>(null);
  const [slug, setSlug] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    skillsApi.terms().then((t) => {
      setTerms(t);
      const kept = typeof window !== "undefined" ? window.sessionStorage.getItem("skill-term") : null;
      const slugs = t.map((x) => x.replace("/", "-"));
      setSlug(slugs.find((x) => x === kept) ?? slugs[0] ?? "");
    }).catch((e) => setErr(`โหลดภาคการศึกษาไม่ได้: ${(e as Error).message}`));
  }, []);
  const pick = (s: string) => { setSlug(s); try { window.sessionStorage.setItem("skill-term", s); } catch { /* private mode */ } };
  return [terms, slug, pick, err];
}

export function SkillTermSelect({ terms, slug, onChange }: { terms: string[]; slug: string; onChange: (s: string) => void }) {
  return (
    <select className="inp" style={{ maxWidth: 200 }} aria-label="ภาค/ปีการศึกษา" value={slug} onChange={(e) => onChange(e.target.value)}>
      {terms.map((t) => <option key={t} value={t.replace("/", "-")}>ภาค {t}</option>)}
    </select>
  );
}

export function SkillTag({ code, cat, title }: { code: string; cat?: Cat | string; title?: string }) {
  const c = CAT_COLOR[(cat ?? code.replace(/\d+$/, "")) as Cat] ?? "var(--fg-2)";
  return <span className="pill" title={title} style={{ background: "transparent", border: `1px solid ${c}`, color: c, fontWeight: 600 }}>{code}</span>;
}

export function CertifyModal({ what, onClose, onDone }: { what: string; onClose: () => void; onDone: (ok: boolean, note: string) => void }) {
  const [act, setAct] = useState<"ok" | "return">("ok");
  const [note, setNote] = useState("");
  return (
    <Modal open title={`อนุมัติ${what}`} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" disabled={act === "return" && !note.trim()} onClick={() => onDone(act === "ok", note)}>{act === "ok" ? "อนุมัติ" : "ส่งคืนแก้ไข"}</button></>}>
      <div className="stack">
        <div className="row" style={{ gap: 12 }}>
          <label className="check"><input type="radio" checked={act === "ok"} onChange={() => setAct("ok")} /> อนุมัติ</label>
          <label className="check"><input type="radio" checked={act === "return"} onChange={() => setAct("return")} /> ส่งคืนแก้ไข</label>
        </div>
        <Field label={act === "ok" ? "ความเห็น (ไม่บังคับ)" : "เหตุผล *"} full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}

const ACT_TH: Record<string, string> = { save: "บันทึก", submit: "ส่งอนุมัติ", approve: "อนุมัติ", return: "ส่งคืนแก้ไข", revise: "สร้างฉบับใหม่", confirm: "ยืนยันผล", reopen: "เปิดให้แก้", assign: "กำหนดผู้รับผิดชอบ", review: "ตรวจสอบ", sign: "ลงนาม" };

export function Events({ events }: { events: SkillEvent[] }) {
  if (!events.length) return null;
  return (
    <section className="card pad stack">
      <h2 className="h2">ประวัติ</h2>
      {events.slice(-10).reverse().map((e, i) => <div key={i} className="small">{fmtTime(e.ts)} · {e.by} · {ACT_TH[e.action] ?? e.action}{e.note ? ` · "${e.note}"` : ""}</div>)}
    </section>
  );
}

/** ร่าง → ส่ง → อนุมัติ, with the flow's own step names. */
export function ApprovalSteps({ steps, status }: { steps: SkillFlowStep[]; status: string }) {
  const tl: Step[] = [
    { title: "ร่าง", state: status === "none" || status === "draft" ? "cur" : "done" },
    { title: steps[0]?.position || "ส่ง", detail: steps[0]?.label, state: (status === "returned" ? "rej" : ["sent", "approved"].includes(status) ? "done" : undefined) as Step["state"] },
    { title: steps.at(-1)?.position || "คณะอนุมัติ", detail: steps.at(-1)?.label, state: (status === "approved" ? "done" : status === "sent" ? "cur" : undefined) as Step["state"] },
  ];
  return <Timeline steps={tl} />;
}

function catItems(cats: Record<string, number | null>) {
  return CATS.filter((c) => cats[c] != null).map((c) => [c, cats[c] as number] as const);
}

/** portfolio-detail and me (US-M3-07 09): averages, levels, radar, per term, sources. */
export function PortfolioView({ p, actions }: { p: Portfolio; actions?: ReactNode }) {
  const [open, setOpen] = useState<string | null>(null);
  const st = p.student;
  const rd = p.readiness;
  return (
    <>
      <section className="card pad stack">
        <div className="between">
          <div><h2 className="h2" style={{ margin: 0 }}>{st.name_th}</h2><div className="small faint">{st.sid} · {st.program_name ?? st.program} · {st.faculty} · เข้าศึกษา {st.entry_year} · {st.status}{st.advisor && <> · อาจารย์ที่ปรึกษา {st.advisor}</>}</div></div>
          <div className="row">{actions}</div>
        </div>
        {!p.curriculum && <Note kind="info">ยังไม่มีคู่มือหลักสูตรในระบบที่ตรงกับรหัสหลักสูตรของนิสิต จึงยังไม่มีชุด Skill ที่ต้องประเมิน</Note>}
        {p.curriculum && !p.set && <Note kind="info">หลักสูตร {p.curriculum.name_th} ยังไม่มีชุด Skill ที่อนุมัติแล้ว</Note>}
        {p.set && <div className="small">ชุด Skill ฉบับ {p.set.version}{p.set.cohort_from ? ` (รหัส ${p.set.cohort_from} ขึ้นไป)` : ""} · {p.set.skills.length} Skill · ประเมินแล้ว {p.skills.filter((s) => s.in_set && s.avg != null).length}</div>}
      </section>
      <KpiRow cols={5}>
        {CATS.map((c) => <Kpi key={c} label={<span style={{ color: CAT_COLOR[c] }}>{c} · {CAT_TH[c]}</span>} value={fmt2(p.cats[c])} />)}
        <Kpi label="ระดับรวม" value={p.level ?? "–"} sub={`เฉลี่ย ${fmt2(p.overall)}`} />
      </KpiRow>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,320px) minmax(0,1fr)", gap: 16, alignItems: "start" }}>
        <section className="card pad stack" style={{ alignItems: "center" }}>
          <h2 className="h2" style={{ alignSelf: "flex-start" }}>ภาพรวม 4 ด้าน</h2>
          {catItems(p.cats).length ? <Radar items={catItems(p.cats)} /> : <span className="small faint">ยังไม่มีผลที่ยืนยันแล้ว</span>}
          {rd.graduated && <Note kind={rd.ready ? "ok" : "warn"}>{rd.ready ? "พร้อมออก Skill Transcript" : `ยังออก Skill Transcript ไม่ได้: ${[!rd.has_set && "ไม่มีชุด Skill", rd.missing.length && `ยังไม่ประเมิน ${rd.missing.join(", ")}`, rd.ethics_u.length && `Ethics ไม่ผ่าน ${rd.ethics_u.join(", ")}`].filter(Boolean).join(" · ")}`}</Note>}
          <div className="small faint" style={{ alignSelf: "flex-start" }}>สถานที่ฝึกประสบการณ์: {p.placement ?? "ยังไม่มีข้อมูลจาก SUPREME"}</div>
        </section>
        <section className="card pad stack" style={{ minWidth: 0 }}>
          <h2 className="h2">คะแนนราย Skill</h2>
          <span className="small faint">คะแนน = ค่าเฉลี่ยทุกรายวิชาที่ยืนยันผลแล้ว (BR-M3-01) · Ethics ผ่าน (S) เมื่อ ≥ {p.ethics_pass.toFixed(2)}</span>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Skill</th><th className="r">คะแนน</th><th>ระดับ</th><th className="r">รายวิชา</th><th /></tr></thead>
              <tbody>
                {p.skills.map((s) => (
                  <Fragment key={s.code}>
                    <tr>
                      <td><SkillTag code={s.code} cat={s.cat} /> {s.name_th}{!s.in_set && <span className="small faint"> (นอกชุด)</span>}</td>
                      <td className="r num"><b>{fmt2(s.avg)}</b></td>
                      <td>{s.level ?? <span className="faint">ยังไม่ประเมิน</span>}{s.su && <> · <Pill kind={s.su === "S" ? "ok" : "red"}>{s.su}</Pill></>}</td>
                      <td className="r num">{s.n}</td>
                      <td>{s.sources.length > 0 && <button type="button" className="link-btn small" onClick={() => setOpen(open === s.code ? null : s.code)}>{open === s.code ? "ซ่อน" : "ที่มา"}</button>}</td>
                    </tr>
                    {open === s.code && <tr><td colSpan={5} className="small" style={{ background: "var(--surface-2)" }}>{s.sources.map((x) => `${x.course_code} กลุ่ม ${x.section} ภาค ${x.term}: ${x.score.toFixed(2)}`).join(" · ")} → ({s.sources.map((x) => x.score.toFixed(2)).join(" + ")}) / {s.sources.length} = {fmt2(s.avg)}</td></tr>}
                  </Fragment>
                ))}
                {!p.skills.length && <tr><td colSpan={5} className="empty">ยังไม่มี Skill</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <section className="card pad stack">
        <h2 className="h2">คะแนนสะสมรายภาค</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ภาค</th>{CATS.map((c) => <th key={c} className="r" style={{ color: CAT_COLOR[c] }}>{c}</th>)}</tr></thead>
            <tbody>
              {p.by_term.map((t) => <tr key={t.term}><td>{t.label} <span className="small faint">({t.term})</span></td>{CATS.map((c) => <td key={c} className="r num">{fmt2(t.cats[c])}</td>)}</tr>)}
              {!p.by_term.length && <tr><td colSpan={5} className="empty">ยังไม่มีผลที่ยืนยันแล้ว</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

/** The Skill Transcript (US-M3-08 · TOR 6.12.3–6.12.5): page 1 the scores, page 2 the definitions. */
export function TranscriptView({ doc }: { doc: TranscriptDoc }) {
  const d = doc.data;
  // the page's own address goes into the QR (the server is reached by a different name)
  const origin = useSyncExternalStore(() => () => {}, () => window.location.origin, () => "");
  const rows = CATS.map((c) => [c, d.skills.filter((s) => s.cat === c)] as const);
  return (
    <article className="book" aria-label="Skill Transcript">
      <table className="book-frame">
        <thead><tr><td><div className="book-run"><span>Skill Transcript · {d.student.sid}</span><span>{doc.draft ? "ฉบับร่าง · ยังไม่ลงนาม" : `เลขที่ ${doc.no}`}</span></div></td></tr></thead>
        <tbody><tr><td>
          <header className="book-title"><h1>Skill Transcript</h1><div>มหาวิทยาลัยศรีนครินทรวิโรฒ</div>{doc.draft && <div style={{ color: "#B42318", fontWeight: 700 }}>ฉบับร่าง · ยังไม่ลงนาม</div>}</header>
          <table>
            <tbody>
              <tr><th style={{ width: "28%" }}>ชื่อ-สกุล</th><td>{d.student.name_th}</td><th style={{ width: "18%" }}>รหัสนิสิต</th><td>{d.student.sid}</td></tr>
              <tr><th>หลักสูตร</th><td colSpan={3}>{d.student.program_name ?? d.student.program}</td></tr>
              <tr><th>คณะ</th><td>{d.student.faculty}</td><th>เข้า/สำเร็จ</th><td>{d.student.entry_year} / {d.student.graduated ?? "–"}</td></tr>
            </tbody>
          </table>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 220px", gap: 12, alignItems: "start" }}>
            <table>
              <thead><tr><th>Skill</th><th className="r">คะแนน</th><th>ระดับ</th></tr></thead>
              <tbody>
                {rows.map(([c, xs]) => xs.length > 0 && [
                  <tr key={c}><td colSpan={3}><b>{c} · {CAT_EN[c]}</b>{c === "E" && " (S/U)"} <span style={{ float: "right" }}>{fmt2(d.cats[c])}</span></td></tr>,
                  ...xs.map((s) => <tr key={s.code}><td className="sub">{s.code} {s.name_en ?? s.name_th}</td><td className="r">{c === "E" ? (s.su ?? "–") : fmt2(s.avg)}</td><td>{c === "E" ? (s.su === "S" ? "Satisfactory" : s.su === "U" ? "Unsatisfactory" : "–") : s.level ?? "–"}</td></tr>),
                ])}
              </tbody>
            </table>
            <div style={{ textAlign: "center" }}>
              {catItems(d.cats).length >= 3 && <Radar items={catItems(d.cats)} size={210} color="#9E1B2B" />}
              <div style={{ fontSize: 12 }}>ระดับรวม <b>{d.level ?? "–"}</b> ({fmt2(d.overall)})</div>
            </div>
          </div>
          <p style={{ fontSize: 12 }}>สถานที่ฝึกประสบการณ์: {d.placement ?? "–"}</p>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, marginTop: 18 }}>
            <div style={{ fontSize: 12 }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- an SVG drawn by the API */}
              {doc.no && origin && <img src={skillsApi.qrUrl(doc.no, origin)} alt={`QR ตรวจสอบเอกสาร ${doc.no}`} width={110} height={110} />}
              <div>{doc.no ? <>ตรวจสอบเอกสาร: {origin}/verify/{doc.no}</> : "QR สำหรับตรวจสอบจะแสดงเมื่อออกเอกสารแล้ว"}</div>
            </div>
            <div style={{ textAlign: "center", fontSize: 13 }}>
              {doc.signer ? <><div style={{ fontStyle: "italic" }}>ลงนามดิจิทัล{doc.signer.sample && " (ตัวอย่าง · ยังไม่มีผลทางกฎหมาย)"}</div><div>{doc.signer.name_th}</div><div>{doc.signer.position}</div><div>{doc.issued_at && fmtTime(doc.issued_at)}</div></> : <div className="empty">ยังไม่ลงนาม</div>}
            </div>
          </div>
          <section>
            <h2>นิยามทักษะ (Definitions)</h2>
            <table className="keep">
              <tbody>{d.skills.map((s) => <tr key={s.code}><td style={{ width: "22%" }}><b>{s.code}</b> {s.name_en ?? s.name_th}</td><td>{s.definition ?? "–"}</td></tr>)}</tbody>
            </table>
            <h3>เกณฑ์ระดับความเชี่ยวชาญ</h3>
            <table><tbody>{doc.levels.map((l) => <tr key={l.level}><td>{l.en} · {l.th}</td><td className="r">{l.min.toFixed(2)} – {l.max.toFixed(2)}</td></tr>)}</tbody></table>
          </section>
        </td></tr></tbody>
      </table>
    </article>
  );
}
