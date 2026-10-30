"use client";

// portfolio (mock · US-M3-07): students in the account's scope (อาจารย์ที่ปรึกษา: นิสิตในความดูแล)
// with their GS/SS/E/C averages and overall level; search by id or name, filter by curriculum
// and entry year, export the list.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { skillsApi, type PortfolioItem } from "@/lib/api";
import { CATS, CAT_COLOR, fmt2 } from "@/lib/skills";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, DataTable, Filters, SearchBox, SelectFilter, type Column } from "@/components/kit";

export default function PortfolioListPage() {
  const router = useRouter();
  const [items, setItems] = useState<PortfolioItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [prog, setProg] = useState("");
  const [entry, setEntry] = useState("");
  useEffect(() => { skillsApi.portfolios().then((r) => setItems(r.items)).catch((e) => setErr((e as Error).message)); }, []);
  const progs = useMemo(() => [...new Set((items ?? []).map((i) => i.program).filter(Boolean) as string[])].sort(), [items]);
  const years = useMemo(() => [...new Set((items ?? []).map((i) => String(i.entry_year ?? "")).filter(Boolean))].sort(), [items]);
  const rows = (items ?? []).filter((i) => (!prog || i.program === prog) && (!entry || String(i.entry_year) === entry));
  const columns: Column<PortfolioItem>[] = [
    { key: "n", label: "นิสิต", sort: (i) => i.sid, render: (i) => <><b>{i.name_th}</b><div className="small faint">{i.sid}</div></> },
    { key: "p", label: "หลักสูตร", render: (i) => <span className="small">{i.program}</span> },
    { key: "y", label: "ปีเข้า", sort: (i) => i.entry_year, render: (i) => <span className="num">{i.entry_year}</span> },
    ...CATS.map((c) => ({ key: c, label: <span style={{ color: CAT_COLOR[c] }}>{c}</span>, sort: (i: PortfolioItem) => i.cats[c] ?? -1, render: (i: PortfolioItem) => <div style={{ minWidth: 70 }}><b className="num">{fmt2(i.cats[c])}</b>{i.cats[c] != null && <Bar pct={(i.cats[c]! / 5) * 100} color={CAT_COLOR[c]} />}</div> })),
    { key: "lv", label: "ระดับรวม", sort: (i) => i.overall ?? -1, render: (i) => (i.level ? <Pill kind="red">{i.level}</Pill> : <span className="faint">ยังไม่มีผล</span>) },
  ];
  function exportCsv() {
    const url = URL.createObjectURL(new Blob([toCsv(["รหัส", "ชื่อ", "หลักสูตร", "ปีเข้า", ...CATS, "ระดับรวม"], rows.map((i) => [i.sid, i.name_th, i.program ?? "", i.entry_year ?? "", ...CATS.map((c) => i.cats[c] ?? ""), i.level ?? ""]))], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: "skill-portfolio.csv" }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ติดตามการประเมิน Skill"]} title="Skill Portfolio" sub="ผลทักษะสะสมของนิสิตในขอบเขตข้อมูลของบัญชีนี้ · คะแนน = ค่าเฉลี่ยทุกรายวิชาที่ยืนยันผลแล้ว"
        actions={<button type="button" className="btn" disabled={!rows.length} onClick={exportCsv}>ส่งออกรายชื่อ</button>} />
      {err && <Note kind="warn">{err}</Note>}
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.sid} search={q} unit="คน" searchText={(i) => `${i.sid} ${i.name_th}`} onRowClick={(i) => router.push(`/portfolio/${i.sid}`)}
        empty={items ? "ไม่พบนิสิต" : "กำลังโหลด…"}
        toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นด้วยรหัส ชื่อ หรือนามสกุล" /><SelectFilter label="หลักสูตร" value={prog} options={progs} onChange={setProg} /><SelectFilter label="รหัสปีเข้า" value={entry} options={years} onChange={setEntry} /></Filters>} />
    </>
  );
}
