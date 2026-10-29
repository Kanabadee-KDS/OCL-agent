"use client";

// หมวด 3 (PLO/Sub-PLO · KSEC · ตารางสรุป) and หมวด 4 (โครงสร้าง · Curriculum Mapping · รายวิชา)
// of the คู่มือหลักสูตร (BRD 01 §4, US-M1-08). In review the faculty may change the Mapping
// only; the API refuses anything else (ocl_api.curricula._edit_problem).
import { useState } from "react";
import Link from "next/link";
import { getPath, setPath } from "@/lib/form";
import {
  CATS, addNode, allCodes, coursesOf, creditSum, flatten, formatCell, ksecKey, ksecLabel, mapNode, mappingColumns, nodeOf,
  mappingRows, renameKsec, setCell, summary, syncKsec, type Course, type KsecItem, type KsecPlo, type KsecRow, type Node, type Plo,
} from "@/lib/curriculum";
import { Note, Pill } from "@/components/ui";
import { Tabs } from "@/components/kit";

type Data = Record<string, unknown>;

export function Section3({ data, onChange, readOnly }: { data: Data; onChange: (d: Data) => void; readOnly: boolean }) {
  const [tab, setTab] = useState<"plo" | "ksec" | "sum">("plo");
  const plos = (getPath(data, "plo.plos") as Plo[] | undefined) ?? [];
  const ksec = syncKsec(plos, (getPath(data, "ksec.plos") as KsecPlo[] | undefined) ?? []);
  const [sel, setSel] = useState(0);

  function put(nextPlos: Plo[], nextKsec?: KsecPlo[]) {
    const k = syncKsec(nextPlos, nextKsec ?? ksec);
    let d = setPath(data, "plo.plos", nextPlos);
    d = setPath(d, "plo.count", nextPlos.length);
    d = setPath(d, "ksec.plos", k.map((x) => ({ ...x, item_count: x.items.length })));
    d = setPath(d, "ksec.codes", allCodes(k));
    d = setPath(d, "ksec.count", allCodes(k).length);
    onChange(d);
  }
  const setPlo = (i: number, p: Partial<Plo>) =>
    put(plos.map((x, k) => (k === i ? { ...x, ...p } : x)), p.code !== undefined ? renameKsec(ksec, plos[i].code, p.code) : undefined);
  const at = Math.min(sel, ksec.length - 1);
  const cur = ksec[at];
  const setItems = (items: KsecItem[]) => put(plos, ksec.map((k, i) => (i === at ? { ...k, items } : k)));
  const ploNo = cur ? plos.findIndex((p) => p.code === cur.code) + 1 : 0;

  return (
    <section className="card pad stack">
      <Tabs label="หมวด 3" value={tab} onChange={setTab} items={[["plo", "3.1 PLO / Sub-PLO"], ["ksec", "3.2 KSEC"], ["sum", "3.3 ตารางสรุป"]] as const} />
      {tab === "plo" && (
        <div className="stack">
          {plos.map((p, i) => (
            <div key={i} className="card pad stack" style={{ gap: 6 }}>
              <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                <input className="inp" style={{ width: 100 }} aria-label={`PLO ${i + 1}: รหัส`} disabled={readOnly} value={p.code} onChange={(e) => setPlo(i, { code: e.target.value })} />
                <textarea className="inp" rows={2} style={{ height: "auto", padding: 8, flex: 1 }} aria-label={`PLO ${i + 1}: ข้อความ`} disabled={readOnly} value={p.text} onChange={(e) => setPlo(i, { text: e.target.value })} />
                {!readOnly && <button type="button" className="btn xs" aria-label={`ลบ PLO ${i + 1}`} onClick={() => put(plos.filter((_, k) => k !== i))}>ลบ</button>}
              </div>
              {(p.sub_plos ?? []).map((s, j) => (
                <div key={j} className="row" style={{ gap: 8, paddingLeft: 108, flexWrap: "nowrap" }}>
                  <span className="small faint">{p.code}.{j + 1}</span>
                  <input className="inp" style={{ flex: 1 }} aria-label={`${p.code} Sub-PLO ${j + 1}`} disabled={readOnly} value={s} onChange={(e) => setPlo(i, { sub_plos: (p.sub_plos ?? []).map((x, k) => (k === j ? e.target.value : x)) })} />
                  {!readOnly && <button type="button" className="btn xs" onClick={() => setPlo(i, { sub_plos: (p.sub_plos ?? []).filter((_, k) => k !== j) })}>ลบ</button>}
                </div>
              ))}
              {!readOnly && <div style={{ paddingLeft: 108 }}><button type="button" className="btn xs" onClick={() => setPlo(i, { sub_plos: [...(p.sub_plos ?? []), ""] })}>เพิ่ม Sub-PLO</button></div>}
            </div>
          ))}
          {!plos.length && <span className="small faint">ยังไม่มี PLO</span>}
          {!readOnly && <div><button type="button" className="btn" onClick={() => put([...plos, { code: `PLO${plos.length + 1}`, text: "", sub_plos: [] }])}>เพิ่ม PLO</button></div>}
        </div>
      )}
      {tab === "ksec" && (cur ? (
        <div className="stack">
          <div className="seg" style={{ flexWrap: "wrap" }}>{ksec.map((k, i) => <button key={ksecKey(k)} type="button" className={i === at ? "on" : ""} onClick={() => setSel(i)}>{ksecLabel(k)} ({k.items.length})</button>)}</div>
          <span className="small faint">{cur.text}</span>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>รหัส</th><th>ด้าน</th><th>ประเภทย่อย</th><th>รายละเอียด</th>{!readOnly && <th />}</tr></thead>
              <tbody>
                {cur.items.map((it, j) => {
                  const set = (p: Partial<KsecItem>) => setItems(cur.items.map((x, k) => (k === j ? { ...x, ...p } : x)));
                  return (
                    <tr key={j}>
                      <td><input className="inp" style={{ width: 90 }} aria-label={`${cur.code} KSEC ${j + 1}: รหัส`} disabled={readOnly} value={it.code} onChange={(e) => set({ code: e.target.value })} /></td>
                      <td><select className="inp" aria-label={`${cur.code} KSEC ${j + 1}: ด้าน`} disabled={readOnly} value={it.category} onChange={(e) => set({ category: e.target.value })}>{CATS.map((c) => <option key={c}>{c}</option>)}</select></td>
                      <td>{it.category === "S" || it.category === "C" ? <select className="inp" aria-label={`${cur.code} KSEC ${j + 1}: ประเภทย่อย`} disabled={readOnly} value={it.subtype ?? ""} onChange={(e) => set({ subtype: e.target.value || null })}><option value="">—</option><option>ทั่วไป</option><option>ลักษณะเฉพาะ</option></select> : <span className="faint">–</span>}</td>
                      <td><input className="inp" aria-label={`${cur.code} KSEC ${j + 1}: รายละเอียด`} disabled={readOnly} value={it.text} onChange={(e) => set({ text: e.target.value })} /></td>
                      {!readOnly && <td><button type="button" className="btn xs" onClick={() => setItems(cur.items.filter((_, k) => k !== j))}>ลบ</button></td>}
                    </tr>
                  );
                })}
                {!cur.items.length && <tr><td colSpan={5} className="small faint">ยังไม่มี KSEC ของ {cur.code}</td></tr>}
              </tbody>
            </table>
          </div>
          {!readOnly && <div><button type="button" className="btn xs" onClick={() => setItems([...cur.items, { code: `K${ploNo}-${cur.items.filter((x) => x.category === "K").length + 1}`, category: "K", subtype: null, text: "" }])}>เพิ่ม KSEC</button></div>}
          <span className="small faint">รหัสซ้ำข้าม PLO ได้ · ทักษะทั่วไป/ลักษณะเฉพาะของ S และ C จะเชื่อมกับฐานข้อมูล Skill (M3)</span>
        </div>
      ) : <span className="small faint">เพิ่ม PLO ก่อน</span>)}
      {tab === "sum" && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>PLO</th>{CATS.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {summary(ksec).map((r) => <tr key={r.key}><td><b>{r.label}</b></td>{CATS.map((c) => <td key={c} className="small">{r.cells[c].join(", ") || "–"}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Section4({ data, onChange, readOnly, mappingOnly, draftId, plos, totalCredits }: {
  data: Data; onChange: (d: Data) => void; readOnly: boolean; mappingOnly: boolean; draftId: string; plos: Plo[]; totalCredits: number | null;
}) {
  const [tab, setTab] = useState<"tree" | "map" | "courses">("tree");
  const tree = (getPath(data, "structure.tree") as Node[] | undefined) ?? [];
  const courses = (getPath(data, "courses.courses") as Course[] | undefined) ?? [];
  const rows = mappingRows(courses, (getPath(data, "mapping.ksec_rows") as KsecRow[] | undefined) ?? []);
  const fixedRO = readOnly || mappingOnly; // structure and courses
  const cols = mappingColumns(plos);
  const mapped = rows.filter((r) => r.ksec_codes.length).length;

  const putTree = (t: Node[]) => onChange(setPath(setPath(data, "structure.tree", t), "structure.node_count", flatten(t).length));
  function putRows(next: KsecRow[]) {
    let d = setPath(data, "mapping.ksec_rows", next);
    d = setPath(d, "mapping.rows", next.map((r) => ({ course_code: r.course_code, course_name: r.course_name, group: r.group, plos: r.plos })));
    d = setPath(d, "mapping.plo_codes", plos.map((p) => p.code));
    d = setPath(d, "mapping.ksec_columns", [...new Set(next.flatMap((r) => Object.keys(r.by_column)))]);
    d = setPath(d, "mapping.unmapped_courses", next.filter((r) => !r.ksec_codes.length).map((r) => r.course_code));
    onChange(d);
  }
  const sum = creditSum(tree);
  const leaves = flatten(tree).filter((x) => !(x.node.children ?? []).length);
  const unlinked = courses.filter((c) => !nodeOf(c, tree)).length;
  const putCourses = (next: Course[]) => onChange(setPath(setPath(data, "courses.courses", next), "courses.count", next.length));

  return (
    <section className="card pad stack">
      <Tabs label="หมวด 4" value={tab} onChange={setTab} items={[["tree", "4.1 โครงสร้าง"], ["map", "4.2 Curriculum Mapping"], ["courses", `รายวิชา (${courses.length})`]] as const} />
      {mappingOnly && <Note kind="info">ระหว่างคณะตรวจสอบ แก้ได้เฉพาะ Curriculum Mapping · โครงสร้างและรายวิชาดูอย่างเดียว</Note>}
      {tab === "tree" && (
        <div className="stack">
          {unlinked > 0 && <Note kind="warn">รายวิชา {unlinked} จาก {courses.length} วิชายังไม่ผูกกับกลุ่มในโครงสร้าง (ข้อมูลนำเข้าบอกเพียงชื่อชุดวิชา) · เลือกกลุ่มได้ที่แท็บรายวิชา</Note>}
          {totalCredits != null && sum !== totalCredits && <Note kind="warn">หน่วยกิตรวมของหมวดวิชา {sum} ไม่ตรงกับหน่วยกิตตลอดหลักสูตรในหมวด 0 ({totalCredits})</Note>}
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>ลำดับ</th><th>หมวดวิชา/กลุ่มวิชา</th><th className="r">หน่วยกิต</th><th>ชุดวิชา</th><th className="r">รายวิชา</th><th /></tr></thead>
              <tbody>
                {flatten(tree).map(({ node, path }) => {
                  const set = (p: Partial<Node>) => putTree(mapNode(tree, node.number, (n) => ({ ...n, ...p })));
                  const n = coursesOf(courses, node).length;
                  return (
                    <tr key={node.number}>
                      <td className="num small">{node.number}</td>
                      <td style={{ paddingLeft: 12 + path.length * 20 }}>
                        <input className="inp" aria-label={`กลุ่ม ${node.number}: ชื่อ`} disabled={fixedRO} value={node.name} onChange={(e) => set({ name: e.target.value })} />
                        {node.module && <textarea className="inp" rows={2} style={{ height: "auto", padding: 6, marginTop: 4 }} aria-label={`กลุ่ม ${node.number}: คำอธิบายชุดวิชา`} placeholder="คำอธิบายชุดวิชา" disabled={fixedRO} value={node.description ?? ""} onChange={(e) => set({ description: e.target.value })} />}
                      </td>
                      <td className="r"><input className="inp num" type="number" style={{ width: 80 }} aria-label={`กลุ่ม ${node.number}: หน่วยกิต`} disabled={fixedRO} value={node.credits ?? ""} onChange={(e) => set({ credits: e.target.value === "" ? null : Number(e.target.value) })} /></td>
                      <td><input type="checkbox" aria-label={`กลุ่ม ${node.number}: ชุดวิชา`} disabled={fixedRO} checked={!!node.module} onChange={(e) => set({ module: e.target.checked })} /></td>
                      <td className="r num">{n}</td>
                      <td>
                        <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                          <Link className="btn xs" href={`/curricula/${draftId}/groups/${encodeURIComponent(node.number)}`}>เปิดกลุ่ม</Link>
                          {!fixedRO && <button type="button" className="btn xs" onClick={() => putTree(addNode(tree, node.number, "กลุ่มวิชาใหม่"))}>+ กลุ่มย่อย</button>}
                          {!fixedRO && !(node.children ?? []).length && !n && <button type="button" className="btn xs" aria-label={`ลบกลุ่ม ${node.number}`} onClick={() => putTree(mapNode(tree, node.number, () => null))}>ลบ</button>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                <tr><td /><td><b>รวม (หมวดวิชา)</b></td><td className="r num"><b>{sum}</b></td><td colSpan={3} /></tr>
              </tbody>
            </table>
          </div>
          {!fixedRO && <div><button type="button" className="btn xs" onClick={() => putTree(addNode(tree, null, "หมวดวิชาใหม่"))}>เพิ่มหมวดวิชา</button></div>}
          <span className="small faint">กลุ่มที่มีกลุ่มย่อยหรือรายวิชาอยู่ลบไม่ได้ · เพิ่ม/นำรายวิชาออกที่ &ldquo;เปิดกลุ่ม&rdquo;</span>
        </div>
      )}
      {tab === "map" && (
        <div className="stack">
          <div className="row" style={{ gap: 8 }}>
            <Pill>รายวิชาในหลักสูตร {rows.length}</Pill><Pill kind="ok">Mapping แล้ว {mapped}</Pill><Pill kind={rows.length - mapped ? "warn" : "grey"}>ยังไม่ Mapping {rows.length - mapped}</Pill>
          </div>
          {!plos.length ? <span className="small faint">ยังไม่มี PLO ในหมวด 3</span> : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr><th rowSpan={2}>รหัส</th><th rowSpan={2}>รายวิชา</th>{plos.map((p) => <th key={p.code} colSpan={4} style={{ textAlign: "center" }}>{p.code}</th>)}</tr>
                  <tr>{cols.map((c) => <th key={c.col} style={{ textAlign: "center" }}>{c.cat}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.course_code || i}>
                      <td className="small num">{r.course_code}</td>
                      <td className="small" style={{ minWidth: 160 }}>{r.course_name}</td>
                      {cols.map((c) => (
                        <td key={c.col} style={{ padding: 2 }}>
                          <input className="inp" style={{ width: 54, padding: "0 4px", textAlign: "center" }} aria-label={`${r.course_code} ${c.col}`} disabled={readOnly}
                            defaultValue={formatCell(r.by_column[c.col], c.col)}
                            onBlur={(e) => { if (e.target.value !== formatCell(r.by_column[c.col], c.col)) putRows(rows.map((x, k) => (k === i ? setCell(x, c.col, e.target.value, plos) : x))); }} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <span className="small faint">ใส่เลขท้ายรหัส KSEC คั่นด้วยจุลภาค เช่น ช่อง S1 &ldquo;1,4&rdquo; = S1-1, S1-4 (รูปแบบตามเล่ม)</span>
        </div>
      )}
      {tab === "courses" && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>รหัส</th><th>ชื่อรายวิชา</th><th>หน่วยกิต</th><th>ชุดวิชา/กลุ่มตามเล่ม</th><th>กลุ่มในโครงสร้าง</th></tr></thead>
            <tbody>
              {courses.map((c, i) => (
                <tr key={i}>
                  <td className="num small">{c.code_th}{c.code_en ? ` · ${c.code_en}` : ""}</td>
                  <td>{c.name_th}<div className="small faint">{c.name_en}</div></td>
                  <td className="small">{c.credit_text ?? c.credits}</td>
                  <td className="small">{c.group}</td>
                  <td>
                    <select className="inp" aria-label={`${c.code_th}: กลุ่มในโครงสร้าง`} disabled={fixedRO} value={nodeOf(c, tree) ?? ""}
                      onChange={(e) => putCourses(courses.map((x, k) => (k === i ? { ...x, node: e.target.value || null } : x)))}>
                      <option value="">— ยังไม่ผูก —</option>
                      {leaves.map(({ node, path }) => <option key={node.number} value={node.number}>{node.number} {[...path.map((p) => p.name), node.name].join(" › ")}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
              {!courses.length && <tr><td colSpan={5} className="small faint">ยังไม่มีรายวิชา · เพิ่มที่ &ldquo;เปิดกลุ่ม&rdquo; ในแท็บโครงสร้าง</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
