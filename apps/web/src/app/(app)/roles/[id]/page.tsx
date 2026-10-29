"use client";

// role-edit (mock · US-U-04): menu × ดู/เพิ่ม/แก้ไข/ลบ/อนุมัติ/พิมพ์, ขอบเขตข้อมูล, the two
// switches, and who changed the group when. The API enforces the same rules (ocl_api.roles).
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { fmtTime, roles as rolesApi, type RoleDetail } from "@/lib/api";
import { canMenu, NAV } from "@/lib/nav";
import { ACTION_ORDER, changes, toggle, type Matrix } from "@/lib/roles";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Modal, Switch, useToast } from "@/components/kit";

export default function RoleEditPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const canEdit = canMenu(perms, "u1", "edit");
  const router = useRouter();
  const toast = useToast();
  const [g, setG] = useState<RoleDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [m, setM] = useState<Matrix>({});
  const [name, setName] = useState("");
  const [scope, setScope] = useState("");
  const [auto, setAuto] = useState(false);
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);

  function load(d: RoleDetail) {
    setG(d);
    setM(d.perms);
    setName(d.name);
    setScope(d.scope_kind);
    setAuto(d.auto_from_teachers);
    setNotify(d.notify_on_change);
  }
  useEffect(() => { rolesApi.get(id).then(load).catch((e) => setErr((e as Error).message)); }, [id]);

  const pending = useMemo(() => {
    if (!g) return 0;
    return changes(g.perms, m) + Number(name.trim() !== g.name) + Number(scope !== g.scope_kind)
      + Number(auto !== g.auto_from_teachers) + Number(notify !== g.notify_on_change);
  }, [g, m, name, scope, auto, notify]);

  async function save() {
    setBusy(true);
    try {
      const d = await rolesApi.update(id, { name: name.trim(), scope_kind: scope, perms: m, auto_from_teachers: auto, notify_on_change: notify });
      load(d);
      toast(d.notified ? `บันทึกแล้ว · แจ้งผู้ใช้ ${d.notified} คนทางอีเมล` : "บันทึกแล้ว");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    try {
      await rolesApi.remove(id);
      toast("ลบกลุ่มสิทธิ์แล้ว");
      router.push("/roles");
    } catch (e) {
      toast((e as Error).message, "err");
      setAskDelete(false);
    }
  }

  if (err) return <><BackLink href="/roles">กลับไปกลุ่มสิทธิ์</BackLink><Note kind="warn">{err}</Note></>;
  if (!g) return <div className="card pad">กำลังโหลด…</div>;
  const actions = g.actions;
  return (
    <>
      <BackLink href="/roles">กลับไปกลุ่มสิทธิ์</BackLink>
      <PageHead
        crumb={["บริหารจัดการสิทธิ์", "กลุ่มสิทธิ์"]}
        title={g.name}
        sub={<>ผู้ใช้ในกลุ่ม {g.users.toLocaleString("th-TH")} คน · {g.builtin ? "กลุ่มตั้งต้นตาม BRD" : "กลุ่มที่สร้างเพิ่ม"}{g.updated_by && <> · แก้ล่าสุด {fmtTime(g.updated_at)} โดย {g.updated_by}</>}</>}
        actions={
          <>
            {!g.builtin && canMenu(perms, "u1", "delete") && <button type="button" className="btn" onClick={() => setAskDelete(true)}>ลบกลุ่ม</button>}
            {canEdit && <button type="button" className="btn primary" disabled={busy || pending === 0} onClick={save}>{pending ? `บันทึก (${pending} รายการ)` : "บันทึก"}</button>}
          </>
        }
      />
      {!canEdit && <Note kind="info">บัญชีนี้ดูได้อย่างเดียว · การแก้สิทธิ์ต้องมีสิทธิ์ &ldquo;แก้ไข&rdquo; ในเมนูนี้</Note>}
      {g.id === "admin" && <Note kind="info">กลุ่มผู้ดูแลระบบต้องคงสิทธิ์ดูและแก้ไขเมนูนี้ เพื่อไม่ให้ไม่มีใครแก้สิทธิ์ได้</Note>}

      <section className="card pad stack">
        <label className="field" style={{ maxWidth: 420 }}>
          <span className="lbl">ชื่อกลุ่มสิทธิ์</span>
          <input className="inp" value={name} disabled={!canEdit} onChange={(e) => setName(e.target.value)} />
        </label>
      </section>

      <section className="card">
        <div className="tbl-wrap" style={{ border: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>เมนู</th>
                {ACTION_ORDER.map((a) => <th key={a} style={{ textAlign: "center", width: 72 }}>{actions[a]}</th>)}
              </tr>
            </thead>
            <tbody>
              {NAV.map((mod) => (
                <ModuleRows key={mod.k} label={mod.label} items={mod.secs.flatMap((s) => s.items)} m={m} disabled={!canEdit} onToggle={(menu, a, on) => setM((cur) => toggle(cur, menu, a, on))} actions={actions} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card pad stack">
        <h2 className="h2" style={{ margin: 0 }}>ขอบเขตข้อมูล</h2>
        <div role="radiogroup" aria-label="ขอบเขตข้อมูล" className="stack" style={{ gap: 6 }}>
          {Object.entries(g.scopes).map(([k, label]) => (
            <label key={k} className="check">
              <input type="radio" name="scope" value={k} checked={scope === k} disabled={!canEdit} onChange={() => setScope(k)} /> {label}
            </label>
          ))}
        </div>
        <p className="small faint" style={{ margin: 0 }}>การกรองข้อมูลตามขอบเขตเริ่มใช้กับรายการคู่มือหลักสูตรในงานถัดไป (FS-2)</p>
        <div className="between">
          <span>กำหนดสิทธิ์อัตโนมัติจากรายชื่ออาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร (6.16.3.4)<br /><span className="small faint">เก็บค่าไว้ ใช้งานได้เมื่อระบบมีรายชื่ออาจารย์ของแต่ละหลักสูตร</span></span>
          <Switch on={auto} disabled={!canEdit} onChange={setAuto} label="กำหนดสิทธิ์อัตโนมัติจากรายชื่ออาจารย์" />
        </div>
        <div className="between">
          <span>แจ้งเตือนสิทธิ์ทางอีเมลเมื่อมีการเปลี่ยนแปลง</span>
          <Switch on={notify} disabled={!canEdit} onChange={setNotify} label="แจ้งเตือนสิทธิ์ทางอีเมล" />
        </div>
        <p className="small faint" style={{ margin: 0 }}>ผู้ใช้ที่มีหลายกลุ่มสิทธิ์สลับบทบาทได้จากปุ่มชื่อบนแถบด้านบน</p>
      </section>

      <section className="card pad stack">
        <h2 className="h2" style={{ margin: 0 }}>ประวัติการแก้ไข</h2>
        {g.events.length === 0 ? <span className="small faint">ยังไม่มีการแก้ไข</span> : (
          <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: 6 }}>
            {g.events.map((e, i) => (
              <li key={i} className="small">
                <b>{fmtTime(e.ts)}</b> · {e.by ?? "–"} · {e.action === "create" ? "สร้างกลุ่ม" : e.action === "update" ? "แก้ไข" : e.action}
                {changeCount(e.detail.added) > 0 && <> · <Pill kind="ok">เพิ่ม {changeCount(e.detail.added)}</Pill></>}
                {changeCount(e.detail.removed) > 0 && <> · <Pill kind="red">ถอด {changeCount(e.detail.removed)}</Pill></>}
                {"scope_kind" in e.detail && <> · เปลี่ยนขอบเขตข้อมูล</>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Modal
        open={askDelete}
        title={`ลบกลุ่ม ${g.name}`}
        onClose={() => setAskDelete(false)}
        foot={<><button type="button" className="btn" onClick={() => setAskDelete(false)}>ยกเลิก</button><button type="button" className="btn primary" onClick={remove}>ลบกลุ่ม</button></>}
      >
        <p style={{ margin: 0 }}>ลบได้เฉพาะกลุ่มที่ไม่มีผู้ใช้ · การลบบันทึกในประวัติ และย้อนกลับไม่ได้</p>
      </Modal>
    </>
  );
}

const changeCount = (v: unknown) => (Array.isArray(v) ? v.length : 0);

function ModuleRows({ label, items, m, disabled, onToggle, actions }: {
  label: string;
  items: { id: string; label: string; inherits?: string }[];
  m: Matrix;
  disabled: boolean;
  onToggle: (menu: string, action: string, on: boolean) => void;
  actions: Record<string, string>;
}) {
  return (
    <>
      <tr><td colSpan={7} style={{ background: "var(--surface-2)", fontWeight: 600 }}>{label}</td></tr>
      {items.map((i) => (
        <tr key={i.id}>
          <td style={{ paddingLeft: 28 }}>{i.label}{i.inherits && <span className="small faint"> · ตามเมนูหลัก</span>}</td>
          {ACTION_ORDER.map((a) => (
            <td key={a} style={{ textAlign: "center" }}>
              {i.inherits ? (
                <span className="faint" aria-hidden="true">{(m[i.inherits] ?? []).includes(a) ? "✓" : "–"}</span>
              ) : (
                <input
                  type="checkbox"
                  aria-label={`${i.label}: ${actions[a]}`}
                  checked={(m[i.id] ?? []).includes(a)}
                  disabled={disabled}
                  onChange={(e) => onToggle(i.id, a, e.target.checked)}
                />
              )}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
