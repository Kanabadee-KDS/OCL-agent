"use client";

// Preview แบบเล่มหลักสูตร (US-M1-05): หมวด 3 (PLO · KSEC · ตารางสรุป) and หมวด 4 (โครงสร้าง ·
// รายวิชา · Curriculum Mapping) in the book's order, from the latest saved sections (the faculty's
// edits included). PDF is the browser's print to A4 (FS-2 Q2 ก); the running head repeats on
// every printed page because it sits in a table header (app.css .book-frame).
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { curricula, curriculumForm, type CurriculumDetail, type SectionData } from "@/lib/api";
import { CATS, flatten, formatCell, ksecKey, ksecLabel, mappingColumns, mappingRows, nodeOf, summary, type Course, type KsecPlo, type KsecRow, type Node, type Plo } from "@/lib/curriculum";
import { getPath } from "@/lib/form";
import { Note } from "@/components/ui";
import { BackLink } from "@/components/kit";

const CAT_TH: Record<string, string> = { K: "ความรู้ (Knowledge)", S: "ทักษะ (Skills)", E: "จริยธรรม (Ethics)", C: "ลักษณะบุคคล (Character)" };

export default function CurriculumPreviewPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<CurriculumDetail | null>(null);
  const [secs, setSecs] = useState<SectionData | null>(null);
  const [at, setAt] = useState<Date | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([curricula.get(id), curriculumForm.sections(id)])
      .then(([dd, ss]) => { setD(dd); setSecs(ss); setAt(new Date()); })
      .catch((e) => setErr((e as Error).message));
  }, [id]);

  const s = useMemo(() => Object.fromEntries(Object.entries(secs ?? {}).map(([k, v]) => [k, v.data])), [secs]);
  if (err) return <><BackLink href={`/curricula/${id}`}>กลับไปหน้าคู่มือ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d || !secs || !at) return <div className="card pad">กำลังโหลด…</div>;

  const v = (getPath(s["0"], "info.values") ?? {}) as Record<string, unknown>;
  const name = (v.name_th as string) || d.name_th || "คู่มือหลักสูตร";
  const year = (v.edition_year as string | number | undefined) ?? d.start_year ?? "–";
  const stamp = at.toLocaleString("th-TH", { dateStyle: "long", timeStyle: "short" });
  const plos = (getPath(s["3"], "plo.plos") as Plo[] | undefined) ?? [];
  const ksec = (getPath(s["3"], "ksec.plos") as KsecPlo[] | undefined) ?? [];
  const tree = (getPath(s["4"], "structure.tree") as Node[] | undefined) ?? [];
  const courses = (getPath(s["4"], "courses.courses") as Course[] | undefined) ?? [];
  const rows = mappingRows(courses, (getPath(s["4"], "mapping.ksec_rows") as KsecRow[] | undefined) ?? []);
  const run = <>คู่มือหลักสูตร {name} · ฉบับ พ.ศ. {String(year)}</>;

  return (
    <>
      <div className="between no-print">
        <BackLink href={`/curricula/${id}`}>กลับไปหน้าคู่มือ</BackLink>
        <div className="row">
          <span className="small faint">ข้อมูลล่าสุดที่บันทึก · ส่งออก {stamp}</span>
          <button type="button" className="btn primary" onClick={() => window.print()}>พิมพ์ / บันทึกเป็น PDF</button>
        </div>
      </div>
      <div className="no-print"><Note kind="info">ในหน้าต่างพิมพ์ เลือกปลายทาง &ldquo;บันทึกเป็น PDF&rdquo; ขนาดกระดาษ A4 · ปิด &ldquo;ส่วนหัวและท้ายกระดาษ&rdquo; ของเบราว์เซอร์ เพราะเล่มมีหัวกระดาษของตัวเองแล้ว</Note></div>
      <article className="book" aria-label="Preview แบบเล่มหลักสูตร">
        <table className="book-frame">
          <thead><tr><td><div className="book-run"><span>{run}</span><span>ส่งออก {stamp}</span></div></td></tr></thead>
          <tbody><tr><td>
            <header className="book-title">
              <h1>{name}</h1>
              {!!v.name_en && <div>{String(v.name_en)}</div>}
              <div className="small">ฉบับ พ.ศ. {String(year)}{v.revision_type ? ` (${String(v.revision_type)})` : ""} · {d.faculty ?? (v.faculty as string) ?? ""} · สถานะ {d.status_th}</div>
            </header>

            <section>
              <h2>หมวดที่ 3 ผลลัพธ์การเรียนรู้ของหลักสูตร</h2>
              <h3>3.1 ผลลัพธ์การเรียนรู้ที่คาดหวังของหลักสูตร (PLOs)</h3>
              {plos.length ? (
                <table>
                  <thead><tr><th style={{ width: "14%" }}>รหัส</th><th>ผลลัพธ์การเรียนรู้</th></tr></thead>
                  <tbody>
                    {plos.flatMap((p) => [
                      <tr key={p.code}><td><b>{p.code}</b></td><td>{p.text}</td></tr>,
                      ...(p.sub_plos ?? []).map((sp, i) => <tr key={`${p.code}.${i}`}><td className="sub">{p.code}.{i + 1}</td><td className="sub">{sp}</td></tr>),
                    ])}
                  </tbody>
                </table>
              ) : <p className="empty">ยังไม่มี PLO</p>}

              <h3>3.2 ความรู้ ทักษะ จริยธรรม และลักษณะบุคคล (KSEC) ตาม PLO</h3>
              {ksec.map((k) => (
                <table key={ksecKey(k)} className="keep">
                  <thead>
                    <tr><th colSpan={3} style={{ textAlign: "left" }}>{ksecLabel(k)} {k.text}</th></tr>
                    <tr><th style={{ width: "12%" }}>รหัส</th><th style={{ width: "24%" }}>ด้าน</th><th>รายละเอียด</th></tr>
                  </thead>
                  <tbody>
                    {k.items.map((it, j) => <tr key={`${it.code}-${j}`}><td>{it.code}</td><td>{CAT_TH[it.category] ?? it.category}{it.subtype ? ` · ${it.subtype}` : ""}</td><td>{it.text}</td></tr>)}
                    {!k.items.length && <tr><td colSpan={3} className="empty">ยังไม่มีรายการ</td></tr>}
                  </tbody>
                </table>
              ))}
              {!ksec.length && <p className="empty">ยังไม่มี KSEC</p>}

              <h3>3.3 ตารางสรุป PLO และ KSEC</h3>
              <table className="keep">
                <thead><tr><th>PLO</th>{CATS.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                <tbody>
                  {summary(ksec).map((r) => <tr key={r.key}><td><b>{r.label}</b></td>{CATS.map((c) => <td key={c} className="codes">{r.cells[c].join(", ")}</td>)}</tr>)}
                </tbody>
              </table>
            </section>

            <section>
              <h2>หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และการจัดการเรียนรู้</h2>
              <h3>4.1 โครงสร้างหลักสูตร</h3>
              <table className="keep">
                <thead><tr><th>หมวดวิชา / กลุ่มวิชา</th><th style={{ width: "18%" }}>หน่วยกิต</th></tr></thead>
                <tbody>
                  {flatten(tree).map(({ node, path }) => (
                    <tr key={node.number}>
                      <td style={{ paddingLeft: 6 + path.length * 18 }}>{node.number} {node.name}{node.module && " (ชุดวิชา)"}{node.module && node.description && <div className="small">{node.description}</div>}</td>
                      <td className="r">{node.credits ?? "–"}</td>
                    </tr>
                  ))}
                  <tr><td><b>รวมตลอดหลักสูตร ไม่น้อยกว่า</b></td><td className="r"><b>{String(v.total_credits ?? tree.reduce((a, n) => a + (Number(n.credits) || 0), 0))}</b></td></tr>
                </tbody>
              </table>

              <h3>4.2 รายวิชาและคำอธิบายรายวิชา</h3>
              {groupCourses(courses, tree).map((g) => (
                <div key={g.key}>
                  <h4>{g.title}</h4>
                  {g.items.map((c, i) => (
                    <div key={`${c.code_th}-${i}`} className="course">
                      <div className="course-head"><b>{c.code_th}</b>{c.code_en ? ` (${c.code_en})` : ""} <b>{c.name_th}</b><span className="cr">{c.credit_text ?? c.credits ?? ""}</span></div>
                      {c.name_en && <div>{c.name_en}</div>}
                      {!!c.prerequisite && <div className="small">วิชาบังคับก่อน: {String(c.prerequisite)}</div>}
                      {!!c.description_th && <p>{String(c.description_th)}</p>}
                      {!!c.description_en && <p lang="en">{String(c.description_en)}</p>}
                    </div>
                  ))}
                </div>
              ))}
              {!courses.length && <p className="empty">ยังไม่มีรายวิชา</p>}

              <h3>4.3 แผนที่แสดงการกระจายความรับผิดชอบ (Curriculum Mapping)</h3>
              {plos.length ? <Mapping plos={plos} rows={rows} /> : <p className="empty">ยังไม่มี PLO ในหมวด 3</p>}
            </section>
          </td></tr></tbody>
        </table>
      </article>
    </>
  );
}

/** Courses by the group they are linked to (structure order); unlinked ones by the book's group text. */
function groupCourses(courses: readonly Course[], tree: readonly Node[]) {
  const out: { key: string; title: string; items: Course[] }[] = [];
  for (const { node, path } of flatten(tree)) {
    const items = courses.filter((c) => nodeOf(c, tree) === node.number);
    if (items.length) out.push({ key: node.number, title: [...path.map((p) => p.name), node.name].join(" › "), items });
  }
  for (const c of courses.filter((x) => !nodeOf(x, tree))) {
    const key = `book:${c.group ?? ""}`;
    const g = out.find((x) => x.key === key) ?? (out.push({ key, title: c.group || "ไม่ระบุกลุ่ม", items: [] }), out[out.length - 1]);
    g.items.push(c);
  }
  return out;
}

function Mapping({ plos, rows }: { plos: Plo[]; rows: KsecRow[] }) {
  const cols = mappingColumns(plos);
  return (
    <table className="map">
      <thead>
        <tr><th rowSpan={2}>รหัสวิชา</th><th rowSpan={2}>รายวิชา</th>{plos.map((p) => <th key={p.code} colSpan={4}>{p.code}</th>)}</tr>
        <tr>{cols.map((c) => <th key={c.col}>{c.col}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.course_code || i}>
            <td>{r.course_code}</td>
            <td className="name">{r.course_name}</td>
            {cols.map((c) => <td key={c.col} className="c">{formatCell(r.by_column[c.col], c.col)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
