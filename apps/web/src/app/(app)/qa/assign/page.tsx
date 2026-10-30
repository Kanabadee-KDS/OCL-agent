"use client";

// qa-assign (mock · US-M4-03): per curriculum in the round, its recorders (more than one) and
// its confirmer, both from HURIS; a curriculum without both cannot be recorded. Copy from the
// earlier round; e-mail everyone assigned (once a day).
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { qaApi, type QaAssign, type QaPerson } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { DATA_KIND } from "@/lib/qa";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, Kpi, KpiRow, Modal, SearchBox, useToast, type Column } from "@/components/kit";
import { RoundSelect, useRound } from "@/components/qa";
import { StaffSearch } from "@/components/staffsearch";

type Row = QaAssign["items"][number];

export default function QaAssignPage() {
  const { data: session } = useSession();
  const canEdit = canMenu(session?.user?.perms, "q1b", "edit");
  const toast = useToast();
  const [rounds, rid, setRid, err] = useRound();
  const [d, setD] = useState<QaAssign | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState<"" | "complete" | "incomplete" | "confirmed">("");
  const [edit, setEdit] = useState<Row | null>(null);
  useEffect(() => { if (rid) qaApi.assign(rid).then(setD).catch((e) => toast((e as Error).message, "err")); }, [rid, toast]);
  const locked = d?.status === "closed";
  const rows = (d?.items ?? []).filter((i) => !f || (f === "complete" ? i.complete : f === "incomplete" ? !i.complete : i.status === "confirmed"));
  const columns: Column<Row>[] = [
    { key: "n", label: "หลักสูตร", sort: (i) => i.name_th ?? "", render: (i) => <><b>{i.name_th}</b><div className="small faint">{i.faculty} · {i.level} · เกณฑ์ พ.ศ. {i.set_year}</div></> },
    { key: "r", label: "ผู้บันทึกข้อมูล", render: (i) => <span className="small">{i.recorders.map((p) => p.name).join(", ") || <span className="faint">ยังไม่กำหนด</span>}</span> },
    { key: "c", label: "ผู้ยืนยันข้อมูล", render: (i) => <span className="small">{i.confirmer?.name ?? <span className="faint">ยังไม่กำหนด</span>}</span> },
    { key: "s", label: "สถานะ", render: (i) => <>{!i.complete && <Pill kind="red">ยังไม่ครบ</Pill>} <Pill kind={DATA_KIND[i.status]}>{d?.statuses[i.status]}</Pill></> },
    { key: "go", label: "", render: (i) => <button type="button" className="btn xs" onClick={() => setEdit(i)}>{canEdit && !locked ? "กำหนด" : "ดู"}</button> },
  ];
  async function run<T>(fn: () => Promise<T>, msg: (x: T) => string) {
    try { const x = await fn(); toast(msg(x)); if (rid) setD(await qaApi.assign(rid)); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <>
      <PageHead crumb={["ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", "ตั้งค่าการประเมิน"]} title="กำหนดผู้บันทึกและผู้ยืนยันข้อมูล"
        sub="ต่อหลักสูตรในรอบ · ผู้บันทึกกรอก/ตรวจทุกเกณฑ์แล้วส่งยืนยัน ผู้ยืนยันยืนยันหรือส่งคืนแก้ไข · หลักสูตรที่ยังไม่มีทั้งผู้บันทึกและผู้ยืนยันเปิดบันทึกไม่ได้"
        actions={<>{rounds && <RoundSelect rounds={rounds} rid={rid} onChange={setRid} />}{canEdit && !locked && rid && <>
          <button type="button" className="btn" onClick={() => run(() => qaApi.copyAssign(rid), (x) => `คัดลอกจากรอบก่อน ${x.copied} หลักสูตร`)}>คัดลอกจากรอบก่อน</button>
          <button type="button" className="btn" onClick={() => run(() => qaApi.notify(rid), (x) => (x.sent ? `ส่งอีเมลถึง ${x.sent} คน` : "ไม่มีผู้ที่ต้องแจ้ง หรือวันนี้แจ้งแล้ว"))}>แจ้งเตือนทางอีเมล</button></>}</>} />
      {err && <Note kind="warn">{err}</Note>}
      {rounds && !rounds.length && <Note kind="info">ยังไม่มีรอบการประเมิน · สร้างที่หน้ารอบการประเมิน</Note>}
      {locked && <Note kind="info">รอบนี้ล็อกข้อมูลแล้ว ดูได้อย่างเดียว</Note>}
      <KpiRow>
        <Kpi label="หลักสูตรในรอบ" value={d?.items.length ?? "–"} on={!f} onClick={() => setF("")} />
        <Kpi label="กำหนดครบ" value={d?.kpi.complete ?? "–"} on={f === "complete"} onClick={() => setF("complete")} />
        <Kpi label="ยังไม่ครบ" value={d?.kpi.incomplete ?? "–"} on={f === "incomplete"} onClick={() => setF("incomplete")} />
        <Kpi label="ยืนยันข้อมูลแล้ว" value={d?.kpi.confirmed ?? "–"} on={f === "confirmed"} onClick={() => setF("confirmed")} />
      </KpiRow>
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.curriculum_id} search={q} unit="หลักสูตร" empty={d ? "ไม่มีหลักสูตร" : "กำลังโหลด…"}
        searchText={(i) => `${i.name_th ?? ""} ${i.recorders.map((p) => p.name).join(" ")} ${i.confirmer?.name ?? ""}`}
        toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นหลักสูตรหรือชื่อผู้บันทึก" /></Filters>} />
      {edit && rid && <AssignModal row={edit} readOnly={!canEdit || locked} onClose={() => setEdit(null)}
        onSave={(r, c) => run(() => qaApi.setAssign(rid, edit.curriculum_id, r, c), () => "บันทึกการกำหนดแล้ว").then(() => setEdit(null))} />}
    </>
  );
}

function AssignModal({ row, readOnly, onClose, onSave }: { row: Row; readOnly: boolean; onClose: () => void; onSave: (recorders: string[], confirmer: string | null) => void }) {
  const [rec, setRec] = useState<QaPerson[]>(row.recorders);
  const [conf, setConf] = useState<QaPerson | null>(row.confirmer);
  return (
    <Modal open size="lg" title={`ผู้บันทึกและผู้ยืนยัน · ${row.name_th}`} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ปิด</button>{!readOnly && <button type="button" className="btn primary" onClick={() => onSave(rec.map((p) => p.pid), conf?.pid ?? null)}>บันทึก</button>}</>}>
      <div className="stack">
        <b>ผู้บันทึกข้อมูล</b>
        <div className="row" style={{ gap: 6 }}>{rec.map((p) => <span key={p.pid} className="pill p-info">{p.name} {!readOnly && <button type="button" className="link-btn" aria-label={`นำ ${p.name} ออก`} onClick={() => setRec((x) => x.filter((y) => y.pid !== p.pid))}>×</button>}</span>)}{!rec.length && <span className="small faint">ยังไม่มี</span>}</div>
        {!readOnly && <StaffSearch label="ค้นผู้บันทึก" exclude={rec.map((p) => p.pid)} onPick={(s) => setRec((x) => [...x, { pid: s.pid, name: `${s.title_short ?? ""}${s.name_th}` }])} />}
        <b>ผู้ยืนยันข้อมูล</b>
        <div>{conf ? <span className="pill p-info">{conf.name} {!readOnly && <button type="button" className="link-btn" aria-label="นำผู้ยืนยันออก" onClick={() => setConf(null)}>×</button>}</span> : <span className="small faint">ยังไม่มี</span>}</div>
        {!readOnly && <StaffSearch label="ค้นผู้ยืนยัน" exclude={conf ? [conf.pid] : []} onPick={(s) => setConf({ pid: s.pid, name: `${s.title_short ?? ""}${s.name_th}` })} />}
        <Note kind="info">ผู้บันทึกและผู้ยืนยันต้องมีบัญชีในระบบที่ผูกรหัสบุคลากร และอยู่ในกลุ่มสิทธิ์ที่เห็นเมนูตรวจสอบข้อมูลองค์ประกอบที่ 1 (เช่น ผู้ตรวจสอบระดับหลักสูตร)</Note>
      </div>
    </Modal>
  );
}
