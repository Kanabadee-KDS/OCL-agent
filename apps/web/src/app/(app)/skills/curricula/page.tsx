"use client";

// skill-cur (mock · US-M3-03): every curriculum's skill set at a glance: GS/SS/E/C counts,
// how many are its own, the status (ยังไม่กำหนด / ร่าง / รออนุมัติ / อนุมัติแล้ว).
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { skillsApi, type SkillSetsOverview } from "@/lib/api";
import { CATS, CAT_COLOR, SET_KIND } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, Kpi, KpiRow, SearchBox, SelectFilter, type Column } from "@/components/kit";

type Item = SkillSetsOverview["items"][number];

export default function SkillSetsPage() {
  const [d, setD] = useState<SkillSetsOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [fac, setFac] = useState("");
  const [st, setSt] = useState("");
  useEffect(() => { skillsApi.sets().then(setD).catch((e) => setErr((e as Error).message)); }, []);
  const facs = useMemo(() => [...new Set((d?.items ?? []).map((i) => i.faculty).filter(Boolean) as string[])].sort(), [d]);
  const columns: Column<Item>[] = [
    { key: "name", label: "หลักสูตร", sort: (i) => i.name_th, render: (i) => <><Link href={`/skills/curricula/${i.id}`}><b>{i.name_th}</b></Link><div className="small faint">{i.faculty}</div></> },
    ...CATS.map((c) => ({ key: c, label: <span style={{ color: CAT_COLOR[c] }}>{c}</span>, align: "right" as const, render: (i: Item) => <span className="num">{i.counts[c] || "–"}</span> })),
    { key: "own", label: "ที่มา", render: (i) => i.status === "none" ? <span className="faint">—</span> : <span className="small">{i.only_core ? "เฉพาะแกนกลาง" : `แกนกลาง + ${i.own} Skill`}</span> },
    { key: "ver", label: "ฉบับ", render: (i) => <span className="small">{i.version ? `${i.version}${i.cohort_from ? ` · รหัส ${i.cohort_from}+` : ""}` : "—"}</span> },
    { key: "st", label: "สถานะ", sort: (i) => i.status, render: (i) => <Pill kind={SET_KIND[i.status]}>{d?.statuses[i.status]}</Pill> },
    { key: "go", label: "", render: (i) => <Link className="btn xs" href={`/skills/curricula/${i.id}`}>เปิด</Link> },
  ];
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ตั้งค่าการบันทึกข้อมูล"]} title="กำหนด Skill ตามหลักสูตร"
        sub="ชุด Skill ของหลักสูตร = Skill แกนกลาง มศว (บังคับ) + เลือกจากฐานข้อมูลกลาง + เพิ่มเอง แล้วส่งให้คณะอนุมัติ · แต่ละฉบับระบุรหัสนิสิตที่ใช้" />
      {err && <Note kind="warn">{err}</Note>}
      <KpiRow>
        <Kpi label="อนุมัติแล้ว" value={d?.kpi.approved ?? "–"} on={st === "approved"} onClick={() => setSt((x) => (x === "approved" ? "" : "approved"))} />
        <Kpi label="ร่าง / รออนุมัติ" value={d?.kpi.pending ?? "–"} />
        <Kpi label="ยังไม่กำหนด" value={d?.kpi.none ?? "–"} on={st === "none"} onClick={() => setSt((x) => (x === "none" ? "" : "none"))} />
        <Kpi label="มีเฉพาะแกนกลาง" value={d?.kpi.only_core ?? "–"} sub="ยังไม่เพิ่ม SS ของหลักสูตร" />
      </KpiRow>
      <DataTable rows={(d?.items ?? []).filter((i) => (!fac || i.faculty === fac) && (!st || i.status === st))} columns={columns} rowKey={(i) => i.id} search={q} unit="หลักสูตร"
        searchText={(i) => i.name_th} empty={d ? "ไม่พบหลักสูตร" : "กำลังโหลด…"}
        toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นหาหลักสูตร" /><SelectFilter label="คณะ" value={fac} options={facs} onChange={setFac} /><SelectFilter label="สถานะ" value={st} options={Object.entries(d?.statuses ?? {})} onChange={setSt} /></Filters>} />
    </>
  );
}
