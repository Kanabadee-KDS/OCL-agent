"use client";

// assess (mock · US-M3-05): the course sections a teacher assesses in the term, the skills
// from the approved mapping (BR-M3-06), students assessed / all, the deadline and the status
// ยังไม่ประเมิน / กำลังประเมิน / รอยืนยัน / ยืนยันแล้ว; by course or by curriculum.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { skillsApi, type AssessList, type AssessRow, type AssessStatus } from "@/lib/api";
import { ASSESS_ACT, ASSESS_KIND } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, DataTable, Filters, SearchBox, Seg, Tabs, type Column } from "@/components/kit";
import { SkillTag, SkillTermSelect, useSkillTerm } from "@/components/skills";

export default function AssessPage() {
  const [terms, slug, setSlug, termErr] = useSkillTerm();
  const [d, setD] = useState<AssessList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState<"all" | AssessStatus>("all");
  const [view, setView] = useState<"course" | "cur">("course");
  const [q, setQ] = useState("");
  useEffect(() => { if (slug) skillsApi.sections(slug).then(setD).catch((e) => setErr((e as Error).message)); }, [slug]);
  const items = useMemo(() => d?.items ?? [], [d]);
  const cnt = (s: AssessStatus) => items.filter((i) => i.status === s).length;
  const rows = useMemo(() => items.filter((i) => f === "all" || i.status === f), [items, f]);
  const href = (i: AssessRow) => `/assess/${slug}/${encodeURIComponent(i.course_code)}/${encodeURIComponent(i.section)}`;
  const columns: Column<AssessRow>[] = [
    { key: "c", label: "รายวิชา / กลุ่มเรียน", sort: (i) => i.course_code, render: (i) => <><Link href={href(i)}><b>{i.course_code} {i.name_th}</b></Link><div className="small faint">กลุ่ม {i.section} · {i.curricula.map((c) => c.name_th).join(", ")}{i.deadline ? ` · กำหนดส่ง ${i.deadline}` : ""}</div></> },
    { key: "sk", label: "Skill ที่ต้องประเมิน", render: (i) => <div className="row" style={{ gap: 4 }}>{i.skills.map((s) => <SkillTag key={s} code={s} />)}</div> },
    { key: "n", label: "นิสิต", align: "right", render: (i) => <span className="num">{i.n}</span> },
    { key: "p", label: "ความคืบหน้า", width: 170, render: (i) => <><div className="small muted num">{i.done} / {i.n} คน</div><Bar pct={i.n ? (i.done / i.n) * 100 : 0} color={i.done === i.n && i.n ? "var(--ok)" : "var(--red)"} /></> },
    { key: "st", label: "สถานะ", sort: (i) => i.status, render: (i) => <Pill kind={ASSESS_KIND[i.status]}>{d?.statuses[i.status]}</Pill> },
    { key: "go", label: "", render: (i) => <Link className={`btn xs${i.status === "ok" ? "" : " primary"}`} href={href(i)}>{ASSESS_ACT[i.status]}</Link> },
  ];
  const byCur = useMemo(() => {
    const m = new Map<string, AssessRow[]>();
    for (const i of rows) for (const c of i.curricula) m.set(c.name_th, [...(m.get(c.name_th) ?? []), i]);
    return [...m.entries()];
  }, [rows]);
  return (
    <>
      <PageHead crumb={["Skill Transcript", "บันทึกการประเมิน Skill"]} title="บันทึกประเมิน Skill"
        sub="รายวิชาที่ต้องประเมินทักษะในภาค · Skill ที่ต้องประเมินมาจาก Skill Mapping ที่อนุมัติแล้วของหลักสูตร"
        actions={terms && <SkillTermSelect terms={terms} slug={slug} onChange={setSlug} />} />
      {(termErr || err) && <Note kind="warn">{termErr || err}</Note>}
      <div className="between">
        <Tabs items={[["course", "ตามรายวิชา"], ["cur", "ตามหลักสูตร"]] as const} value={view} onChange={setView} />
        <Seg items={[["all", `ทั้งหมด · ${items.length}`], ["todo", `ยังไม่ประเมิน · ${cnt("todo")}`], ["doing", `กำลังประเมิน · ${cnt("doing")}`], ["wait", `รอยืนยัน · ${cnt("wait")}`], ["ok", `ยืนยันแล้ว · ${cnt("ok")}`]] as const} value={f} onChange={setF} />
      </div>
      {view === "course"
        ? <DataTable rows={rows} columns={columns} rowKey={(i) => `${i.course_code}|${i.section}`} search={q} unit="กลุ่มเรียน" searchText={(i) => `${i.course_code} ${i.name_th ?? ""}`}
            empty={d ? "ไม่มีรายวิชาที่ต้องประเมิน (ต้องมี Skill Mapping ที่อนุมัติแล้ว)" : "กำลังโหลด…"} toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นรหัสหรือชื่อรายวิชา" /></Filters>} />
        : byCur.map(([name, rs]) => (
            <section key={name} className="card pad stack">
              <h2 className="h2">{name}</h2>
              {rs.map((i) => <Link key={`${i.course_code}|${i.section}`} href={href(i)} className="between" style={{ borderBottom: "1px solid var(--line)", padding: "8px 0" }}><span>{i.course_code} {i.name_th} · กลุ่ม {i.section}</span><span className="row" style={{ gap: 8 }}><span className="small num">{i.done}/{i.n}</span><Pill kind={ASSESS_KIND[i.status]}>{d?.statuses[i.status]}</Pill></span></Link>)}
            </section>
          ))}
      <Note kind="info">รายชื่อนิสิตและกลุ่มเรียนดึงจากข้อมูลการลงทะเบียนใน SUPREME (ข้อมูลตัวอย่างจนกว่าจะได้ API จริง) ผลที่ &quot;ยืนยันแล้ว&quot; นำไปประมวลผลใน Skill Portfolio</Note>
    </>
  );
}
