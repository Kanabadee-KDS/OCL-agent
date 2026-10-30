"use client";

// issue (mock · US-M3-08): graduates by readiness (BR-M3-04): พร้อมออก / ผลประเมินไม่ครบ /
// Ethics ไม่ผ่าน / ออกแล้ว; select the ready ones and "สร้างเอกสารและส่งลงนาม" (ST-ปปปป-nnnnnn,
// signed by the signer from SUPREME through the sample signing service until one is chosen);
// the register of documents issued (R09) with how often each was checked; the conditions.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { fmtTime, skillsApi, type Graduate, type GraduateGroup, type Graduates, type RegisterRow } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { GROUP_TH } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, Kpi, KpiRow, SearchBox, Tabs, useToast, type Column } from "@/components/kit";

const KIND: Record<GraduateGroup, "ok" | "red" | "warn" | "info"> = { ready: "ok", incomplete: "red", ethics: "warn", issued: "info" };

export default function IssuePage() {
  const { data: session } = useSession();
  const canIssue = canMenu(session?.user?.perms, "s6", "add");
  const toast = useToast();
  const [tab, setTab] = useState<"list" | "reg" | "rule">("list");
  const [d, setD] = useState<Graduates | null>(null);
  const [reg, setReg] = useState<RegisterRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [g, setG] = useState<GraduateGroup | "">("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const load = () => {
    skillsApi.graduates().then((x) => { setD(x); setSel(x.items.filter((i) => i.group === "ready").map((i) => i.sid)); }).catch((e) => setErr((e as Error).message));
    skillsApi.register().then(setReg).catch(() => setReg([]));
  };
  useEffect(load, []);
  const rows = useMemo(() => (d?.items ?? []).filter((i) => !g || i.group === g), [d, g]);
  async function issue() {
    setBusy(true);
    try { const r = await skillsApi.issue(sel); toast(`ออกเอกสารแล้ว ${r.issued.length} ฉบับ (${r.issued[0]}${r.issued.length > 1 ? " …" : ""})`); load(); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  const columns: Column<Graduate>[] = [
    { key: "x", label: "", render: (i) => <input type="checkbox" aria-label={`เลือก ${i.name_th}`} disabled={i.group !== "ready" || !canIssue} checked={sel.includes(i.sid)} onChange={(e) => setSel((x) => (e.target.checked ? [...x, i.sid] : x.filter((y) => y !== i.sid)))} style={{ width: 18, height: 18 }} /> },
    { key: "n", label: "ผู้สำเร็จการศึกษา", sort: (i) => i.sid, render: (i) => <><b>{i.name_th}</b><div className="small faint">{i.sid} · {i.program} · สำเร็จ {i.graduated ?? "–"}</div></> },
    { key: "a", label: "ผลประเมิน Skill", render: (i) => (!i.has_set ? <Pill kind="red">ไม่มีชุด Skill ที่อนุมัติ</Pill> : i.missing.length ? <Pill kind="red">ขาด {i.missing.length} Skill</Pill> : <Pill kind="ok">ครบ {i.set_size} Skill</Pill>) },
    { key: "e", label: "Ethics", render: (i) => (i.ethics_u.length ? <Pill kind="red">U ({i.ethics_u.join(", ")})</Pill> : i.has_set && !i.missing.length ? <Pill kind="ok">S ทุกข้อ</Pill> : <span className="faint">–</span>) },
    { key: "g", label: "ความพร้อม", sort: (i) => i.group, render: (i) => <Pill kind={KIND[i.group]}>{GROUP_TH[i.group]}</Pill> },
    { key: "go", label: "", render: (i) => i.transcript ? <Link className="btn xs" href={`/portfolio/${i.sid}/transcript`}>{i.transcript.no}</Link> : <Link className="btn xs" href={`/portfolio/${i.sid}`}>ตรวจสอบ</Link> },
  ];
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ติดตามการประเมิน Skill"]} title="ออกเอกสาร Skill Transcript"
        sub="ผู้สำเร็จการศึกษาในขอบเขตข้อมูลของบัญชีนี้ · ออกได้เมื่อผลประเมินครบทุก Skill ในชุดของหลักสูตร และ Ethics ผ่าน (S) ทุกข้อ (BR-M3-04)"
        actions={tab === "list" && canIssue && <><button type="button" className="btn primary" disabled={!sel.length || busy} onClick={issue}>สร้างเอกสารและส่งลงนาม ({sel.length})</button></>} />
      {err && <Note kind="warn">{err}</Note>}
      <Tabs items={[["list", "ผู้สำเร็จการศึกษา"], ["reg", "ทะเบียนเอกสารที่ออก (R09)"], ["rule", "เงื่อนไขการออกเอกสาร"]] as const} value={tab} onChange={setTab} />
      {tab === "list" && (
        <>
          <KpiRow>
            {(["ready", "incomplete", "ethics", "issued"] as const).map((k) => <Kpi key={k} label={GROUP_TH[k]} value={d?.groups[k] ?? "–"} on={g === k} onClick={() => setG((x) => (x === k ? "" : k))} sub={k === "incomplete" ? "ต้องให้อาจารย์ประเมินเพิ่ม" : k === "ethics" ? "ส่งหลักสูตรพิจารณา" : undefined} />)}
          </KpiRow>
          <DataTable rows={rows} columns={columns} rowKey={(i) => i.sid} search={q} unit="คน" searchText={(i) => `${i.sid} ${i.name_th}`} empty={d ? "ไม่มีผู้สำเร็จการศึกษา" : "กำลังโหลด…"}
            toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นรหัสหรือชื่อ" /></Filters>} />
          <Note kind="info">ลายมือชื่อดิจิทัลยังเป็นบริการตัวอย่าง (บันทึกผู้ลงนามจาก SUPREME และลายนิ้วมือของเอกสาร ไม่มีผลทางกฎหมาย) จนกว่าจะเลือกบริการลงนามจริง</Note>
        </>
      )}
      {tab === "reg" && (
        <section className="card">
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>เลขที่</th><th>นิสิต</th><th>หลักสูตร</th><th>ออกเมื่อ</th><th className="r">ตรวจสอบ (ครั้ง)</th><th /></tr></thead>
            <tbody>
              {(reg ?? []).map((r) => <tr key={r.no}><td className="num"><b>{r.no}</b></td><td>{r.name_th}<div className="small faint">{r.sid}</div></td><td className="small">{r.program}</td><td className="small">{fmtTime(r.issued_at)}</td><td className="r num">{r.checks}</td><td><Link className="btn xs" href={`/portfolio/${r.sid}/transcript`}>ดู</Link></td></tr>)}
              {reg && !reg.length && <tr><td colSpan={6} className="empty">ยังไม่มีเอกสารที่ออก</td></tr>}
            </tbody></table></div>
        </section>
      )}
      {tab === "rule" && (
        <section className="card pad stack">
          <h2 className="h2">เงื่อนไขการออกเอกสาร (BR-M3-04)</h2>
          <ol className="stack" style={{ margin: 0, paddingLeft: 20 }}>
            <li>สำเร็จการศึกษาแล้ว (สถานะจาก SUPREME)</li>
            <li>หลักสูตรมีชุด Skill ที่อนุมัติแล้วสำหรับรุ่นของนิสิต และทุก Skill ในชุดมีผลประเมินที่ยืนยันแล้วอย่างน้อย 1 รายวิชา</li>
            <li>Ethics ผ่าน (S) ทุกข้อ: คะแนนตั้งแต่ {d?.ethics_pass.toFixed(2) ?? "2.50"} <Pill kind="warn">สมมติ · รอเกณฑ์แปลงจากลูกค้า</Pill></li>
          </ol>
          <span className="small faint">เลขที่ ST-ปปปป-nnnnnn ไม่ซ้ำ · ผู้ลงนามมาจาก SUPREME · ทุกฉบับตรวจได้ที่ /verify/เลขที่ หรือ QR บนเอกสาร โดยไม่ต้องเข้าสู่ระบบ</span>
        </section>
      )}
    </>
  );
}
