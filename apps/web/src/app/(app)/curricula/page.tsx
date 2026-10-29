"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { canMenu } from "@/lib/nav";
import { curricula, fmtTime, STATUS_KIND, type CurriculumList, type CurriculumRow } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Field, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";

const LEVELS = ["ปริญญาตรี", "ประกาศนียบัตรบัณฑิต", "ปริญญาโท", "ประกาศนียบัตรบัณฑิตชั้นสูง", "ปริญญาเอก"];
import { options } from "@/lib/table";

const KPI_SUB: Record<string, string> = {
  import: "จากการนำเข้าด้วย AI",
  review: "กำหนด 5 วันทำการ",
  verified: "ล็อก แก้ผ่าน สมอ.08",
  published: "เปิด/ปิดโดยส่วนกลาง",
};

const COLUMNS: Column<CurriculumRow>[] = [
  {
    key: "name", label: "หลักสูตร", sort: (c) => c.name_th,
    render: (c) => (
      <>
        <Link href={`/curricula/${c.id}`} style={{ fontWeight: 600 }}>{c.name_th ?? "(ไม่มีชื่อ)"}</Link>
        <div className="small faint">{c.program_code ?? "ไม่มีรหัส สกอ."} · งาน {c.job_id}</div>
      </>
    ),
  },
  { key: "level", label: "ระดับ", sort: (c) => c.level, render: (c) => c.level ?? "–" },
  { key: "faculty", label: "คณะ", sort: (c) => c.faculty, render: (c) => <span className="small">{c.faculty ?? "–"}</span> },
  { key: "year", label: "ปีที่เริ่มใช้", sort: (c) => c.start_year, render: (c) => c.start_year ?? "–" },
  { key: "rev", label: "ฉบับ", render: (c) => <span className="small">{c.revision_type ?? "–"}</span> },
  {
    key: "status", label: "สถานะ",
    render: (c) => (
      <>
        <Pill kind={STATUS_KIND[c.status]}>{c.status_th}</Pill>
        {c.status === "review" && <div className="small faint">ติ๊กแล้ว {Object.values(c.faculty_checked ?? {}).filter(Boolean).length}/2 หมวด</div>}
      </>
    ),
  },
  { key: "due", label: "กำหนดตรวจ", sort: (c) => c.review_due_at, render: (c) => <span className="small">{c.review_due_at ?? "–"}</span> },
  {
    key: "last", label: "ล่าสุด", sort: (c) => c.last_event?.ts ?? c.finalized_at,
    render: (c) => <span className="small">{c.last_event ? `${fmtTime(c.last_event.ts)} · ${c.last_event.by}` : fmtTime(c.finalized_at)}</span>,
  },
  {
    key: "act", label: "",
    render: (c) => (
      <Link href={`/curricula/${c.id}`} className="btn xs">
        {c.status === "review" ? "ตรวจสอบ" : c.status === "import" ? "แก้ไขร่าง / ส่งตรวจ" : "ดูรายละเอียด"}
      </Link>
    ),
  },
];

const searchText = (c: CurriculumRow) => `${c.name_th ?? ""} ${c.program_code ?? ""} ${c.faculty ?? ""} ${c.job_id}`;
const filterValue = (c: CurriculumRow, k: string) => (k === "status" ? c.status : k === "faculty" ? c.faculty : k === "level" ? c.level : undefined);

export default function CurriculaPage() {
  const [data, setData] = useState<CurriculumList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ status: "", faculty: "", level: "" });
  const { data: session } = useSession();
  const router = useRouter();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name_th: "", level: "ปริญญาตรี", faculty: "" });
  async function add() {
    try {
      const d = await curricula.create({ ...draft, faculty: draft.faculty || null });
      toast("เพิ่มหลักสูตรแล้ว");
      router.push(`/curricula/${d.id}`);
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }
  useEffect(() => { curricula.list().then(setData).catch((e) => setErr((e as Error).message)); }, []);
  const items = data?.items ?? [];
  const set = (k: keyof typeof f) => (v: string) => setF((o) => ({ ...o, [k]: v }));
  return (
    <>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "คู่มือหลักสูตร"]}
        title="คู่มือหลักสูตร"
        sub="สถานะของคู่มือหลักสูตรที่นำเข้าจากเล่มด้วย AI: ร่าง → คณะตรวจสอบ (5 วันทำการ แก้ได้เฉพาะหมวด 3–4) → ตรวจสอบสำเร็จ (ล็อก) → เผยแพร่"
        actions={
          <>
            {canMenu(session?.user?.perms, "c1", "add") && <button type="button" className="btn" onClick={() => setAdding(true)}><Ic name="plus" size={17} /> เพิ่มหลักสูตร</button>}
            <Link href="/import" className="btn primary"><Ic name="ai" size={17} /> นำเข้าจากเล่มด้วย AI</Link>
          </>
        }
      />
      {err && <Note kind="warn">{err}</Note>}
      {!data && !err && <div className="card pad">กำลังโหลด…</div>}
      {data && (
        <>
          <KpiRow>
            {Object.entries(data.statuses).map(([k, label]) => (
              <Kpi key={k} label={label} value={data.counts[k] ?? 0} sub={KPI_SUB[k]} on={f.status === k} onClick={() => set("status")(f.status === k ? "" : k)} />
            ))}
          </KpiRow>
          <Filters>
            <SearchBox value={q} onChange={setQ} placeholder="ค้นหาชื่อหลักสูตร รหัส สกอ. หรือคณะ" />
            <SelectFilter label="สถานะ" value={f.status} options={Object.entries(data.statuses)} onChange={set("status")} />
            <SelectFilter label="คณะ" value={f.faculty} options={options(items, (c) => c.faculty)} onChange={set("faculty")} />
            <SelectFilter label="ระดับ" value={f.level} options={options(items, (c) => c.level)} onChange={set("level")} />
          </Filters>
          <DataTable
            rows={items}
            columns={COLUMNS}
            rowKey={(c) => c.id}
            search={q}
            searchText={searchText}
            filters={f}
            filterValue={filterValue}
            unit="หลักสูตร"
            empty={items.length === 0 ? "ยังไม่มีคู่มือหลักสูตร · นำเข้าจากเล่มแล้วกด \"บันทึกเข้าระบบ\"" : "ไม่พบหลักสูตรตามเงื่อนไข"}
          />
        </>
      )}
      <Modal
        open={adding}
        title="เพิ่มหลักสูตร"
        onClose={() => setAdding(false)}
        foot={<><button type="button" className="btn" onClick={() => setAdding(false)}>ยกเลิก</button><button type="button" className="btn primary" disabled={!draft.name_th.trim()} onClick={add}>สร้างร่าง</button></>}
      >
        <div className="stack">
          <Field label="ชื่อหลักสูตร (ภาษาไทย)">{(id) => <input id={id} className="inp" value={draft.name_th} onChange={(e) => setDraft((o) => ({ ...o, name_th: e.target.value }))} placeholder="เช่น หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชา..." />}</Field>
          <Field label="ระดับการศึกษา">{(id) => <select id={id} className="inp" value={draft.level} onChange={(e) => setDraft((o) => ({ ...o, level: e.target.value }))}>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select>}</Field>
          <Field label="คณะ/ส่วนงาน">{(id) => <><input id={id} className="inp" list="faculties" value={draft.faculty} onChange={(e) => setDraft((o) => ({ ...o, faculty: e.target.value }))} /><datalist id="faculties">{options(data?.items ?? [], (c) => c.faculty).map((x) => <option key={x} value={x} />)}</datalist></>}</Field>
          <Note kind="info">ร่างใหม่ยังไม่มีข้อมูล · กรอกหมวด 0–5 ในฟอร์มของคู่มือ หรือใช้ &ldquo;นำเข้าจากเล่มด้วย AI&rdquo; เพื่อเติมจากเล่มหลักสูตร</Note>
        </div>
      </Modal>
    </>
  );
}
