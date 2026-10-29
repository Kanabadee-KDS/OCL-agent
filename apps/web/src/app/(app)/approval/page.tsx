"use client";

// กำหนดการตั้งค่าการอนุมัติ (mock: approval · US-U-05): every flow as a chain of steps.
import { useEffect, useState } from "react";
import Link from "next/link";
import { flowsApi, fmtTime, type Flow } from "@/lib/api";
import { Ic, Note, PageHead, Pill } from "@/components/ui";

export default function ApprovalPage() {
  const [items, setItems] = useState<Flow[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    flowsApi.list().then((r) => {
      setItems(r.items);
      setNames(Object.fromEntries(r.groups.map((g) => [g.id, g.name])));
    }).catch((e) => setErr((e as Error).message));
  }, []);
  const who = (roles: string[], position: string | null) => position || roles.map((r) => names[r] ?? r).join(" / ") || "–";
  return (
    <>
      <PageHead
        crumb={["บริหารจัดการสิทธิ์", "บริหารกลุ่มสิทธิ์"]}
        title="กำหนดการตั้งค่าการอนุมัติ"
        sub="ตั้งขั้นตอนการอนุมัติของแต่ละงาน ผู้อนุมัติแต่ละขั้น และระยะเวลาที่ควรดำเนินการ · บันทึกแล้วเป็นฉบับใหม่ งานที่เริ่มแล้วใช้ฉบับเดิมจนจบ"
      />
      {err && <Note kind="warn">{err}</Note>}
      {!items && !err && <div className="card pad">กำลังโหลด…</div>}
      {items?.map((f) => (
        <section key={f.id} className="card pad stack">
          <div className="between">
            <div className="row" style={{ gap: 8 }}>
              <h2 className="h2" style={{ margin: 0 }}>{f.name}</h2>
              <Pill>{f.steps.length} ขั้นตอน</Pill>
              <Pill kind="info">ฉบับที่ {f.version}</Pill>
              {f.id === "curriculum" ? <Pill kind="ok">ใช้งานอยู่</Pill> : <Pill kind="grey">ใช้เมื่อเปิดงานนี้</Pill>}
            </div>
            <Link href={`/approval/${f.id}`} className="btn xs">แก้ไข</Link>
          </div>
          <div className="row" style={{ gap: 6 }}>
            {f.steps.map((s, i) => (
              <span key={i} className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                {i > 0 && <Ic name="chev" size={13} width={2} />}
                <span className="pill p-grey" title={`${s.label} · ${s.days} วันทำการ`}>{who(s.roles, s.position)}</span>
              </span>
            ))}
          </div>
          {f.updated_by && <span className="small faint">แก้ล่าสุด {fmtTime(f.updated_at)} โดย {f.updated_by}</span>}
        </section>
      ))}
    </>
  );
}
