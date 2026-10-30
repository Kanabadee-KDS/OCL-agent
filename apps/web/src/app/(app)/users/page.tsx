"use client";

// กำหนดผู้ใช้งาน (mock: users · US-U-03): search and filter accounts, add staff from the HURIS
// copy, invite outside evaluators with an end date, edit groups/units, suspend or re-enable.
// Accounts are never deleted; Buasri passwords are set on the server (plan FS-1c · Q1 ข).
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { fmtTime, usersApi, type Staff, type UserDetail, type UserOptions, type UserRow } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { Ic, Note, PageHead, Pill } from "@/components/ui";
import { Check, DataTable, Field, Filters, Modal, SampleData, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";

const STATUS: [string, string][] = [["active", "ใช้งาน"], ["suspended", "ระงับ"], ["expired", "หมดสิทธิ์"]];
const statusOf = (u: UserRow) => (!u.active ? "suspended" : u.usable ? "active" : "expired");

type Mode = { kind: "add" } | { kind: "invite" } | { kind: "edit"; email: string };

export default function UsersPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const me = session?.user?.email ?? "";
  const canAdd = canMenu(perms, "u3", "add");
  const canEdit = canMenu(perms, "u3", "edit");
  const toast = useToast();
  const [rows, setRows] = useState<UserRow[] | null>(null);
  const [opts, setOpts] = useState<UserOptions | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ role: "", status: "" });
  const [mode, setMode] = useState<Mode | null>(null);

  const reload = () => usersApi.list().then((r) => setRows(r.items)).catch((e) => setErr((e as Error).message));
  useEffect(() => {
    reload();
    usersApi.options().then(setOpts).catch((e) => setErr((e as Error).message));
  }, []);
  const roleName = useMemo(() => Object.fromEntries((opts?.roles ?? []).map((r) => [r.id, r.name])), [opts]);

  async function toggleActive(u: UserRow) {
    try {
      await usersApi.setActive(u.email, !u.active);
      toast(u.active ? `ระงับ ${u.name || u.email} แล้ว` : `เปิดใช้ ${u.name || u.email} แล้ว`);
      reload();
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }

  const columns: Column<UserRow>[] = [
    {
      key: "who", label: "ผู้ใช้", sort: (u) => u.name || u.email,
      render: (u) => (
        <div className="row" style={{ flexWrap: "nowrap", gap: 10 }}>
          <span className="av" style={{ width: 32, height: 32, fontSize: 12 }}>{(u.name.replace(/^\S+\.\s?|\[/g, "") || u.email).slice(0, 1)}</span>
          <div>
            <b>{u.name || "(ยังไม่มีชื่อ)"}</b>
            <div className="small faint">{u.email}{u.kind === "external" && " · ผู้ใช้ภายนอก"}</div>
          </div>
        </div>
      ),
    },
    { key: "roles", label: "กลุ่มสิทธิ์", render: (u) => <div className="row" style={{ gap: 4 }}>{u.roles.map((r) => <Pill key={r} kind={r === "admin" ? "red" : "grey"}>{roleName[r] ?? r}</Pill>)}</div> },
    { key: "units", label: "หน่วยงานที่มองเห็น", render: (u) => <div className="row" style={{ gap: 4 }}>{u.units.length ? u.units.map((x) => <Pill key={x} kind="info">{x}</Pill>) : <span className="small faint">–</span>}</div> },
    {
      key: "status", label: "สถานะ", sort: (u) => statusOf(u),
      render: (u) => (
        <>
          {statusOf(u) === "active" ? <Pill kind="ok">ใช้งาน</Pill> : statusOf(u) === "suspended" ? <Pill kind="grey">ระงับ</Pill> : <Pill kind="warn">หมดสิทธิ์</Pill>}
          {u.expires_at && <div className="small faint">ถึง {u.expires_at}</div>}
        </>
      ),
    },
    {
      key: "pw", label: "เข้าสู่ระบบ",
      render: (u) => <span className="small">{u.kind === "external" ? "รหัสยืนยันทางอีเมล" : u.has_password ? "บัวศรีไอดี · ตั้งรหัสผ่านแล้ว" : <span className="faint">ยังไม่ตั้งรหัสผ่าน</span>}</span>,
    },
    { key: "last", label: "เข้าใช้ล่าสุด", sort: (u) => u.last_login_at, render: (u) => <span className="small">{u.last_login_at ? fmtTime(u.last_login_at) : "–"}</span> },
    {
      key: "act", label: "",
      render: (u) => (
        <div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
          <button type="button" className="btn xs" onClick={() => setMode({ kind: "edit", email: u.email })}>{canEdit ? "แก้ไข" : "ดู"}</button>
          {canEdit && u.email !== me && <button type="button" className="btn xs" onClick={() => toggleActive(u)}>{u.active ? "ระงับ" : "เปิดใช้"}</button>}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHead
        crumb={["บริหารจัดการสิทธิ์", "บริหารผู้ใช้งาน"]}
        title="กำหนดผู้ใช้งาน"
        sub="ผู้ใช้หนึ่งคนมีได้มากกว่า 1 กลุ่มสิทธิ์ และกำหนดหน่วยงานที่มองเห็นได้มากกว่า 1 หน่วยงาน · ระงับแทนการลบ"
        actions={canAdd && (
          <>
            <button type="button" className="btn" onClick={() => setMode({ kind: "invite" })}><Ic name="mail" size={17} /> เชิญผู้ใช้ภายนอก</button>
            <button type="button" className="btn primary" onClick={() => setMode({ kind: "add" })}><Ic name="plus" size={17} /> เพิ่มผู้ใช้</button>
          </>
        )}
      />
      {err && <Note kind="warn">{err}</Note>}
      {!rows && !err && <div className="card pad">กำลังโหลด…</div>}
      {rows && (
        <>
          <Filters>
            <SearchBox value={q} onChange={setQ} placeholder="ค้นหาชื่อหรืออีเมล" />
            <SelectFilter label="กลุ่มสิทธิ์" value={f.role} options={(opts?.roles ?? []).map((r) => [r.id, r.name] as [string, string])} onChange={(v) => setF((o) => ({ ...o, role: v }))} />
            <SelectFilter label="สถานะ" value={f.status} options={STATUS} onChange={(v) => setF((o) => ({ ...o, status: v }))} />
          </Filters>
          <DataTable
            rows={rows}
            columns={columns}
            rowKey={(u) => u.email}
            search={q}
            searchText={(u) => `${u.name} ${u.email} ${u.buasri_id ?? ""}`}
            filters={f}
            filterValue={(u, k) => (k === "status" ? statusOf(u) : k === "role" ? (u.roles.includes(f.role) ? f.role : "") : undefined)}
            unit="คน"
            empty="ไม่พบผู้ใช้"
          />
          <p className="small faint">บัญชีบุคลากรเข้าสู่ระบบด้วยบัวศรีไอดี · ผู้ดูแล server เป็นผู้ตั้งรหัสผ่านให้บัญชีใหม่ จนกว่าจะเชื่อมระบบยืนยันตัวตนของมหาวิทยาลัย</p>
        </>
      )}
      {mode && opts && (
        <UserModal
          mode={mode}
          opts={opts}
          me={me}
          canEdit={canEdit}
          onClose={() => setMode(null)}
          onSaved={(msg) => { toast(msg); setMode(null); reload(); }}
        />
      )}
    </>
  );
}

function UserModal({ mode, opts, me, canEdit, onClose, onSaved }: {
  mode: Mode; opts: UserOptions; me: string; canEdit: boolean; onClose: () => void; onSaved: (msg: string) => void;
}) {
  const toast = useToast();
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [staffQ, setStaffQ] = useState("");
  const [staff, setStaff] = useState<Staff[]>([]);
  const [picked, setPicked] = useState<Staff | null>(null);
  const [staffSample, setStaffSample] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [sid, setSid] = useState("");
  const [roles, setRoles] = useState<string[]>(mode.kind === "invite" ? ["evaluator"] : []);
  const [units, setUnits] = useState<string[]>([]);
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);
  const self = mode.kind === "edit" && mode.email === me;
  const readOnly = mode.kind === "edit" && !canEdit;

  useEffect(() => {
    if (mode.kind !== "edit") return;
    usersApi.get(mode.email).then((d) => {
      setDetail(d);
      setName(d.name);
      setRoles(d.roles);
      setUnits(d.units);
      setExpires(d.expires_at ?? "");
    }).catch((e) => toast((e as Error).message, "err"));
  }, [mode, toast]);

  useEffect(() => {
    if (mode.kind !== "add" || staffQ.trim().length < 2) return;
    const t = setTimeout(() => {
      usersApi.staff(staffQ).then((r) => { setStaff(r.items); setStaffSample(!!r.source?.sample); }).catch(() => setStaff([]));
    }, 250);
    return () => clearTimeout(t);
  }, [staffQ, mode.kind]);

  const shownStaff = staffQ.trim().length >= 2 ? staff : [];
  const flip = (list: string[], v: string, on: boolean) => (on ? [...list, v] : list.filter((x) => x !== v));

  async function save() {
    setBusy(true);
    try {
      if (mode.kind === "add") {
        const u = await usersApi.add(picked ? { pid: picked.pid, roles, units, expires_at: expires || null } : { email, name, roles, units, expires_at: expires || null, ...(sid.trim() ? { sid: sid.trim() } : {}) });
        onSaved(`เพิ่ม ${u.name || u.email} แล้ว · ตั้งรหัสผ่านบัวศรีไอดีที่ server ก่อนเข้าใช้`);
      } else if (mode.kind === "invite") {
        const u = await usersApi.invite({ email, name, roles, units, expires_at: expires });
        onSaved(`ส่งคำเชิญถึง ${u.email} แล้ว (เข้าคิวอีเมล)`);
      } else {
        await usersApi.edit(mode.email, { name, roles, units, ...(expires ? { expires_at: expires } : { clear_expiry: !!detail?.expires_at }) });
        onSaved("บันทึกแล้ว");
      }
    } catch (e) {
      toast((e as Error).message, "err");
      setBusy(false);
    }
  }

  const title = mode.kind === "add" ? "เพิ่มผู้ใช้" : mode.kind === "invite" ? "เชิญผู้ใช้ภายนอก" : readOnly ? "ข้อมูลผู้ใช้" : "แก้ไขผู้ใช้";
  const ready = mode.kind === "add" ? (picked || email.includes("@")) && roles.length > 0
    : mode.kind === "invite" ? email.includes("@") && name.trim() && expires && roles.length > 0
    : !readOnly;
  return (
    <Modal
      open
      size="lg"
      title={title}
      onClose={onClose}
      foot={
        <>
          <button type="button" className="btn" onClick={onClose}>{readOnly ? "ปิด" : "ยกเลิก"}</button>
          {!readOnly && <button type="button" className="btn primary" disabled={busy || !ready} onClick={save}>{mode.kind === "invite" ? "ส่งคำเชิญ" : "บันทึก"}</button>}
        </>
      }
    >
      <div className="stack">
        {mode.kind === "add" && (
          <>
            <Field label={<>ค้นหาบุคลากร {staffSample && <SampleData source="HURIS" />}</>} pulled="HURIS">
              {(id) => <input id={id} className="inp" value={staffQ} onChange={(e) => { setStaffQ(e.target.value); setPicked(null); }} placeholder="พิมพ์ชื่อหรือรหัสบุคลากร อย่างน้อย 2 ตัวอักษร" />}
            </Field>
            {picked ? (
              <Note kind="ok">เลือก {picked.title_short}{picked.name_th} · {picked.faculty} · {picked.email} <button type="button" className="link-btn" onClick={() => setPicked(null)}>เปลี่ยน</button></Note>
            ) : shownStaff.length > 0 && (
              <div className="stack" style={{ gap: 4 }}>
                {shownStaff.map((s) => (
                  <button key={s.pid} type="button" className="card" style={{ padding: "8px 12px", textAlign: "left", cursor: "pointer" }} onClick={() => setPicked(s)}>
                    <b>{s.title_short}{s.name_th}</b> <span className="small faint">{s.pid} · {s.faculty} · {s.email}</span>
                  </button>
                ))}
              </div>
            )}
            {!picked && <span className="small faint">หรือกรอกเอง (บุคลากรที่ยังไม่อยู่ในข้อมูล HURIS)</span>}
          </>
        )}
        {(mode.kind === "invite" || (mode.kind === "add" && !picked)) && (
          <div className="form-grid">
            <Field label={mode.kind === "invite" ? "อีเมลผู้ได้รับเชิญ" : "อีเมล"}>{(id) => <input id={id} className="inp" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={mode.kind === "invite" ? "name@example.com" : "[buasri id]@g.swu.ac.th"} />}</Field>
            <Field label="ชื่อ-นามสกุล">{(id) => <input id={id} className="inp" value={name} onChange={(e) => setName(e.target.value)} />}</Field>
            {mode.kind === "add" && <Field label="รหัสนิสิต (บัญชีนิสิต)" pulled="SUPREME" hint="ผูกบัญชีกับนิสิตเพื่อดู Skill Portfolio และ Skill Transcript ของตนเอง · ชื่อดึงจาก SUPREME ถ้าเว้นว่าง">{(id) => <input id={id} className="inp num" value={sid} onChange={(e) => { setSid(e.target.value.replace(/\D/g, "")); if (e.target.value && !roles.length) setRoles(["student"]); }} placeholder="เช่น 6600100028" />}</Field>}
          </div>
        )}
        {mode.kind === "edit" && detail && (
          <div className="form-grid">
            <Field label="ชื่อ-นามสกุล">{(id) => <input id={id} className="inp" value={name} disabled={readOnly} onChange={(e) => setName(e.target.value)} />}</Field>
            <Field label="อีเมล">{(id) => <input id={id} className="inp" value={detail.email} disabled />}</Field>
            {detail.sid && <Field label="รหัสนิสิต">{(id) => <input id={id} className="inp num" value={detail.sid ?? ""} disabled />}</Field>}
          </div>
        )}
        {mode.kind === "edit" && !detail ? <span className="small faint">กำลังโหลด…</span> : (
          <>
            <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 6 }} disabled={readOnly || self}>
              <legend className="lbl">กลุ่มสิทธิ์ (เลือกได้หลายกลุ่ม){self && " · แก้กลุ่มของบัญชีตัวเองไม่ได้"}</legend>
              <div className="row" style={{ gap: "6px 16px" }}>
                {opts.roles.map((r) => <Check key={r.id} checked={roles.includes(r.id)} onChange={(on) => setRoles((l) => flip(l, r.id, on))}>{r.name}</Check>)}
              </div>
            </fieldset>
            <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 6 }} disabled={readOnly}>
              <legend className="lbl">หน่วยงาน/หลักสูตรที่มองเห็น (เลือกได้หลายรายการ) {opts.units_sample && <SampleData source="SUPREME" />}</legend>
              <div className="row" style={{ gap: "6px 16px", maxHeight: 180, overflow: "auto", border: "1px solid var(--line)", borderRadius: 10, padding: 10 }}>
                {opts.units.map((x) => <Check key={x} checked={units.includes(x)} onChange={(on) => setUnits((l) => flip(l, x, on))}>{x}</Check>)}
              </div>
            </fieldset>
            <Field label={mode.kind === "invite" ? "สิทธิ์ใช้งานถึงวันที่" : "สิทธิ์ใช้งานถึงวันที่ (เว้นว่าง = ไม่มีวันสิ้นสุด)"}>
              {(id) => <input id={id} className="inp" type="date" value={expires} disabled={readOnly || self} onChange={(e) => setExpires(e.target.value)} style={{ maxWidth: 220 }} />}
            </Field>
          </>
        )}
        {mode.kind === "invite" && <Note kind="info">ระบบส่งคำเชิญเข้าคิวอีเมล · การเข้าสู่ระบบด้วยรหัสยืนยันทางอีเมลจะเปิดใช้ในงานถัดไป</Note>}
        {detail && detail.events.length > 0 && (
          <div className="stack" style={{ gap: 4 }}>
            <span className="lbl">ประวัติการแก้ไข</span>
            {detail.events.map((e, i) => (
              <span key={i} className="small">{fmtTime(e.ts)} · {e.by ?? "–"} · {({ create: "เพิ่มผู้ใช้", invite: "เชิญ", update: "แก้ไข", suspend: "ระงับ", enable: "เปิดใช้", cli_add: "เพิ่มทาง server", cli_set: e.detail.password_set ? "ตั้งรหัสผ่านทาง server" : "แก้ทาง server", cli_disable: "ระงับทาง server", cli_enable: "เปิดใช้ทาง server" } as Record<string, string>)[e.action] ?? e.action}</span>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
