"use client";

// skill-map (mock · US-M3-04): per term and curriculum, which skills of its approved set each
// offered course assesses; courses not offered show apart and cannot be set; a module (ชุดวิชา)
// can take one set of skills for all its courses. Coverage shows skills no course assesses.
// Draft → ส่งอนุมัติ (flow skill_mapping) → only an approved mapping is assessed (BR-M3-06).
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { skillsApi, type SkillMapping } from "@/lib/api";
import { CATS, CAT_COLOR, CAT_EN, SET_KIND, coverage } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { Kpi, KpiRow, useToast } from "@/components/kit";
import { ApprovalSteps, CertifyModal, Events, SkillTag, SkillTermSelect, useSkillTerm } from "@/components/skills";

export default function SkillMappingPage() {
  const toast = useToast();
  const [terms, slug, setSlug, termErr] = useSkillTerm();
  const [curs, setCurs] = useState<{ id: number; name_th: string; faculty: string | null }[] | null>(null);
  const [cid, setCid] = useState<number | null>(null);
  const [d, setD] = useState<SkillMapping | null>(null);
  const [cells, setCells] = useState<Record<string, string[]>>({});
  const [cert, setCert] = useState(false);
  const fill = (x: SkillMapping) => { setD(x); setCells(Object.fromEntries(x.courses.filter((c) => c.skills.length).map((c) => [c.code, c.skills]))); };
  useEffect(() => {
    if (!slug) return;
    skillsApi.mapCurricula(slug).then((r) => { setCurs(r); setCid((x) => x ?? r[0]?.id ?? null); }).catch((e) => toast((e as Error).message, "err"));
  }, [slug, toast]);
  useEffect(() => { if (slug && cid) skillsApi.mapping(slug, cid).then(fill).catch((e) => toast((e as Error).message, "err")); }, [slug, cid, toast]);
  const skills = useMemo(() => d?.set?.skills ?? [], [d]);
  const cov = useMemo(() => (d ? coverage(d.courses, cells, skills) : null), [d, cells, skills]);
  const norm = (o: Record<string, string[]>) => JSON.stringify(Object.keys(o).sort().filter((k) => o[k].length).map((k) => [k, o[k]]));
  const dirty = !!d && norm(Object.fromEntries(d.courses.map((c) => [c.code, c.skills]))) !== norm(cells);
  const mine = d?.rights.courses;
  const editable = (code: string) => !!d?.can_edit && (!mine || mine.includes(code));
  const toggle = (code: string, s: string) => setCells((x) => { const cur = x[code] ?? []; const nx = cur.includes(s) ? cur.filter((y) => y !== s) : skills.filter((k) => k === s || cur.includes(k)); return { ...x, [code]: nx }; });
  const modules = useMemo(() => [...new Set((d?.courses ?? []).filter((c) => c.offered && c.module).map((c) => c.module as string))], [d]);
  function applyModule(m: string) {
    const live = (d?.courses ?? []).filter((c) => c.offered && c.module === m);
    const union = skills.filter((s) => live.some((c) => (cells[c.code] ?? []).includes(s)));
    setCells((x) => ({ ...x, ...Object.fromEntries(live.filter((c) => editable(c.code)).map((c) => [c.code, union])) }));
    toast(`ใช้ Skill ชุดเดียวกันทั้งชุดวิชา ${m} (${union.length} Skill)`);
  }
  async function run(fn: () => Promise<SkillMapping>, msg: string) {
    try { const x = await fn(); fill(x); toast(x.copied_from ? `${msg} จากภาค ${x.copied_from}${x.skipped?.length ? ` · ข้าม ${x.skipped.join(", ")} (ไม่เปิดสอน)` : ""}` : msg); } catch (e) { toast((e as Error).message, "err"); }
  }
  const live = (d?.courses ?? []).filter((c) => c.offered);
  const off = (d?.courses ?? []).filter((c) => !c.offered);
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ตั้งค่าการบันทึกข้อมูล"]} title="กำหนดรายวิชาประเมิน Skill (Skill Mapping)"
        sub="เลือกภาคและหลักสูตร แล้วกำหนดว่าแต่ละ Skill ประเมินในรายวิชาใด คะแนน Skill ของนิสิตคำนวณจากค่าเฉลี่ยทุกรายวิชาที่ประเมิน"
        actions={d && <>
          {d.can_edit && <button type="button" className="btn" onClick={() => run(() => skillsApi.copyMapping(slug, d.curriculum.id), "คัดลอก Mapping แล้ว")}>คัดลอกจากภาคก่อน</button>}
          {d.can_edit && <button type="button" className="btn" disabled={!dirty} onClick={() => run(() => skillsApi.saveMapping(slug, d.curriculum.id, cells), "บันทึกร่างแล้ว")}>{dirty ? "บันทึกร่าง" : "บันทึกแล้ว"}</button>}
          {d.can_submit && <button type="button" className="btn primary" onClick={() => run(async () => { if (dirty) await skillsApi.saveMapping(slug, d.curriculum.id, cells); return skillsApi.submitMapping(slug, d.curriculum.id); }, "ส่ง Mapping เข้าสู่การอนุมัติแล้ว")}>ส่งอนุมัติ</button>}
          {d.can_certify && <button type="button" className="btn primary" onClick={() => setCert(true)}>อนุมัติ / ส่งคืน</button>}
        </>} />
      {termErr && <Note kind="warn">{termErr}</Note>}
      <div className="row" style={{ gap: 8 }}>
        {terms && <SkillTermSelect terms={terms} slug={slug} onChange={setSlug} />}
        <select className="inp" style={{ flex: "1 1 360px" }} aria-label="หลักสูตร" value={cid ?? ""} onChange={(e) => setCid(Number(e.target.value))}>
          {(curs ?? []).map((c) => <option key={c.id} value={c.id}>{c.name_th} · {c.faculty}</option>)}
        </select>
        {d && <Pill kind={SET_KIND[d.status]}>{d.status_th}</Pill>}
        {d?.set && <span className="small faint">ชุด Skill ฉบับ {d.set.version}{d.set.cohort_from ? ` · รหัส ${d.set.cohort_from}+` : ""}</span>}
      </div>
      {curs && !curs.length && <Note kind="info">ไม่มีหลักสูตรในขอบเขตข้อมูลของบัญชีนี้</Note>}
      {d && !d.set && <Note kind="warn">หลักสูตรนี้ยังไม่มีชุด Skill ที่อนุมัติแล้ว · <Link href={`/skills/curricula/${d.curriculum.id}`}>ไปที่กำหนด Skill ตามหลักสูตร</Link></Note>}
      {d?.status === "returned" && <Note kind="warn">ส่งคืนแก้ไข: {[...d.events].reverse().find((e) => e.action === "return")?.note}</Note>}
      {mine && <Note kind="info">บัญชีนี้กำหนดได้เฉพาะรายวิชา {mine.join(", ")}</Note>}
      {d && d.set && cov && (
        <>
          <KpiRow>
            <Kpi label="รายวิชาที่เปิดสอนในหลักสูตร" value={live.length} sub={`ไม่เปิดสอนในภาค ${off.length}`} />
            <Kpi label="กำหนดแล้ว" value={cov.mapped} sub="รายวิชาที่มี Skill อย่างน้อย 1" />
            <Kpi label="จุดประเมิน" value={cov.points} sub="รายวิชา × Skill" />
            <Kpi label="Skill ที่ยังไม่มีรายวิชา" value={cov.gaps.length} sub={cov.gaps.join(", ") || "ครบทุก Skill"} />
          </KpiRow>
          {modules.length > 0 && d.can_edit && <div className="row" style={{ gap: 6 }}><span className="small">ใช้ Skill ชุดเดียวกันทั้งชุดวิชา:</span>{modules.map((m) => <button key={m} type="button" className="btn xs" onClick={() => applyModule(m)}>{m}</button>)}</div>}
          <section className="card" style={{ overflow: "hidden" }}>
            <div className="tbl-wrap" style={{ border: 0 }}>
              <table className="tbl" style={{ fontSize: 13 }}>
                <thead><tr><th>Skill</th>{live.map((c) => <th key={c.code} className="c" title={c.name_th}><div style={{ fontWeight: 400, opacity: 0.8 }}>{c.module ?? ""}</div>{c.code}</th>)}<th className="c">ประเมินจาก</th></tr></thead>
                <tbody>
                  {CATS.map((k) => {
                    const rows = d.skills.filter((s) => s.cat === k);
                    if (!rows.length) return null;
                    return [
                      <tr key={k}><td colSpan={live.length + 2} style={{ background: "var(--surface-2)", fontWeight: 600, color: CAT_COLOR[k] }}>{k} · {CAT_EN[k]}</td></tr>,
                      ...rows.map((s) => {
                        const n = live.filter((c) => (cells[c.code] ?? []).includes(s.code)).length;
                        return (
                          <tr key={s.code}>
                            <td style={{ minWidth: 220 }}><SkillTag code={s.code} cat={s.cat} /> <span className="small">{s.name_th}</span></td>
                            {live.map((c) => {
                              const on = (cells[c.code] ?? []).includes(s.code);
                              return <td key={c.code} className="c"><button type="button" aria-pressed={on} aria-label={`${s.code} ${c.code}`} disabled={!editable(c.code)} onClick={() => toggle(c.code, s.code)}
                                style={{ width: 28, height: 28, borderRadius: 6, border: `1px solid ${on ? CAT_COLOR[k] : "var(--line)"}`, background: on ? CAT_COLOR[k] : "transparent", color: "#fff", cursor: editable(c.code) ? "pointer" : "default" }}>{on ? "✓" : ""}</button></td>;
                            })}
                            <td className="c">{n ? <Pill>{n} วิชา</Pill> : <Pill kind="red">ยังไม่กำหนด</Pill>}</td>
                          </tr>
                        );
                      }),
                    ];
                  })}
                </tbody>
              </table>
            </div>
          </section>
          {off.length > 0 && <Note kind="info">รายวิชาของหลักสูตรที่ไม่เปิดสอนในภาคนี้ (กำหนดไม่ได้): {off.map((c) => c.code).join(", ")}</Note>}
          <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) 280px", gap: 16, alignItems: "start" }}>
            <Events events={d.events} />
            <section className="card pad stack"><h2 className="h2">ขั้นตอนอนุมัติ</h2><ApprovalSteps steps={d.steps} status={d.status} /></section>
          </div>
        </>
      )}
      {cert && d && <CertifyModal what="Skill Mapping" onClose={() => setCert(false)} onDone={(ok, note) => { setCert(false); run(() => skillsApi.certifyMapping(slug, d.curriculum.id, ok, note), ok ? "อนุมัติ Skill Mapping แล้ว" : "ส่งคืนแก้ไขแล้ว"); }} />}
    </>
  );
}
