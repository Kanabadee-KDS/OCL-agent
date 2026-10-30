"use client";

// dash-plan (mock · US-M2-07): a term's plans and reports in the user's ขอบเขตข้อมูล: offered
// items, items without recorders, % sent (plans due 2 weeks before the term, reports after
// it), published, units under the target (red), the late list with แจ้งเตือน / แจ้งเตือนทั้งหมด.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { fmtTime, m2Api, type M2Dashboard, type M2Status } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { STATUS_KIND } from "@/lib/m2";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, Kpi, KpiRow, useToast } from "@/components/kit";
import { TermSelect, useTerm } from "@/components/m2";

const ST: [M2Status, string, string][] = [["none", "ยังไม่บันทึก", "var(--line-2)"], ["draft", "บันทึกแล้ว", "var(--info)"], ["sent", "ส่งตรวจสอบ", "var(--gold)"], ["returned", "ส่งคืนแก้ไข", "var(--red)"], ["approved", "รับรองแล้ว", "#7FB09E"], ["published", "เผยแพร่", "var(--ok)"]];

export default function PlanDashboard() {
  const { data: session } = useSession();
  const canRemind = canMenu(session?.user?.perms, "d2", "edit");
  const toast = useToast();
  const [terms, slug, setSlug, termErr] = useTerm();
  const [d, setD] = useState<M2Dashboard | null>(null);
  const load = () => slug && m2Api.dashboard(slug).then(setD).catch((e) => toast((e as Error).message, "err"));
  useEffect(() => { if (slug) m2Api.dashboard(slug).then(setD).catch((e) => toast((e as Error).message, "err")); }, [slug, toast]);

  async function remind(key?: string, doc?: "plan" | "report") {
    try { const r = await m2Api.remind(slug, key, doc); toast(r.sent ? `ส่งแจ้งเตือน ${r.sent} รายการ` : "ไม่มีรายการที่ต้องแจ้ง หรือวันนี้แจ้งแล้ว", r.sent ? "ok" : "err"); load(); } catch (e) { toast((e as Error).message, "err"); }
  }
  function exportCsv() {
    if (!d) return;
    const head = ["หน่วยงาน", "รายวิชา/ชุดวิชาที่เปิดสอน", "แผนส่งแล้ว (%)", "รายงานส่งแล้ว (%)", "ต่ำกว่าเป้า"];
    const body = d.units.map((u) => [u.unit, u.count, u.plan_pct, u.report_pct, u.below ? "ใช่" : ""]);
    const url = URL.createObjectURL(new Blob([toCsv(head, body)], { type: "text/csv;charset=utf-8" }));
    Object.assign(document.createElement("a"), { href: url, download: `dashboard-plans-${slug}.csv` }).click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead crumb={["แดชบอร์ด"]} title="แดชบอร์ดการบันทึกแผนการเรียนรู้"
        sub={<>ติดตามการบันทึกแผนและรายงานผลการจัดการเรียนรู้ รายวิชา/ชุดวิชา · เฉพาะขอบเขตข้อมูลของบัญชีนี้{d?.synced_at && <> · ตารางสอนดึงล่าสุด {fmtTime(d.synced_at)}</>}</>}
        actions={<>{terms && <TermSelect terms={terms} slug={slug} onChange={setSlug} />}<button type="button" className="btn" disabled={!d} onClick={exportCsv}>ส่งออก CSV</button></>} />
      {termErr && <Note kind="warn">{termErr}</Note>}
      {terms && !terms.length && <Note kind="info">ยังไม่มีข้อมูลตารางสอน SUPREME</Note>}
      {d && (
        <>
          <KpiRow>
            <Kpi label="รายวิชา/ชุดวิชาที่เปิดสอน" value={d.offered} sub={`ชุดวิชา ${d.modules}`} />
            <Kpi label="ยังไม่กำหนดผู้บันทึก" value={d.unassigned} sub="แผนหรือรายงานยังว่าง" />
            <Kpi label="แผนฯ ส่งแล้ว" value={`${d.plan_pct}%`} sub={`ครบกำหนด ${d.term.plan_close ?? "ยังไม่กำหนด"}`} />
            <Kpi label="รายงานผลฯ ส่งแล้ว" value={`${d.report_pct}%`} sub={`ครบกำหนด ${d.term.report_close ?? "ยังไม่กำหนด"}`} />
            <Kpi label="เผยแพร่โดยส่วนกลาง" value={d.published.plan + d.published.report} sub={`แผน ${d.published.plan} · รายงาน ${d.published.report}`} />
          </KpiRow>
          <section className="card pad stack">
            <h2 className="h2">สถานะการบันทึก</h2>
            {(["plan", "report"] as const).map((doc) => {
              const total = d.offered || 1;
              return (
                <div key={doc} className="grid" style={{ gridTemplateColumns: "200px minmax(0,1fr)", gap: 12, alignItems: "center" }}>
                  <span>{doc === "plan" ? "แผนการจัดการเรียนรู้" : "รายงานผลการจัดการเรียนรู้"}</span>
                  <div className="bar lg" role="img" aria-label={ST.map(([k, l]) => `${l} ${d.status[doc][k]}`).join(", ")}>{ST.filter(([k]) => d.status[doc][k]).map(([k, l, c]) => <span key={k} title={`${l}: ${d.status[doc][k]}`} style={{ width: `${(d.status[doc][k] / total) * 100}%`, background: c }} />)}</div>
                </div>
              );
            })}
            <div className="row" style={{ gap: 10 }}>{ST.map(([k, l, c]) => <span key={k} className="small"><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: c, marginRight: 4 }} />{l}</span>)}</div>
          </section>
          <section className="card pad stack">
            <h2 className="h2">ความคืบหน้าจำแนกตามหน่วยงานเจ้าของวิชา</h2>
            <span className="small faint">แดงเมื่อแผนส่งแล้วต่ำกว่าเป้า {d.target_pct}%</span>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>หน่วยงาน</th><th className="r">เปิดสอน</th><th style={{ minWidth: 160 }}>แผนฯ</th><th className="r">%</th><th style={{ minWidth: 160 }}>รายงานผลฯ</th><th className="r">%</th></tr></thead>
                <tbody>
                  {d.units.map((u) => (
                    <tr key={u.unit}>
                      <td style={u.below ? { color: "var(--red-ink, var(--red))", fontWeight: 600 } : undefined}>{u.unit}</td><td className="r num">{u.count}</td>
                      <td><Bar pct={u.plan_pct} color={u.below ? "var(--red)" : "var(--ok)"} /></td><td className="r num">{u.plan_pct}</td>
                      <td><Bar pct={u.report_pct} color="var(--info)" /></td><td className="r num">{u.report_pct}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="card pad stack">
            <div className="between"><h2 className="h2">รายการที่เลยกำหนดส่ง ({d.late.length})</h2>{canRemind && d.late.length > 0 && <button type="button" className="btn" onClick={() => remind()}>แจ้งเตือนทั้งหมด</button>}</div>
            <span className="small faint">เรียงจากค้างนานสุด · แจ้งเตือนส่งอีเมลถึงผู้บันทึกของรายการนั้น ได้วันละครั้ง · รายการที่ยังไม่กำหนดผู้บันทึกส่งไม่ได้</span>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>รหัส</th><th>เอกสาร</th><th>หน่วยงาน</th><th>สถานะ</th><th>ผู้บันทึก</th><th className="r">เลยกำหนด</th><th /></tr></thead>
                <tbody>
                  {d.late.slice(0, 50).map((x) => (
                    <tr key={x.key + x.doc}>
                      <td><Link href={`/${x.doc === "plan" ? "plans" : "reports"}/${slug}/${encodeURIComponent(x.key)}`}><b>{x.code}</b></Link> <span className="small">{x.name_th}</span></td>
                      <td className="small">{x.doc === "plan" ? "แผนฯ" : "รายงานผลฯ"}</td><td className="small">{x.unit}</td>
                      <td><Pill kind={STATUS_KIND[x.status]}>{ST.find(([k]) => k === x.status)?.[1]}</Pill></td>
                      <td className="small">{x.recorders.join(", ") || <span className="faint">ยังไม่กำหนด</span>}</td>
                      <td className="r num">{x.days} วัน</td>
                      <td>{canRemind && x.recorders.length > 0 && <button type="button" className="btn xs" onClick={() => remind(x.key, x.doc)}>แจ้งเตือน</button>}</td>
                    </tr>
                  ))}
                  {!d.late.length && <tr><td colSpan={7} className="small faint">ไม่มีรายการเลยกำหนด (หรือยังไม่ได้ตั้งวันครบกำหนดของภาค)</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
