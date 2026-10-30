"use client";

// skill-assign (mock · US-M3-02): who sets the skills of each curriculum, more than one person,
// each with a role that starts their rights (the mock's SKROLE), four rights to tick (SKP) and
// a scope: the whole curriculum or the courses chosen. New people get an e-mail. The tab
// "สิทธิ์เพิ่ม Skill ในฐานข้อมูล" names the groups or people who may add skills of each side.
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { skillsApi, usersApi, type SkillAssign, type SkillAssignOverview, type SkillDbPerm, type Staff } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { CATS } from "@/lib/skills";
import { Note, PageHead, Pill } from "@/components/ui";
import { Check, DataTable, Field, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, Tabs, useToast, type Column } from "@/components/kit";

type Item = SkillAssignOverview["items"][number];
const SCOPE_TH: Record<string, string> = { all: "ทั้งมหาวิทยาลัย", faculty: "คณะ/ส่วนงาน", program: "เฉพาะหลักสูตรที่รับผิดชอบ" };

export default function SkillAssignPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const canEdit = canMenu(perms, "s2", "edit");
  const toast = useToast();
  const [tab, setTab] = useState<"cur" | "db">("cur");
  const [d, setD] = useState<SkillAssignOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [fac, setFac] = useState("");
  const [edit, setEdit] = useState<Item | null>(null);
  const load = () => skillsApi.assign().then(setD).catch((e) => setErr((e as Error).message));
  useEffect(() => { skillsApi.assign().then(setD).catch((e) => setErr((e as Error).message)); }, []);
  const facs = useMemo(() => [...new Set((d?.items ?? []).map((i) => i.faculty).filter(Boolean) as string[])].sort(), [d]);
  const columns: Column<Item>[] = [
    { key: "name", label: "หลักสูตร", sort: (i) => i.name_th, render: (i) => <><b>{i.name_th}</b><div className="small faint">{i.faculty}</div></> },
    { key: "who", label: "ผู้รับผิดชอบ", render: (i) => i.assign.length ? <div className="small">{i.assign.map((a) => <div key={a.pid}>{a.name} · {d?.roles[a.role]?.label}</div>)}</div> : <span className="faint">—</span> },
    { key: "scope", label: "ขอบเขต", render: (i) => <span className="small">{i.assign.length ? (i.assign.some((a) => a.scope === "all") ? "ทั้งหลักสูตร" : "") + (i.assign.some((a) => a.scope === "courses") ? ` รายวิชา ${new Set(i.assign.flatMap((a) => a.courses)).size} วิชา` : "") : "—"}</span> },
    { key: "perms", label: "สิทธิ์", render: (i) => <div className="row" style={{ gap: 4 }}>{Object.keys(d?.perms ?? {}).filter((p) => i.assign.some((a) => a.perms.includes(p))).map((p) => <Pill key={p}>{d!.perms[p].split(" (")[0]}</Pill>)}</div> },
    { key: "st", label: "สถานะ", render: (i) => <Pill kind={i.assign.length ? "ok" : "red"}>{i.assign.length ? "กำหนดแล้ว" : "ยังไม่กำหนด"}</Pill> },
    { key: "go", label: "", render: (i) => <button type="button" className="btn xs" onClick={() => setEdit(i)}>{canEdit ? "กำหนด" : "ดู"}</button> },
  ];
  return (
    <>
      <PageHead crumb={["Skill Transcript", "ตั้งค่าการบันทึกข้อมูล"]} title="กำหนดผู้บันทึกแผนการประเมิน Skill"
        sub="กำหนดว่าใครเพิ่ม Skill ในฐานข้อมูลได้ และใครเป็นผู้กำหนด Skill Mapping ของแต่ละหลักสูตร/รายวิชา (กำหนดได้มากกว่า 1 คน)" />
      {err && <Note kind="warn">{err}</Note>}
      <Tabs items={[["cur", "ผู้กำหนด Skill รายหลักสูตร/รายวิชา"], ["db", "สิทธิ์เพิ่ม Skill ในฐานข้อมูล"]] as const} value={tab} onChange={setTab} />
      {tab === "cur" && (
        <>
          <KpiRow>
            <Kpi label="หลักสูตรทั้งหมด" value={d?.kpi.total ?? "–"} sub="ในขอบเขตข้อมูลของบัญชีนี้" />
            <Kpi label="กำหนดผู้รับผิดชอบแล้ว" value={d?.kpi.assigned ?? "–"} />
            <Kpi label="ยังไม่กำหนด" value={d?.kpi.none ?? "–"} />
            <Kpi label="ผู้รับผิดชอบ (คน)" value={d?.kpi.people ?? "–"} />
          </KpiRow>
          <DataTable rows={(d?.items ?? []).filter((i) => !fac || i.faculty === fac)} columns={columns} rowKey={(i) => i.id} search={q} unit="หลักสูตร"
            searchText={(i) => `${i.name_th} ${i.assign.map((a) => a.name).join(" ")}`} empty={d ? "ไม่พบหลักสูตร" : "กำลังโหลด…"}
            toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นหาหลักสูตรหรือผู้รับผิดชอบ" /><SelectFilter label="คณะ" value={fac} options={facs} onChange={setFac} /></Filters>} />
          <Note kind="info">ผู้รับผิดชอบที่ได้รับมอบหมายต้องอยู่ในกลุ่มสิทธิ์ที่เห็นเมนู &quot;กำหนด Skill ตามหลักสูตร&quot; และ &quot;กำหนดรายวิชาประเมิน Skill&quot; (เช่น ผู้ตรวจสอบระดับหลักสูตร) จึงจะเปิดหน้านั้นได้</Note>
        </>
      )}
      {tab === "db" && <DbPerms canEdit={canEdit} />}
      {edit && d && <AssignModal item={edit} d={d} readOnly={!canEdit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); toast("บันทึกการกำหนดผู้รับผิดชอบแล้ว"); }} />}
    </>
  );
}

function StaffSearch({ onPick, exclude }: { onPick: (s: Staff) => void; exclude: string[] }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Staff[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => { usersApi.staff(q).then((r) => setFound(r.items)).catch(() => setFound([])); }, 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="stack" style={{ gap: 4 }}>
      <input className="inp" aria-label="ค้นบุคลากร" placeholder="พิมพ์ชื่อหรือรหัสบุคลากร (ระบบบุคลากร) เพื่อเพิ่ม" value={q} onChange={(e) => setQ(e.target.value)} />
      {q.trim().length >= 2 && found.filter((s) => !exclude.includes(s.pid)).map((s) => (
        <button key={s.pid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => { onPick(s); setQ(""); }}>
          <b>{s.title_short}{s.name_th}</b> <span className="small faint">{s.pid} · {s.faculty}</span>
        </button>
      ))}
    </div>
  );
}

function AssignModal({ item, d, readOnly, onClose, onSaved }: { item: Item; d: SkillAssignOverview; readOnly: boolean; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [rows, setRows] = useState<SkillAssign[]>(item.assign);
  const set = (i: number, patch: Partial<SkillAssign>) => setRows((x) => x.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  async function save() {
    try { await skillsApi.setAssign(item.id, rows); onSaved(); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <Modal open size="xl" title={`กำหนดผู้รับผิดชอบ Skill · ${item.name_th}`} onClose={onClose}
      foot={<><span className="small muted" style={{ marginRight: "auto" }}>{rows.length} คน</span><button type="button" className="btn" onClick={onClose}>ปิด</button>{!readOnly && <button type="button" className="btn primary" onClick={save}>บันทึกการกำหนด</button>}</>}>
      <div className="stack">
        {!readOnly && <StaffSearch exclude={rows.map((r) => r.pid)} onPick={(s) => setRows((x) => [...x, { pid: s.pid, name: `${s.title_short ?? ""}${s.name_th}`, role: "cur", perms: [...d.roles.cur.perms], scope: "all", courses: [] }])} />}
        <span className="small faint">เลือกบทบาทเพื่อตั้งสิทธิ์เริ่มต้น แล้วปรับสิทธิ์และขอบเขตของแต่ละคนได้อิสระ</span>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ผู้รับผิดชอบ</th><th>บทบาท</th>{Object.entries(d.perms).map(([k, l]) => <th key={k} className="c" style={{ maxWidth: 120, whiteSpace: "normal", fontSize: 12 }}>{l}</th>)}<th>ขอบเขต</th><th /></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.pid} style={{ verticalAlign: "top" }}>
                  <td><b>{r.name ?? r.pid}</b><div className="small faint">{r.pid}</div></td>
                  <td><select className="inp" aria-label={`บทบาท ${r.name}`} disabled={readOnly} value={r.role} onChange={(e) => { const role = d.roles[e.target.value]; set(i, { role: e.target.value, perms: [...role.perms], scope: role.scope }); }}>{Object.entries(d.roles).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></td>
                  {Object.keys(d.perms).map((p) => <td key={p} className="c"><input type="checkbox" aria-label={`${r.name} ${d.perms[p]}`} disabled={readOnly} checked={r.perms.includes(p)} onChange={(e) => set(i, { perms: e.target.checked ? [...r.perms, p] : r.perms.filter((x) => x !== p) })} style={{ width: 18, height: 18 }} /></td>)}
                  <td style={{ minWidth: 200 }}>
                    <select className="inp" aria-label={`ขอบเขต ${r.name}`} disabled={readOnly} value={r.scope} onChange={(e) => set(i, { scope: e.target.value as SkillAssign["scope"] })}><option value="all">ทั้งหลักสูตร</option><option value="courses">เฉพาะรายวิชาที่เลือก</option></select>
                    {r.scope === "courses" && <div className="stack" style={{ gap: 2, marginTop: 4 }}>{item.courses.map((c) => <Check key={c} disabled={readOnly} checked={r.courses.includes(c)} onChange={(v) => set(i, { courses: v ? [...r.courses, c] : r.courses.filter((x) => x !== c) })}>{c}</Check>)}{!item.courses.length && <span className="small faint">หลักสูตรนี้ยังไม่มีรายวิชา</span>}</div>}
                  </td>
                  <td>{!readOnly && <button type="button" className="btn xs" onClick={() => setRows((x) => x.filter((_, k) => k !== i))}>นำออก</button>}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="empty">ยังไม่มีผู้รับผิดชอบ</td></tr>}
            </tbody>
          </table>
        </div>
        <Note kind="warn">ระบบแจ้งเตือนผู้ได้รับสิทธิ์ใหม่ทางอีเมล · ผู้ที่ได้สิทธิ์ &quot;เฉพาะรายวิชาที่เลือก&quot; กำหนด Mapping ได้เฉพาะรายวิชานั้น</Note>
      </div>
    </Modal>
  );
}

function DbPerms({ canEdit }: { canEdit: boolean }) {
  const toast = useToast();
  const [rows, setRows] = useState<SkillDbPerm[] | null>(null);
  const [roleNames, setRoleNames] = useState<Record<string, string>>({});
  const [add, setAdd] = useState<{ who: string; cats: string[]; unit_scope: SkillDbPerm["unit_scope"] } | null>(null);
  useEffect(() => { skillsApi.dbPerms().then((r) => { setRows(r.items); setRoleNames(r.groups); }).catch((e) => toast((e as Error).message, "err")); }, [toast]);
  async function save() {
    if (!add) return;
    try { setRows(await skillsApi.addDbPerm({ ...add, cats: add.cats as SkillDbPerm["cats"] })); setAdd(null); toast("เพิ่มผู้มีสิทธิ์แล้ว"); } catch (e) { toast((e as Error).message, "err"); }
  }
  return (
    <section className="card">
      <div className="between pad"><span className="muted">ผู้ใช้หรือกลุ่มสิทธิ์ที่เพิ่ม/แก้ไขรายการในฐานข้อมูล Skill ได้ (ส่วนกลางกำหนด)</span>{canEdit && <button type="button" className="btn primary sm" onClick={() => setAdd({ who: "role:curator", cats: ["SS", "E", "C"], unit_scope: "program" })}>เพิ่มผู้มีสิทธิ์</button>}</div>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ผู้ใช้ / กลุ่มสิทธิ์</th><th>ด้านที่เพิ่มได้</th><th>ขอบเขตหน่วยงาน</th><th /></tr></thead>
        <tbody>
          {(rows ?? []).map((r) => <tr key={r.id}><td><b>{r.label}</b> <span className="small faint">{r.kind === "role" ? "กลุ่มสิทธิ์" : "ผู้ใช้"}</span></td><td><div className="row" style={{ gap: 4 }}>{r.cats.map((c) => <Pill key={c}>{c}</Pill>)}</div></td><td className="small">{SCOPE_TH[r.unit_scope]}</td>
            <td>{canEdit && <button type="button" className="btn xs" onClick={() => skillsApi.delDbPerm(r.id).then(setRows).catch((e) => toast((e as Error).message, "err"))}>ลบ</button>}</td></tr>)}
          {rows && !rows.length && <tr><td colSpan={4} className="empty">ยังไม่มี · เฉพาะส่วนกลางเพิ่ม Skill ได้</td></tr>}
        </tbody></table></div>
      {add && (
        <Modal open title="สิทธิ์เพิ่ม Skill ในฐานข้อมูล" onClose={() => setAdd(null)} foot={<><button type="button" className="btn" onClick={() => setAdd(null)}>ยกเลิก</button><button type="button" className="btn primary" onClick={save}>บันทึก</button></>}>
          <div className="stack">
            <Field label="กลุ่มสิทธิ์" full>{(id) => <select id={id} className="inp" value={add.who.startsWith("role:") ? add.who : ""} onChange={(e) => setAdd({ ...add, who: e.target.value })}><option value="">— ผู้ใช้รายคน (ค้นด้านล่าง) —</option>{Object.entries(roleNames).map(([k, v]) => <option key={k} value={`role:${k}`}>{v}</option>)}</select>}</Field>
            {!add.who.startsWith("role:") && <><StaffSearch exclude={[]} onPick={(s) => setAdd({ ...add, who: `pid:${s.pid}` })} />{add.who && <span className="small">เลือก {add.who.slice(4)}</span>}</>}
            <div className="field"><span className="lbl">ด้านที่เพิ่มได้</span><div className="row">{CATS.map((c) => <Check key={c} checked={add.cats.includes(c)} onChange={(v) => setAdd({ ...add, cats: v ? [...add.cats, c] : add.cats.filter((x) => x !== c) })}>{c}</Check>)}</div></div>
            <Field label="ขอบเขตหน่วยงาน" full>{(id) => <select id={id} className="inp" value={add.unit_scope} onChange={(e) => setAdd({ ...add, unit_scope: e.target.value as SkillDbPerm["unit_scope"] })}>{Object.entries(SCOPE_TH).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</Field>
            <span className="small faint">&quot;ทั้งมหาวิทยาลัย&quot; เพิ่ม Skill ขอบเขตส่วนกลาง มศว ได้ด้วย</span>
          </div>
        </Modal>
      )}
    </section>
  );
}
