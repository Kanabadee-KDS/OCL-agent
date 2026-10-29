"use client";

// Field editors of the คู่มือหลักสูตร form, one per `kind` of the API's spec
// (ocl_api.curriculum_form). Values are read and written by the field's `path`.
import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { curriculumForm, personsApi, usersApi, type FormField, type PersonPick, type Staff, type TeacherCheck } from "@/lib/api";
import { asInput, columnTotals, fromInput, getPath } from "@/lib/form";
import { Note, Pill } from "@/components/ui";
import { Check, Pulled, useToast } from "@/components/kit";

type Row = Record<string, unknown>;
export type Ctx = {
  draftId: string;
  sections: Record<string, Record<string, unknown>>; // all sections, for the read-only copies
  readOnly: boolean;
  canAddOption: boolean;
  onAddOption: (key: string, value: string) => Promise<void>;
  onBook: (file: File) => Promise<void>;
};

export function FieldLabel({ f, required }: { f: FormField; required: boolean }) {
  return (
    <span className="lbl">
      {f.label}{required && <b style={{ color: "var(--red)" }}> *</b>}
      {f.source && f.source !== "เล่ม" && <Pulled src={f.source} />}
    </span>
  );
}

export function Field({ f, value, onChange, ctx, required }: { f: FormField; value: unknown; onChange: (v: unknown) => void; ctx: Ctx; required: boolean }) {
  const wide = ["table", "teachers", "teachers_view", "plan", "tags", "textarea", "book", "master"].includes(f.kind);
  return (
    <div className={`field ${wide ? "full" : ""}`}>
      <FieldLabel f={f} required={required} />
      <Editor f={f} value={value} onChange={onChange} ctx={ctx} />
      {f.hint && <span className="small faint">{f.hint}</span>}
    </div>
  );
}

function Editor({ f, value, onChange, ctx }: { f: FormField; value: unknown; onChange: (v: unknown) => void; ctx: Ctx }) {
  const ro = ctx.readOnly;
  switch (f.kind) {
    case "textarea":
      return <textarea className="inp" rows={3} style={{ height: "auto", padding: 8 }} aria-label={f.label} disabled={ro} value={asInput(value, "text")} onChange={(e) => onChange(fromInput(e.target.value, "text"))} />;
    case "int":
    case "date":
    case "text":
      return <input className="inp" aria-label={f.label} disabled={ro} type={f.kind === "int" ? "number" : f.kind === "date" ? "date" : "text"} value={asInput(value, f.kind)} onChange={(e) => onChange(fromInput(e.target.value, f.kind))} />;
    case "bool":
      return <Check checked={value === true} disabled={ro} onChange={onChange}>ใช่</Check>;
    case "enum":
      return <EnumEditor f={f} value={value} onChange={onChange} ctx={ctx} />;
    case "tags":
      return (
        <div className="row" style={{ gap: "6px 16px" }}>
          {(f.options ?? []).map((o) => {
            const list = Array.isArray(value) ? (value as string[]) : [];
            return <Check key={o} checked={list.includes(o)} disabled={ro} onChange={(on) => onChange(on ? [...list, o] : list.filter((x) => x !== o))}>{o}</Check>;
          })}
          {f.lookup && ctx.canAddOption && <AddOption onAdd={(v) => ctx.onAddOption(f.lookup_key, v)} />}
        </div>
      );
    case "table":
      return <TableEditor f={f} value={value} onChange={onChange} ctx={ctx} />;
    case "teachers":
      return <TeachersEditor value={value} onChange={onChange} ctx={ctx} />;
    case "teachers_view":
      return <TeachersView rows={(getPath(ctx.sections["0"], "teachers.teachers") as Row[]) ?? []} />;
    case "plan":
      return <PlanEditor value={value} onChange={onChange} ctx={ctx} />;
    case "book":
      return <BookEditor value={value} ctx={ctx} />;
    case "master":
      return <Master s0={ctx.sections["0"]} />;
    default:
      return <span className="small faint">({f.kind})</span>;
  }
}

function EnumEditor({ f, value, onChange, ctx }: { f: FormField; value: unknown; onChange: (v: unknown) => void; ctx: Ctx }) {
  const opts = f.options ?? [];
  const v = asInput(value, "text");
  return (
    <div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
      <select className="inp" aria-label={f.label} disabled={ctx.readOnly} value={v} onChange={(e) => onChange(e.target.value || null)} style={{ flex: 1 }}>
        <option value="">— เลือก —</option>
        {v && !opts.includes(v) && <option value={v}>{v} (จากเล่ม)</option>}
        {opts.map((o) => <option key={o}>{o}</option>)}
      </select>
      {f.lookup && ctx.canAddOption && <AddOption onAdd={(x) => ctx.onAddOption(f.lookup_key, x)} />}
    </div>
  );
}

/** The administrators add an option to a list (BRD 01 US-M1-04: basic data they can extend). */
function AddOption({ onAdd }: { onAdd: (v: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [v, setV] = useState("");
  if (!open) return <button type="button" className="btn xs" title="เพิ่มตัวเลือก (ผู้ดูแลระบบ)" onClick={() => setOpen(true)}>+ ตัวเลือก</button>;
  return (
    <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
      <input className="inp" style={{ width: 160 }} aria-label="ตัวเลือกใหม่" value={v} onChange={(e) => setV(e.target.value)} autoFocus />
      <button type="button" className="btn xs primary" disabled={!v.trim()} onClick={async () => { await onAdd(v.trim()); setV(""); setOpen(false); }}>เพิ่ม</button>
      <button type="button" className="btn xs" onClick={() => setOpen(false)}>ยกเลิก</button>
    </span>
  );
}

function Cell({ c, value, onChange, disabled }: { c: FormField; value: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  if (c.kind === "enum") {
    const v = asInput(value, "text");
    return (
      <select className="inp" aria-label={c.label} disabled={disabled} value={v} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>
        {v && !(c.options ?? []).includes(v) && <option value={v}>{v}</option>}
        {(c.options ?? []).map((o) => <option key={o}>{o}</option>)}
      </select>
    );
  }
  return <input className="inp" aria-label={c.label} disabled={disabled} type={c.kind === "int" ? "number" : c.kind === "date" ? "date" : "text"} value={asInput(value, c.kind)} onChange={(e) => onChange(fromInput(e.target.value, c.kind))} />;
}

function TableEditor({ f, value, onChange, ctx }: { f: FormField; value: unknown; onChange: (v: unknown) => void; ctx: Ctx }) {
  const rows = (Array.isArray(value) ? value : []) as Row[];
  const cols = f.columns ?? [];
  const set = (i: number, key: string, v: unknown) => onChange(rows.map((r, k) => (k === i ? { ...r, [key]: v } : r)));
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th style={{ width: 40 }}>#</th>{cols.map((c) => <th key={c.key}>{c.label}</th>)}{!ctx.readOnly && <th />}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="num">{i + 1}</td>
                {cols.map((c) => <td key={c.key}><Cell c={c} value={r[c.key]} disabled={ctx.readOnly} onChange={(v) => set(i, c.key, v)} /></td>)}
                {!ctx.readOnly && <td><button type="button" className="btn xs" aria-label={`ลบแถว ${i + 1}`} onClick={() => onChange(rows.filter((_, k) => k !== i))}>ลบ</button></td>}
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={cols.length + 2} className="small faint">ยังไม่มีรายการ</td></tr>}
          </tbody>
        </table>
      </div>
      {!ctx.readOnly && (
        <div className="row">
          <button type="button" className="btn xs" onClick={() => onChange([...rows, {}])}>เพิ่มแถว</button>
          {cols.filter((c) => c.lookup && ctx.canAddOption).map((c) => <span key={c.key} className="small">{c.label}: <AddOption onAdd={(v) => ctx.onAddOption(c.lookup_key, v)} /></span>)}
        </div>
      )}
    </div>
  );
}

const LEVELS = ["ตรี", "โท", "เอก"];

function TeachersEditor({ value, onChange, ctx }: { value: unknown; onChange: (v: unknown) => void; ctx: Ctx }) {
  const rows = (Array.isArray(value) ? value : []) as Row[];
  const ro = ctx.readOnly;
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Staff[]>([]);
  const [xq, setXq] = useState("");
  const [xfound, setXfound] = useState<PersonPick[]>([]);
  const [check, setCheck] = useState<TeacherCheck | null>(null);
  const toast = useToast();
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => { usersApi.staff(q).then((r) => setFound(r.items)).catch(() => setFound([])); }, 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    if (xq.trim().length < 2) return;
    const t = setTimeout(() => { personsApi.search(xq).then(setXfound).catch(() => setXfound([])); }, 250);
    return () => clearTimeout(t);
  }, [xq]);
  const shown = q.trim().length >= 2 ? found : [];
  const xshown = xq.trim().length >= 2 ? xfound : [];
  const renumber = (list: Row[]) => list.map((r, i) => ({ ...r, order: i + 1 }));
  const set = (i: number, key: string, v: unknown) => onChange(rows.map((r, k) => (k === i ? { ...r, [key]: v } : r)));
  const move = (i: number, by: -1 | 1) => {
    const j = i + by;
    if (j < 0 || j >= rows.length) return;
    const out = [...rows];
    [out[i], out[j]] = [out[j], out[i]];
    onChange(renumber(out));
  };
  function addStaff(s: Staff & { education?: unknown[] }) {
    const edu = (s.education ?? []) as unknown[][];
    const top = edu.some((e) => e[0] === "ปริญญาเอก") ? "เอก" : edu.some((e) => e[0] === "ปริญญาโท") ? "โท" : "ตรี";
    onChange(renumber([...rows, { name: s.name_th, rank: (s as Row).position ?? s.title_short, pid: s.pid, highest_level: top, responsible: false, group: null }]));
    setQ("");
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>ลำดับ</th><th>ชื่อ-นามสกุล</th><th>ตำแหน่งทางวิชาการ</th><th>คุณวุฒิสูงสุด</th><th>ผู้รับผิดชอบ</th><th>แขนง</th><th>ประธาน</th>{!ro && <th />}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="num">{i + 1}</td>
                <td><input className="inp" aria-label={`อาจารย์ ${i + 1}: ชื่อ`} disabled={ro} value={asInput(r.name, "text")} onChange={(e) => set(i, "name", e.target.value)} />{typeof r.pid === "string" && <span className="small faint"> {r.pid}</span>}{typeof r.xid === "string" && <span className="small faint"> บุคคลภายนอก {r.xid}</span>}</td>
                <td><input className="inp" aria-label={`อาจารย์ ${i + 1}: ตำแหน่ง`} disabled={ro} value={asInput(r.rank, "text")} onChange={(e) => set(i, "rank", e.target.value)} /></td>
                <td><select className="inp" aria-label={`อาจารย์ ${i + 1}: คุณวุฒิ`} disabled={ro} value={asInput(r.highest_level, "text")} onChange={(e) => set(i, "highest_level", e.target.value || null)}><option value="">—</option>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></td>
                <td><input type="checkbox" aria-label={`อาจารย์ ${i + 1}: ผู้รับผิดชอบ`} disabled={ro} checked={r.responsible === true} onChange={(e) => set(i, "responsible", e.target.checked)} /></td>
                <td><input className="inp" aria-label={`อาจารย์ ${i + 1}: แขนง`} disabled={ro} value={asInput(r.group, "text")} onChange={(e) => set(i, "group", e.target.value || null)} /></td>
                <td><input type="radio" name="chair" aria-label={`อาจารย์ ${i + 1}: ประธาน`} disabled={ro} checked={r.chair === true} onChange={() => onChange(rows.map((x, k) => ({ ...x, chair: k === i })))} /></td>
                {!ro && (
                  <td>
                    <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                      <button type="button" className="btn xs" aria-label={`เลื่อนอาจารย์ ${i + 1} ขึ้น`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                      <button type="button" className="btn xs" aria-label={`เลื่อนอาจารย์ ${i + 1} ลง`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}>↓</button>
                      <button type="button" className="btn xs" aria-label={`ลบอาจารย์ ${i + 1}`} onClick={() => onChange(renumber(rows.filter((_, k) => k !== i)))}>ลบ</button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={8} className="small faint">ยังไม่มีอาจารย์</td></tr>}
          </tbody>
        </table>
      </div>
      {!ro && (
        <div className="stack" style={{ gap: 4 }}>
          <div className="row" style={{ gap: 8 }}>
            <input className="inp" style={{ maxWidth: 320 }} aria-label="ค้นบุคลากรจาก HURIS" placeholder="เพิ่มจาก HURIS: พิมพ์ชื่อหรือรหัสบุคลากร" value={q} onChange={(e) => setQ(e.target.value)} />
            <input className="inp" style={{ maxWidth: 320 }} aria-label="ค้นทะเบียนบุคคลภายนอก" placeholder="เพิ่มบุคคลภายนอก: พิมพ์ชื่อหรือหน่วยงาน" value={xq} onChange={(e) => setXq(e.target.value)} />
          </div>
          {xshown.map((x) => (
            <button key={x.xid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }}
              onClick={() => { onChange(renumber([...rows, { name: x.name, rank: x.rank, xid: x.xid, highest_level: x.highest_level, org: x.org, responsible: false, group: null }])); setXq(""); }}>
              <b>{x.name}</b> <span className="small faint">{x.xid} · {x.kind} · {x.org}</span>
            </button>
          ))}
          {xq.trim().length >= 2 && !xshown.length && <span className="small faint">ไม่พบในทะเบียน · เพิ่มที่เมนู <Link href="/persons">บริหารบุคคลภายนอก</Link> ก่อน</span>}
          {shown.map((s) => (
            <button key={s.pid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => addStaff(s)}>
              <b>{s.title_short}{s.name_th}</b> <span className="small faint">{s.pid} · {s.faculty}</span>
            </button>
          ))}
        </div>
      )}
      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn xs" onClick={() => curriculumForm.teacherCheck(ctx.draftId).then(setCheck).catch((e) => toast((e as Error).message, "err"))}>ตรวจคุณสมบัติและความซ้ำซ้อน</button>
        <span className="small faint">ตรวจจากข้อมูลที่บันทึกแล้ว · เกณฑ์เบื้องต้น เกณฑ์เต็มอยู่ในการประเมินหลักสูตร</span>
      </div>
      {check && (
        <Note kind={check.issues.length || check.duplicates.length ? "warn" : "ok"}>
          ผู้รับผิดชอบ {check.responsible} คน (ต้องอย่างน้อย {check.required})
          {check.issues.map((x) => <div key={x}>· {x}</div>)}
          {check.duplicates.map((d) => <div key={d.name + d.id}>· {d.name} เป็นผู้รับผิดชอบใน {d.curriculum} ด้วย</div>)}
          {!check.issues.length && !check.duplicates.length && <div>ผ่านเกณฑ์เบื้องต้น</div>}
        </Note>
      )}
    </div>
  );
}

function TeachersView({ rows }: { rows: Row[] }) {
  if (!rows.length) return <span className="small faint">ยังไม่มีรายชื่อในหมวด 0.2</span>;
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr><th>ลำดับ</th><th>ชื่อ-นามสกุล</th><th>ตำแหน่ง</th><th>คุณวุฒิสูงสุด</th><th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}><td className="num">{i + 1}</td><td>{asInput(r.name, "text")}{r.responsible === true && " *"}</td><td className="small">{asInput(r.rank, "text")}</td><td className="small">{asInput(r.highest_level, "text")}</td><td>{r.chair === true && <Pill kind="info">ประธาน</Pill>}</td></tr>
          ))}
        </tbody>
      </table>
      <span className="small faint">* = อาจารย์ผู้รับผิดชอบหลักสูตร · แก้ที่หมวด 0.2</span>
    </div>
  );
}

type Plan = { years?: string[]; rows?: { label?: string; values?: (number | null)[] }[]; graduates?: (number | null)[] };

function PlanEditor({ value, onChange, ctx }: { value: unknown; onChange: (v: unknown) => void; ctx: Ctx }) {
  const plans = (Array.isArray(value) ? value : []) as Plan[];
  const values0 = (getPath(ctx.sections["0"], "info.values") ?? {}) as Row;
  const start = Number(values0.start_year) || new Date().getFullYear() + 543;
  const nYears = Number(values0.duration_years) || 4;
  const plan: Plan = plans[0] ?? {
    years: Array.from({ length: 5 }, (_, i) => String(start + i)),
    rows: Array.from({ length: nYears }, (_, i) => ({ label: `ชั้นปีที่ ${i + 1}`, values: [0, 0, 0, 0, 0] })),
    graduates: [0, 0, 0, 0, 0],
  };
  const years = plan.years ?? [];
  const rows = plan.rows ?? [];
  const put = (p: Plan) => onChange([{ ...p, total: columnTotals(p.rows ?? [], years.length) }, ...plans.slice(1)]);
  const setCell = (ri: number, yi: number, v: number | null) => put({ ...plan, rows: rows.map((r, k) => (k === ri ? { ...r, values: years.map((_, j) => (j === yi ? v : r.values?.[j] ?? 0)) } : r)) });
  const totals = columnTotals(rows, years.length);
  const sum = (plan.rows?.[0]?.values ?? []).reduce<number>((a, b) => a + (Number(b) || 0), 0);
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>จำนวนนิสิต (คน)</th>{years.map((y) => <th key={y} className="r">{y}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>
                <td>{r.label ?? `ชั้นปีที่ ${ri + 1}`}</td>
                {years.map((y, yi) => <td key={y}><input className="inp num" type="number" min={0} style={{ width: 80 }} aria-label={`${r.label ?? ri + 1} ปี ${y}`} disabled={ctx.readOnly} value={asInput(r.values?.[yi], "int")} onChange={(e) => setCell(ri, yi, fromInput(e.target.value, "int") as number | null)} /></td>)}
              </tr>
            ))}
            <tr><td><b>รวม</b></td>{totals.map((t, i) => <td key={i} className="r num"><b>{t}</b></td>)}</tr>
            <tr>
              <td>คาดว่าจะสำเร็จการศึกษา</td>
              {years.map((y, yi) => <td key={y}><input className="inp num" type="number" min={0} style={{ width: 80 }} aria-label={`สำเร็จ ปี ${y}`} disabled={ctx.readOnly} value={asInput(plan.graduates?.[yi], "int")} onChange={(e) => put({ ...plan, graduates: years.map((_, j) => (j === yi ? (fromInput(e.target.value, "int") as number | null) : plan.graduates?.[j] ?? 0)) })} /></td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <span className="small faint">รับรวม 5 ปี {sum} คน · เฉลี่ยปีละ {years.length ? Math.round(sum / years.length) : 0} คน{!plans.length && " · ยังไม่มีแผนจากเล่ม ตารางนี้สร้างจากปีที่เริ่มใช้"}</span>
    </div>
  );
}

function BookEditor({ value, ctx }: { value: unknown; ctx: Ctx }) {
  const book = (value ?? null) as { name?: string; size?: number; by?: string; at?: string; label?: string } | null;
  const [busy, setBusy] = useState(false);
  return (
    <div className="stack" style={{ gap: 6 }}>
      {book?.name ? (
        <div className="row" style={{ gap: 8 }}>
          <Pill kind="ok">{book.label ?? "ฉบับอนุมัติ"}</Pill>
          <a href={curriculumForm.bookUrl(ctx.draftId)} target="_blank" rel="noreferrer">{book.name}</a>
          <span className="small faint">{Math.round((book.size ?? 0) / 1024)} KB · {book.by} · {book.at?.replace("T", " ").slice(0, 16)}</span>
        </div>
      ) : <span className="small faint">ยังไม่ได้แนบ</span>}
      {!ctx.readOnly && (
        <input type="file" accept="application/pdf" aria-label="แนบไฟล์เล่มอนุมัติ" disabled={busy} onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setBusy(true);
          try { await ctx.onBook(file); } finally { setBusy(false); e.target.value = ""; }
        }} />
      )}
    </div>
  );
}

function Master({ s0 }: { s0: Record<string, unknown> | undefined }) {
  const v = (getPath(s0, "info.values") ?? {}) as Row;
  const rows: [string, unknown][] = [
    ["รหัสหลักสูตร สกอ.", v.program_code], ["ชื่อหลักสูตร (ไทย)", v.name_th], ["ชื่อหลักสูตร (อังกฤษ)", v.name_en],
    ["ชื่อปริญญา", [v.degree_full_th, v.degree_abbr_th].filter(Boolean).join(" · ")], ["สาขาวิชา", v.field_of_study],
    ["หน่วยกิตตลอดหลักสูตร", v.total_credits],
  ];
  return (
    <dl className="kv" style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "4px 12px", margin: 0 }}>
      {rows.map(([k, val]) => <Fragment key={k}><dt className="small faint">{k}</dt><dd style={{ margin: 0 }}>{asInput(val, "text") || "–"}</dd></Fragment>)}
    </dl>
  );
}
