"use client";

// Shared pieces of M2 (FS-4): the term picker, the staff picker of the recorders, and the
// list of items of a term for plans or reports (US-M2-03: per unit, then "เข้าทำ").
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fmtTime, m2Api, usersApi, type M2Doc, type M2Item, type M2Items, type M2Person, type M2Term, type Staff } from "@/lib/api";
import { STATUS_KIND, sentPct } from "@/lib/m2";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { DataTable, Filters, Kpi, KpiRow, Modal, SearchBox, SelectFilter, useToast, type Column } from "@/components/kit";

/** The terms (newest first) and the one chosen; remembered for the session. A failed load
 *  is an error to show, not "no terms". */
export function useTerm(): [M2Term[] | null, string, (slug: string) => void, string | null] {
  const [terms, setTerms] = useState<M2Term[] | null>(null);
  const [slug, setSlug] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    m2Api.terms().then((t) => {
      setTerms(t);
      const kept = typeof window !== "undefined" ? window.sessionStorage.getItem("m2-term") : null;
      setSlug(t.find((x) => x.slug === kept)?.slug ?? t[0]?.slug ?? "");
    }).catch((e) => setErr(`โหลดภาคการศึกษาไม่ได้: ${(e as Error).message} · ลองโหลดหน้าใหม่`));
  }, []);
  const pick = (s: string) => { setSlug(s); try { window.sessionStorage.setItem("m2-term", s); } catch { /* private mode */ } };
  return [terms, slug, pick, err];
}

export function TermSelect({ terms, slug, onChange }: { terms: M2Term[]; slug: string; onChange: (s: string) => void }) {
  return (
    <select className="inp" style={{ maxWidth: 200 }} aria-label="ภาค/ปีการศึกษา" value={slug} onChange={(e) => onChange(e.target.value)}>
      {terms.map((t) => <option key={t.slug} value={t.slug}>ภาค {t.term}</option>)}
    </select>
  );
}

export function StaffPicker({ title, value, onClose, onSave }: { title: string; value: M2Person[]; onClose: () => void; onSave: (pids: string[]) => void }) {
  const [list, setList] = useState<M2Person[]>(value);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Staff[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => { usersApi.staff(q).then((r) => setFound(r.items)).catch(() => setFound([])); }, 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <Modal open title={title} onClose={onClose}
      foot={<><button type="button" className="btn" onClick={onClose}>ยกเลิก</button><button type="button" className="btn primary" onClick={() => onSave(list.map((p) => p.pid))}>บันทึก</button></>}>
      <div className="stack">
        <div className="row" style={{ gap: 6 }}>
          {list.map((p) => <span key={p.pid} className="pill p-info">{p.name} <button type="button" className="link-btn" aria-label={`นำ ${p.name} ออก`} onClick={() => setList((x) => x.filter((y) => y.pid !== p.pid))}>×</button></span>)}
          {!list.length && <span className="small faint">ยังไม่มีผู้บันทึก</span>}
        </div>
        <input className="inp" aria-label="ค้นบุคลากร" placeholder="พิมพ์ชื่อหรือรหัสบุคลากร (ระบบบุคลากร)" value={q} onChange={(e) => setQ(e.target.value)} />
        {q.trim().length >= 2 && found.filter((s) => !list.some((p) => p.pid === s.pid)).map((s) => (
          <button key={s.pid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => { setList((x) => [...x, { pid: s.pid, name: `${s.title_short ?? ""}${s.name_th}` }]); setQ(""); }}>
            <b>{s.title_short}{s.name_th}</b> <span className="small faint">{s.pid} · {s.faculty}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

const who = (ps: M2Person[]) => (ps.length ? ps.map((p) => p.name).join(", ") : <span className="faint">ยังไม่กำหนด</span>);

/** plan / rep (mock · US-M2-03): per unit, then the items of the unit. */
export function ItemsPage({ doc }: { doc: M2Doc }) {
  const toast = useToast();
  const [terms, slug, setSlug, termErr] = useTerm();
  const [d, setD] = useState<M2Items | null>(null);
  const [unit, setUnit] = useState("");
  const [q, setQ] = useState("");
  const [st, setSt] = useState("");
  useEffect(() => { if (slug) m2Api.items(slug).then(setD).catch((e) => toast((e as Error).message, "err")); }, [slug, toast]);
  // BR-M2-05: a recorder outside their scope sees only the documents assigned to them
  const items = useMemo(() => (d?.items ?? []).filter((i) => i.offered && (i.scoped || i.mine[doc])), [d, doc]);
  const units = useMemo(() => {
    const m = new Map<string, M2Item[]>();
    for (const i of items) m.set(i.unit ?? "ไม่ระบุหน่วยงาน", [...(m.get(i.unit ?? "ไม่ระบุหน่วยงาน") ?? []), i]);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "th"));
  }, [items]);
  const rows = items.filter((i) => (!unit || (i.unit ?? "ไม่ระบุหน่วยงาน") === unit) && (!st || i.status[doc] === st));
  const base = doc === "plan" ? "/plans" : "/reports";
  const label = doc === "plan" ? "แผนการจัดการเรียนรู้" : "รายงานผลการจัดการเรียนรู้";
  const mineOnly = items.length > 0 && items.every((i) => !i.scoped);
  const columns: Column<M2Item>[] = [
    { key: "code", label: "รายวิชา/ชุดวิชา", sort: (i) => i.code, render: (i) => <><Link href={`${base}/${slug}/${encodeURIComponent(i.key)}`} style={{ fontWeight: 600 }}>{i.kind === "module" ? "ชุดวิชา " : ""}{i.code}</Link> {i.kind === "course" && i.name_th}<div className="small faint">{i.kind === "module" ? `รายวิชา ${i.courses.join(", ")}` : ""}{i.sections} กลุ่ม · ลงทะเบียน {i.enrolled}</div></> },
    { key: "unit", label: "หน่วยงานเจ้าของวิชา", render: (i) => <span className="small">{i.unit}</span> },
    { key: "who", label: "ผู้บันทึก", render: (i) => <span className="small">{who(i.assign[doc])}</span> },
    { key: "st", label: "สถานะ", sort: (i) => i.status[doc], render: (i) => <Pill kind={STATUS_KIND[i.status[doc]]}>{d?.statuses[i.status[doc]]}</Pill> },
    { key: "go", label: "", render: (i) => <Link className="btn xs" href={`${base}/${slug}/${encodeURIComponent(i.key)}`}>{i.mine[doc] && ["none", "draft", "returned"].includes(i.status[doc]) ? "บันทึก" : "เปิด"}</Link> },
  ];
  function exportCsv() {
    const head = ["หน่วยงาน", "รายวิชาที่เปิดสอน", ...Object.values(d?.statuses ?? {}), "ร้อยละความคืบหน้า"];
    const body = units.map(([u, xs]) => [u, xs.length, ...Object.keys(d?.statuses ?? {}).map((s) => xs.filter((x) => x.status[doc] === s).length), sentPct(xs.map((x) => x.status[doc]))]);
    const url = URL.createObjectURL(new Blob([toCsv(head, body)], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `${doc}-${slug}.csv` }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead crumb={["แผนการจัดการเรียนรู้", `บันทึก${label}`]} title={`บันทึก${label}`}
        sub={<>นับเฉพาะรายวิชาที่เปิดสอนในภาคตามตารางสอน SUPREME · รายวิชาร่วมบันทึกครั้งเดียวที่หน่วยงานเจ้าของวิชา{d?.synced_at && <> · ดึงข้อมูลล่าสุด {fmtTime(d.synced_at)}</>}</>}
        actions={<>{terms && <TermSelect terms={terms} slug={slug} onChange={setSlug} />}<button type="button" className="btn" disabled={!units.length} onClick={exportCsv}>ส่งออกภาพรวม</button><button type="button" className="btn" onClick={() => window.print()}>พิมพ์รายงานสรุป</button></>} />
      {termErr && <Note kind="warn">{termErr}</Note>}
      {terms && !terms.length && <Note kind="info">ยังไม่มีข้อมูลตารางสอน SUPREME</Note>}
      {mineOnly && <Note kind="info">แสดงเฉพาะรายวิชา/ชุดวิชาที่บัญชีนี้ได้รับมอบหมาย</Note>}
      <KpiRow>
        <Kpi label="เปิดสอน" value={items.length} sub={`${d?.items.length ?? 0} รายการในภาค`} />
        {(["none", "draft", "sent", "published"] as const).map((s) => <Kpi key={s} label={d?.statuses[s] ?? s} value={items.filter((i) => i.status[doc] === s).length} on={st === s} onClick={() => setSt((x) => (x === s ? "" : s))} />)}
        <Kpi label="ความคืบหน้า" value={`${sentPct(items.map((i) => i.status[doc]))}%`} sub="(ส่งตรวจสอบ + รับรอง + เผยแพร่) ÷ เปิดสอน" />
      </KpiRow>
      <section className="card pad stack">
        <h2 className="h2">ภาพรวมตามหน่วยงานเจ้าของวิชา</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>หน่วยงาน</th><th className="r">เปิดสอน</th>{Object.entries(d?.statuses ?? {}).map(([k, v]) => <th key={k} className="r">{v}</th>)}<th className="r">%</th><th /></tr></thead>
            <tbody>
              {units.map(([u, xs]) => (
                <tr key={u} style={u === unit ? { background: "var(--surface-2)" } : undefined}>
                  <td>{u}</td><td className="r num">{xs.length}</td>
                  {Object.keys(d?.statuses ?? {}).map((s) => <td key={s} className="r num">{xs.filter((x) => x.status[doc] === s).length || "–"}</td>)}
                  <td className="r num">{sentPct(xs.map((x) => x.status[doc]))}%</td>
                  <td><button type="button" className="btn xs" onClick={() => setUnit(u === unit ? "" : u)}>{u === unit ? "ทั้งหมด" : "เข้าทำ"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <DataTable rows={rows} columns={columns} rowKey={(i) => i.key} search={q} searchText={(i) => `${i.code} ${i.name_th ?? ""} ${i.courses.join(" ")}`} unit="รายการ"
        empty={d ? "ไม่มีรายการ" : "กำลังโหลด…"}
        toolbar={<Filters><SearchBox value={q} onChange={setQ} placeholder="ค้นรหัสหรือชื่อรายวิชา/ชุดวิชา" /><SelectFilter label="สถานะ" value={st} options={Object.entries(d?.statuses ?? {})} onChange={setSt} />{unit && <Pill kind="info">{unit}</Pill>}</Filters>} />
    </>
  );
}
