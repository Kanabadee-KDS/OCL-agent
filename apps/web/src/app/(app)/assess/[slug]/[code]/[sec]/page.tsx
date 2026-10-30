"use client";

// assess-form (mock · US-M3-06): the students of the section (SUPREME) × the skills to assess,
// a score 0–5 each with the rubric beside, "ให้คะแนนเท่ากันทั้งกลุ่ม", the Excel form to download
// and import, บันทึกร่าง and ยืนยันผลการประเมิน (then it counts in the portfolio and is locked;
// central may reopen it with a reason).
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { skillsApi, type AssessForm } from "@/lib/api";
import { ASSESS_KIND, completeCount, levelOf, parseScore } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Field, Modal, useToast } from "@/components/kit";
import { Events, SkillTag } from "@/components/skills";

type Grid = Record<string, Record<string, string>>;

export default function AssessFormPage() {
  const { slug, code, sec } = useParams<{ slug: string; code: string; sec: string }>();
  const c = decodeURIComponent(code), s = decodeURIComponent(sec);
  const toast = useToast();
  const [d, setD] = useState<AssessForm | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [grid, setGrid] = useState<Grid>({});
  const [rub, setRub] = useState<string | null>(null);
  const [same, setSame] = useState<Record<string, string>>({});
  const [reopen, setReopen] = useState<string | null>(null);
  const fill = (x: AssessForm) => {
    setD(x);
    setGrid(Object.fromEntries(x.students.map((st) => [st.sid, Object.fromEntries(x.skills.map((k) => [k, x.scores[st.sid]?.[k] != null ? String(x.scores[st.sid][k]) : ""]))])));
    setRub((r) => r ?? x.skills[0] ?? null);
  };
  useEffect(() => { skillsApi.section(slug, c, s).then(fill).catch((e) => setErr((e as Error).message)); }, [slug, c, s]);
  const parsed = useMemo(() => Object.fromEntries(Object.entries(grid).map(([sid, row]) => [sid, Object.fromEntries(Object.entries(row).map(([k, v]) => [k, parseScore(v)]))])), [grid]);
  const bad = Object.values(parsed).some((row) => Object.values(row).some((v) => v !== null && Number.isNaN(v)));
  const done = d ? completeCount(d.students.map((x) => x.sid), d.skills, parsed as Record<string, Record<string, number | null>>) : 0;
  const dirty = !!d && d.students.some((st) => d.skills.some((k) => (d.scores[st.sid]?.[k] ?? null) !== parsed[st.sid]?.[k]));
  async function run(fn: () => Promise<AssessForm>, msg: string) {
    try { fill(await fn()); toast(msg); } catch (e) { toast((e as Error).message, "err"); }
  }
  const save = () => skillsApi.saveScores(slug, c, s, parsed as Record<string, Record<string, number | null>>);
  if (err) return <><BackLink href="/assess">กลับไปรายการรายวิชา</BackLink><Note kind="warn">{err}</Note></>;
  if (!d) return <div className="card pad">กำลังโหลด…</div>;
  const ro = !d.can_edit;
  const rs = d.skill_rows.find((x) => x.code === rub);
  return (
    <>
      <BackLink href="/assess">กลับไปรายการรายวิชา</BackLink>
      <PageHead crumb={["Skill Transcript", "บันทึกประเมิน Skill"]} title={`${d.course_code} ${d.name_th ?? ""} · กลุ่ม ${d.section}`}
        sub={<>ภาค {d.term} · นิสิต {d.n} คน · ประเมินครบแล้ว {done} / {d.n} คน · <Pill kind={ASSESS_KIND[d.status]}>{({ todo: "ยังไม่ประเมิน", doing: "กำลังประเมิน", wait: "รอยืนยัน", ok: "ยืนยันแล้ว" })[d.status]}</Pill>{d.deadline ? ` · กำหนดส่ง ${d.deadline}` : ""}</>}
        actions={<>
          <a className="btn" href={skillsApi.formUrl(slug, c, s)}>แบบฟอร์ม Excel</a>
          {!ro && <label className="btn" style={{ cursor: "pointer" }}>นำเข้า Excel<input type="file" accept=".xlsx" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) run(() => skillsApi.importScores(slug, c, s, f), `นำเข้าคะแนนแล้ว`); }} /></label>}
          {!ro && <button type="button" className="btn" disabled={!dirty || bad} onClick={() => run(save, "บันทึกร่างแล้ว")}>บันทึกร่าง</button>}
          {!ro && <button type="button" className="btn primary" disabled={bad || done < d.n} onClick={() => run(async () => { if (dirty) await save(); return skillsApi.confirm(slug, c, s); }, "ยืนยันผลการประเมินแล้ว")}>ยืนยันผลการประเมิน</button>}
          {d.can_reopen && <button type="button" className="btn" onClick={() => setReopen("")}>เปิดให้แก้</button>}
        </>} />
      {d.status === "ok" && <Note kind="ok">ยืนยันผลแล้ว{d.confirmed_by ? ` โดย ${d.confirmed_by}` : ""} · ผลนำไปใช้ใน Skill Portfolio แล้ว หากต้องแก้ไขให้ติดต่อผู้ดูแลส่วนกลางเพื่อเปิดสิทธิ์</Note>}
      {!d.mine && !ro && <Note kind="info">บัญชีนี้ไม่ใช่ผู้สอนของกลุ่มนี้ แก้ได้ในฐานะส่วนกลาง</Note>}
      {bad && <Note kind="warn">มีคะแนนที่ไม่ถูกต้อง (ต้องเป็นตัวเลข 0–5)</Note>}
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) 300px", gap: 16, alignItems: "start" }}>
        <section className="card" style={{ minWidth: 0 }}>
          <div className="tbl-wrap" style={{ border: 0 }}>
            <table className="tbl">
              <thead>
                <tr><th>นิสิต</th>{d.skills.map((k) => <th key={k} className="c"><button type="button" className="link-btn" onClick={() => setRub(k)}><SkillTag code={k} /></button></th>)}<th>ระดับ</th></tr>
                {!ro && <tr><td className="small faint">ให้คะแนนเท่ากันทั้งกลุ่ม</td>{d.skills.map((k) => <td key={k} className="c"><div className="row" style={{ gap: 2, flexWrap: "nowrap" }}><input className="inp num" style={{ width: 56, height: 30 }} aria-label={`คะแนนเท่ากันทั้งกลุ่ม ${k}`} value={same[k] ?? ""} onChange={(e) => setSame((x) => ({ ...x, [k]: e.target.value }))} /><button type="button" className="btn xs" onClick={() => { const v = same[k] ?? ""; setGrid((g) => Object.fromEntries(Object.entries(g).map(([sid, row]) => [sid, { ...row, [k]: v }]))); }}>ใส่</button></div></td>)}<td /></tr>}
              </thead>
              <tbody>
                {d.students.map((st) => {
                  const row = parsed[st.sid] ?? {};
                  const vals = Object.values(row).filter((v): v is number => v !== null && !Number.isNaN(v));
                  const lv = vals.length === d.skills.length ? levelOf(vals.reduce((a, b) => a + b, 0) / vals.length, d.levels) : null;
                  return (
                    <tr key={st.sid}>
                      <td><b>{st.name_th}</b><div className="small faint">{st.sid}</div></td>
                      {d.skills.map((k) => <td key={k} className="c"><input className="inp num" style={{ width: 64, height: 32, borderColor: Number.isNaN(row[k]) ? "var(--red)" : undefined }} aria-label={`${st.sid} ${k}`} disabled={ro} value={grid[st.sid]?.[k] ?? ""} onChange={(e) => setGrid((g) => ({ ...g, [st.sid]: { ...g[st.sid], [k]: e.target.value } }))} /></td>)}
                      <td className="small">{lv?.en ?? "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
        <aside className="card pad stack">
          <h2 className="h2">Rubric {rs && <SkillTag code={rs.code} cat={rs.cat} />}</h2>
          {rs ? <><b>{rs.name_th}</b><span className="small faint">{rs.definition}</span>
            {d.levels.map((l, i) => <div key={l.level} className="small"><b>{l.level} · {l.en}</b> ({l.min.toFixed(2)}–{l.max.toFixed(2)})<div>{rs.rubric[i] || "–"}</div></div>)}</> : <span className="small faint">เลือก Skill ที่หัวตาราง</span>}
        </aside>
      </div>
      <Events events={d.events} />
      {reopen !== null && (
        <Modal open title="เปิดให้แก้ผลการประเมิน" onClose={() => setReopen(null)} foot={<><button type="button" className="btn" onClick={() => setReopen(null)}>ยกเลิก</button><button type="button" className="btn primary" disabled={!reopen.trim()} onClick={() => { const n = reopen; setReopen(null); run(() => skillsApi.reopen(slug, c, s, n), "เปิดให้แก้แล้ว"); }}>เปิดให้แก้</button></>}>
          <Field label="เหตุผล *" full>{(id) => <textarea id={id} className="inp" rows={3} style={{ height: "auto", padding: 8 }} value={reopen} onChange={(e) => setReopen(e.target.value)} />}</Field>
        </Modal>
      )}
    </>
  );
}
