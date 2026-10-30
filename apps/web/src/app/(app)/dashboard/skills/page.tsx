"use client";

// dash-skill (mock · US-M3-10): a term's assessment in the user's ขอบเขตข้อมูล: sections to
// assess, % of students fully assessed [สมมติ], waiting for confirmation, not started, the
// Skill Transcripts issued / ready / incomplete, progress per faculty (red under the target),
// the sections still open with แจ้งเตือน (an e-mail to the teachers, once a day).
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { skillsApi, type AssessStatus, type SkillDashboard } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { ASSESS_KIND } from "@/lib/skills";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, Kpi, KpiRow, useToast } from "@/components/kit";
import { SkillTermSelect, useSkillTerm } from "@/components/skills";

const ST: [AssessStatus, string, string][] = [["todo", "ยังไม่ประเมิน", "var(--line-2)"], ["doing", "กำลังประเมิน", "var(--gold)"], ["wait", "รอยืนยัน", "var(--info)"], ["ok", "ยืนยันแล้ว", "var(--ok)"]];

export default function SkillDashboardPage() {
  const { data: session } = useSession();
  const canRemind = canMenu(session?.user?.perms, "d3", "edit");
  const toast = useToast();
  const [terms, slug, setSlug, termErr] = useSkillTerm();
  const [d, setD] = useState<SkillDashboard | null>(null);
  const load = () => slug && skillsApi.dashboard(slug).then(setD).catch((e) => toast((e as Error).message, "err"));
  useEffect(() => { if (slug) skillsApi.dashboard(slug).then(setD).catch((e) => toast((e as Error).message, "err")); }, [slug, toast]);
  async function remind(code?: string, sec?: string) {
    try { const r = await skillsApi.remind(slug, code, sec); toast(r.sent ? `ส่งแจ้งเตือน ${r.sent} รายการ` : "ไม่มีรายการที่ต้องแจ้ง หรือวันนี้แจ้งแล้ว", r.sent ? "ok" : "err"); load(); } catch (e) { toast((e as Error).message, "err"); }
  }
  function exportCsv() {
    if (!d) return;
    const url = URL.createObjectURL(new Blob([toCsv(["คณะ", "รายวิชา-กลุ่ม", "ยืนยันแล้ว (%)", "นิสิตประเมินแล้ว (%)", "ต่ำกว่าเป้า"], d.units.map((u) => [u.faculty, u.sections, u.confirmed_pct, u.assessed_pct, u.below ? "ใช่" : ""]))], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `dashboard-skills-${slug}.csv` }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead crumb={["แดชบอร์ด"]} title="แดชบอร์ดการประเมิน Skill Transcript" sub="ติดตามการประเมิน Skill รายวิชา-กลุ่ม และการออกเอกสาร · เฉพาะขอบเขตข้อมูลของบัญชีนี้"
        actions={<>{terms && <SkillTermSelect terms={terms} slug={slug} onChange={setSlug} />}<button type="button" className="btn" disabled={!d} onClick={exportCsv}>ส่งออก CSV</button></>} />
      {termErr && <Note kind="warn">{termErr}</Note>}
      {d && (
        <>
          <KpiRow cols={5}>
            <Kpi label="รายวิชา-กลุ่มที่ต้องประเมิน" value={d.sections} sub="ตาม Skill Mapping ที่อนุมัติ" />
            <Kpi label="ประเมินครบแล้ว (นิสิต)" value={`${d.assessed_pct}%`} sub={`ของ ${d.students} คน-รายวิชา`} />
            <Kpi label="รอผู้สอนยืนยัน" value={d.status.wait} sub="รายวิชา-กลุ่ม" />
            <Kpi label="ยังไม่เริ่มประเมิน" value={d.status.todo} sub="รายวิชา-กลุ่ม" />
            <Kpi label="Skill Transcript ที่ออกแล้ว" value={d.transcripts.issued} sub={`พร้อมออก ${d.transcripts.ready} · ไม่ครบ ${d.transcripts.incomplete + d.transcripts.ethics} · ผู้สำเร็จการศึกษา ${d.graduates}`} />
          </KpiRow>
          <section className="card pad stack">
            <h2 className="h2">จำแนกตามคณะ/ส่วนงาน</h2>
            <span className="small faint">แดงเมื่อนิสิตประเมินแล้วต่ำกว่าเป้า {d.target_pct}%</span>
            <div className="tbl-wrap"><table className="tbl"><thead><tr><th>คณะ</th><th className="r">รายวิชา-กลุ่ม</th><th style={{ minWidth: 170 }}>สถานะ</th><th className="r">ยืนยันแล้ว</th><th className="r">นิสิตประเมินแล้ว</th></tr></thead>
              <tbody>{d.units.map((u) => <tr key={u.faculty}>
                <td style={u.below ? { color: "var(--red-ink, var(--red))", fontWeight: 600 } : undefined}>{u.faculty}</td><td className="r num">{u.sections}</td>
                <td><div className="bar lg" role="img" aria-label={ST.map(([k, l]) => `${l} ${u.status[k]}`).join(", ")}>{ST.filter(([k]) => u.status[k]).map(([k, l, c]) => <span key={k} title={`${l}: ${u.status[k]}`} style={{ width: `${(u.status[k] / u.sections) * 100}%`, background: c }} />)}</div></td>
                <td className="r num">{u.confirmed_pct}%</td><td className="r num" style={{ minWidth: 120 }}>{u.assessed_pct}%<Bar pct={u.assessed_pct} color={u.below ? "var(--red)" : "var(--ok)"} /></td></tr>)}
                {!d.units.length && <tr><td colSpan={5} className="empty">ไม่มีรายวิชาที่ต้องประเมินในภาคนี้</td></tr>}
              </tbody></table></div>
            <div className="row" style={{ gap: 10 }}>{ST.map(([k, l, c]) => <span key={k} className="small"><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: c, marginRight: 4 }} />{l}</span>)}</div>
          </section>
          <section className="card pad stack">
            <div className="between"><h2 className="h2">รายวิชาที่ยังไม่ยืนยันผล ({d.late.length}){d.late_days > 0 && <span className="small" style={{ color: "var(--red)" }}> · เลยกำหนดส่ง {d.late_days} วัน</span>}</h2>{canRemind && d.late.length > 0 && <button type="button" className="btn" onClick={() => remind()}>แจ้งเตือนทั้งหมด</button>}</div>
            <span className="small faint">เรียงจากยังไม่เริ่มประเมิน · แจ้งเตือนส่งอีเมลถึงผู้สอนของรายวิชานั้น ได้วันละครั้ง{d.deadline ? ` · กำหนดส่ง ${d.deadline}` : ""}</span>
            <div className="tbl-wrap"><table className="tbl"><thead><tr><th>รายวิชา</th><th>คณะ</th><th>สถานะ</th><th className="r">ประเมินแล้ว</th><th>ผู้สอน</th><th /></tr></thead>
              <tbody>{d.late.map((x) => <tr key={`${x.course_code}|${x.section}`}>
                <td><Link href={`/assess/${slug}/${encodeURIComponent(x.course_code)}/${encodeURIComponent(x.section)}`}><b>{x.course_code}</b></Link> กลุ่ม {x.section} <span className="small">{x.name_th}</span></td>
                <td className="small">{x.faculty}</td><td><Pill kind={ASSESS_KIND[x.status]}>{ST.find(([k]) => k === x.status)?.[1]}</Pill></td><td className="r num">{x.done}/{x.n}</td>
                <td className="small">{x.teachers.map((t) => t.name).join(", ")}</td>
                <td>{canRemind && x.teachers.length > 0 && <button type="button" className="btn xs" onClick={() => remind(x.course_code, x.section)}>แจ้งเตือน</button>}</td></tr>)}
                {!d.late.length && <tr><td colSpan={6} className="empty">ยืนยันผลครบทุกรายวิชาแล้ว</td></tr>}
              </tbody></table></div>
          </section>
          <Note kind="info">% ประเมินครบ = นิสิตที่ได้คะแนนครบทุก Skill ใน Mapping ÷ นิสิตทั้งหมดของรายวิชา-กลุ่ม [สมมติ]</Note>
        </>
      )}
    </>
  );
}
