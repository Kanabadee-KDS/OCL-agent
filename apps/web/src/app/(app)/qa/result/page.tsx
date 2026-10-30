"use client";

// qa-result (mock · US-M4-07): per round, ผ่านทุกข้อ + ไม่ผ่านอย่างน้อย 1 ข้อ + รอพิจารณา =
// curricula in the round (BR-M4-01); per curriculum passed / applicable and the result;
// export, and R10 (ฉบับร่าง / ฉบับจริงเมื่อทุกข้อมีผล).
import { useEffect, useState } from "react";
import Link from "next/link";
import { qaApi, type QaSummary } from "@/lib/api";
import { DATA_KIND } from "@/lib/qa";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Kpi, KpiRow, type Column } from "@/components/kit";
import { ResultPill, RoundSelect, useRound } from "@/components/qa";

type Row = QaSummary["items"][number];
const RES_TH = { pass: "ผ่าน", fail: "ไม่ผ่าน", pending: "รอพิจารณา" };

export default function QaResultPage() {
  const [rounds, rid, setRid, err] = useRound();
  const [d, setD] = useState<QaSummary | null>(null);
  const [f, setF] = useState<"" | "pass" | "fail" | "pending">("");
  const [e2, setE2] = useState<string | null>(null);
  useEffect(() => { if (rid) qaApi.summary(rid).then(setD).catch((e) => setE2((e as Error).message)); }, [rid]);
  const rows = (d?.items ?? []).filter((i) => !f || i.final === f);
  const columns: Column<Row>[] = [
    { key: "n", label: "หลักสูตร", sort: (i) => i.name_th ?? "", render: (i) => <><Link href={`/qa/${rid}/${i.curriculum_id}`}><b>{i.name_th}</b></Link><div className="small faint">{i.level} · เกณฑ์ พ.ศ. {i.set_year}</div></> },
    { key: "fac", label: "คณะ", render: (i) => <span className="small">{i.faculty}</span> },
    { key: "p", label: "ผ่าน/ทั้งหมด", align: "right", sort: (i) => i.passed / (i.total || 1), render: (i) => <span className="num">{i.passed}/{i.total}</span> },
    { key: "st", label: "สถานะข้อมูล", render: (i) => <Pill kind={DATA_KIND[i.status]}>{({ none: "ยังไม่บันทึก", doing: "อยู่ระหว่างบันทึก", sent: "ส่งยืนยันแล้ว", confirmed: "ยืนยันข้อมูลแล้ว" })[i.status]}</Pill> },
    { key: "f", label: "ผลสุดท้าย", sort: (i) => i.final, render: (i) => <ResultPill r={i.final} /> },
    { key: "r10", label: "R10", render: (i) => <Link className="btn xs" href={`/qa/${rid}/preview?cid=${i.curriculum_id}`}>{i.complete && i.status === "confirmed" ? "ฉบับจริง" : "ฉบับร่าง"}</Link> },
  ];
  function exportCsv() {
    if (!d) return;
    const url = URL.createObjectURL(new Blob([toCsv(["หลักสูตร", "ระดับ", "คณะ", "เกณฑ์", "ผ่าน", "ทั้งหมด", "ผลสุดท้าย"], d.items.map((i) => [i.name_th ?? "", i.level ?? "", i.faculty ?? "", i.set_year, i.passed, i.total, RES_TH[i.final]]))], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `qa-result-${d.year}.csv` }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตรวจสอบและประเมิน"]} title="สรุปผลการประเมิน"
        sub={d ? <>{d.name} · {d.status_th}</> : "ผลการประเมินองค์ประกอบที่ 1 ต่อรอบ"}
        actions={<>{rounds && <RoundSelect rounds={rounds} rid={rid} onChange={setRid} />}<button type="button" className="btn" disabled={!d?.items.length} onClick={exportCsv}>ส่งออก CSV</button>{rid && <Link className="btn" href={`/qa/${rid}/preview`}>R10 ทั้งรอบ</Link>}</>} />
      {(err || e2) && <Note kind="warn">{err || e2}</Note>}
      <KpiRow>
        <Kpi label="หลักสูตรในรอบ" value={d?.kpi.programs ?? "–"} on={!f} onClick={() => setF("")} />
        <Kpi label="ผ่านทุกข้อ" value={d?.kpi.pass ?? "–"} on={f === "pass"} onClick={() => setF("pass")} />
        <Kpi label="ไม่ผ่านอย่างน้อย 1 ข้อ" value={d?.kpi.fail ?? "–"} on={f === "fail"} onClick={() => setF("fail")} />
        <Kpi label="รอพิจารณา" value={d?.kpi.pending ?? "–"} on={f === "pending"} onClick={() => setF("pending")} />
      </KpiRow>
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.curriculum_id} unit="หลักสูตร" empty={d ? "ไม่มีหลักสูตร" : "กำลังโหลด…"} />
    </>
  );
}
