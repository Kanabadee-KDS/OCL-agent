"use client";

// qa-check (mock · US-M4-06): the curricula of the round the account may see (an evaluator:
// only those assigned), filters cleared with one button, the status of items 1–10, the data
// status and the result by BR-M4-01; Preview one or all (R10).
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { qaApi, type QaPrograms, type QaProgramRow } from "@/lib/api";
import { DATA_KIND, RESULT_KIND, RESULT_TH } from "@/lib/qa";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, SearchBox, SelectFilter, type Column } from "@/components/kit";
import { ResultPill, RoundSelect, useRound } from "@/components/qa";

const MARK: Record<string, string> = { pass: "✓", fail: "✕", pending: "?", na: "–", none: "·" };

export default function QaCheckPage() {
  const router = useRouter();
  const [rounds, rid, setRid, err] = useRound();
  const [d, setD] = useState<QaPrograms | null>(null);
  const [e2, setE2] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ level: "", set: "", fac: "", res: "", st: "" });
  useEffect(() => { if (rid) qaApi.programs(rid).then(setD).catch((e) => setE2((e as Error).message)); }, [rid]);
  const items = useMemo(() => d?.items ?? [], [d]);
  const opts = (k: (i: QaProgramRow) => string | null | number) => [...new Set(items.map(k).filter(Boolean).map(String))].sort();
  const rows = items.filter((i) => (!f.level || i.level === f.level) && (!f.set || String(i.set_year) === f.set) && (!f.fac || i.faculty === f.fac) && (!f.res || i.final === f.res) && (!f.st || i.status === f.st));
  const nos = useMemo(() => [...new Set(items.flatMap((i) => Object.keys(i.results)))].sort((a, b) => Number(a) - Number(b)), [items]);
  const columns: Column<QaProgramRow>[] = [
    { key: "n", label: "หลักสูตร", sort: (i) => i.name_th ?? "", render: (i) => <><Link href={`/qa/${rid}/${i.curriculum_id}`}><b>{i.name_th}</b></Link><div className="small faint">{i.faculty} · {i.level} · เกณฑ์ พ.ศ. {i.set_year}{i.roles.length ? ` · ${i.roles.map((r) => ({ recorder: "ผู้บันทึก", confirmer: "ผู้ยืนยัน", evaluator: "ผู้ประเมิน" })[r]).join(", ")}` : ""}</div></> },
    { key: "items", label: <span>เกณฑ์ {nos[0]}–{nos.at(-1)}</span>, render: (i) => <div className="row" style={{ gap: 2, flexWrap: "nowrap" }}>{nos.map((n) => <span key={n} title={`ข้อ ${n}: ${RESULT_TH[i.results[n] ?? "none"]}`} className={`pill p-${RESULT_KIND[i.results[n] ?? "none"] === "grey" ? "grey" : RESULT_KIND[i.results[n] ?? "none"]}`} style={{ minWidth: 22, justifyContent: "center", padding: "0 4px" }}>{MARK[i.results[n] ?? "none"]}</span>)}</div> },
    { key: "st", label: "สถานะข้อมูล", render: (i) => <>{!i.complete && <Pill kind="red">ยังไม่กำหนดผู้บันทึก</Pill>} <Pill kind={DATA_KIND[i.status]}>{i.status_th}</Pill></> },
    { key: "f", label: "ผลประเมิน", sort: (i) => i.final, render: (i) => <ResultPill r={i.final} /> },
    { key: "go", label: "", render: (i) => <Link className="btn xs" href={`/qa/${rid}/${i.curriculum_id}`}>เปิด</Link> },
  ];
  const sel = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  return (
    <>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตรวจสอบและประเมิน"]} title="ตรวจสอบข้อมูลองค์ประกอบที่ 1"
        sub="ตัวบ่งชี้ 1.1 การบริหารจัดการหลักสูตรตามเกณฑ์มาตรฐาน · ข้อมูลหลักฐานดึงจาก Data Warehouse (อัปเดตวันถัดไป) หากผิดให้ติดต่อหน่วยงานเจ้าของข้อมูล"
        actions={<>{rounds && <RoundSelect rounds={rounds} rid={rid} onChange={setRid} />}{rid && items.length > 0 && <Link className="btn" href={`/qa/${rid}/preview`}>Preview All</Link>}</>} />
      {(err || e2) && <Note kind="warn">{err || e2}</Note>}
      {rounds && !rounds.length && <Note kind="info">ยังไม่มีรอบการประเมิน</Note>}
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.curriculum_id} search={q} unit="หลักสูตร" searchText={(i) => i.name_th ?? ""} onRowClick={(i) => router.push(`/qa/${rid}/${i.curriculum_id}`)}
        empty={d ? "ไม่มีหลักสูตรที่บัญชีนี้ได้รับมอบหมายหรืออยู่ในขอบเขตข้อมูล" : "กำลังโหลด…"}
        toolbar={<Filters>
          <SearchBox value={q} onChange={setQ} placeholder="ค้นหาหลักสูตร" />
          <SelectFilter label="ระดับ" value={f.level} options={opts((i) => i.level)} onChange={sel("level")} />
          <SelectFilter label="เกณฑ์" value={f.set} options={opts((i) => i.set_year).map((y) => [y, `พ.ศ. ${y}`] as [string, string])} onChange={sel("set")} />
          <SelectFilter label="หน่วยงาน" value={f.fac} options={opts((i) => i.faculty)} onChange={sel("fac")} />
          <SelectFilter label="ผลประเมิน" value={f.res} options={Object.entries(d?.results ?? {})} onChange={sel("res")} />
          <SelectFilter label="สถานะข้อมูล" value={f.st} options={Object.entries(d?.statuses ?? {})} onChange={sel("st")} />
          <button type="button" className="btn sm" onClick={() => { setQ(""); setF({ level: "", set: "", fac: "", res: "", st: "" }); }}>ล้างตัวกรอง</button>
        </Filters>} />
    </>
  );
}
