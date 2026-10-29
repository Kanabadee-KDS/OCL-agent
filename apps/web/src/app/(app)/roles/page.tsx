"use client";

// กำหนดกลุ่มสิทธิ์การใช้งาน (mock: roles · US-U-04): every group, its data scope, modules and
// members; a new group starts as a copy of an existing one and opens in role-edit.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { roles as rolesApi, type RoleGroup } from "@/lib/api";
import { canMenu, NAV } from "@/lib/nav";
import { Ic, Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Field, Modal, useToast, type Column } from "@/components/kit";

const MOD_LABEL: Record<string, string> = { c: "หลักสูตร", p: "แผนฯ", s: "Skill", q: "ประเมินหลักสูตร", r: "รายงาน", u: "สิทธิ์", m: "นิสิต" };

export default function RolesPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState<RoleGroup[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [copy, setCopy] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { rolesApi.list().then((r) => setItems(r.items)).catch((e) => setErr((e as Error).message)); }, []);

  async function create() {
    setBusy(true);
    try {
      const g = await rolesApi.create(name, copy || null);
      toast(`สร้างกลุ่ม ${g.name} แล้ว`);
      router.push(`/roles/${g.id}`);
    } catch (e) {
      toast((e as Error).message, "err");
      setBusy(false);
    }
  }

  const columns: Column<RoleGroup>[] = [
    {
      key: "name", label: "กลุ่มสิทธิ์", sort: (g) => g.ord,
      render: (g) => (
        <>
          <Link href={`/roles/${g.id}`} style={{ fontWeight: 600 }}>{g.name}</Link>
          {!g.builtin && <> <Pill kind="info">สร้างเพิ่ม</Pill></>}
        </>
      ),
    },
    { key: "scope", label: "ขอบเขตข้อมูล", render: (g) => <span className="small">{g.scope || "–"}</span> },
    {
      key: "mods", label: "เมนูที่เข้าถึง",
      render: (g) => <div className="row" style={{ gap: 4 }}>{(g.modules ?? []).map((m) => <Pill key={m}>{MOD_LABEL[m] ?? m}</Pill>)}{!g.modules?.length && <span className="small faint">ยังไม่มี</span>}</div>,
    },
    { key: "users", label: "ผู้ใช้", align: "right", sort: (g) => g.users, render: (g) => <span className="num">{g.users.toLocaleString("th-TH")}</span> },
    { key: "act", label: "", render: (g) => <Link href={`/roles/${g.id}`} className="btn xs">กำหนดสิทธิ์</Link> },
  ];

  return (
    <>
      <PageHead
        crumb={["บริหารจัดการสิทธิ์", "บริหารกลุ่มสิทธิ์"]}
        title="กำหนดกลุ่มสิทธิ์การใช้งาน"
        sub="กำหนดสิทธิ์ ดู/เพิ่ม/แก้ไข/ลบ/อนุมัติ/พิมพ์ รายเมนู และขอบเขตข้อมูลตามมุมมองหลักสูตร รายบุคคล หรือส่วนงาน (TOR 6.16.3)"
        actions={canMenu(perms, "u1", "add") && (
          <button type="button" className="btn primary" onClick={() => setOpen(true)}><Ic name="plus" size={17} /> เพิ่มกลุ่มสิทธิ์</button>
        )}
      />
      {err && <Note kind="warn">{err}</Note>}
      {!items && !err && <div className="card pad">กำลังโหลด…</div>}
      {items && <DataTable rows={items} columns={columns} rowKey={(g) => g.id} unit="กลุ่ม" pageSize={50} />}
      <p className="small faint">จำนวนผู้ใช้นับเฉพาะบัญชีที่เปิดใช้งาน · เมนูทั้งหมด {NAV.reduce((n, m) => n + m.secs.reduce((k, s) => k + s.items.length, 0), 0)} เมนู</p>
      <Modal
        open={open}
        title="เพิ่มกลุ่มสิทธิ์"
        onClose={() => setOpen(false)}
        foot={
          <>
            <button type="button" className="btn" onClick={() => setOpen(false)}>ยกเลิก</button>
            <button type="button" className="btn primary" disabled={busy || !name.trim()} onClick={create}>สร้างและกำหนดสิทธิ์</button>
          </>
        }
      >
        <div className="stack">
          <Field label="ชื่อกลุ่มสิทธิ์">{(id) => <input id={id} className="inp" value={name} onChange={(e) => setName(e.target.value)} placeholder="เช่น ผู้ช่วยงานวิชาการคณะ" />}</Field>
          <Field label="คัดลอกสิทธิ์จาก">
            {(id) => (
              <select id={id} className="inp" value={copy} onChange={(e) => setCopy(e.target.value)}>
                <option value="">— ไม่คัดลอก —</option>
                {(items ?? []).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            )}
          </Field>
        </div>
      </Modal>
    </>
  );
}
