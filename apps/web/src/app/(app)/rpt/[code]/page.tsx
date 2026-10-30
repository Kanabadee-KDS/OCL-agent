"use client";

// rpt (mock · US-M5-01 02 03 · R01–R14): one page for every report. The API sends the filters
// of the user's ขอบเขตข้อมูล, the KPI tiles and the tables; the page shows them, keeps the
// filters in the address (a link opens the same view), downloads the Excel file (one sheet per
// table), prints as PDF, and for R01–R03 e-mails whoever has not sent yet (once a day).
import { Suspense, useEffect, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { reportsApi, type Report, type ReportTable } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { NARROWING, REPORT_MENU, cellText } from "@/lib/reports";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Filters, Kpi, KpiRow, Modal, Radar, useToast } from "@/components/kit";

const SHOWN = 50;

export default function ReportPage() {
  return <Suspense><ReportView /></Suspense>;
}

function ReportView() {
  const code = String(useParams<{ code: string }>().code).toUpperCase();
  const sp = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const { data: session } = useSession();
  const toast = useToast();
  const params = Object.fromEntries(sp.entries());
  const key = sp.toString();
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    reportsApi.report(code, Object.fromEntries(new URLSearchParams(key).entries())).then((x) => { setR(x); setErr(null); }).catch((e) => { setR(null); setErr((e as Error).message); });
  }, [code, key]);
  const canRemind = !!r?.remind && canMenu(session?.user?.perms, REPORT_MENU[code], "edit");
  const setFilter = (k: string, v: string) => {
    const q = new URLSearchParams(key);
    if (v) q.set(k, v); else q.delete(k);
    if (k === "faculty") q.delete("program");
    router.replace(`${path}${q.size ? `?${q}` : ""}`);
  };
  function print() {
    setAll(true);
    setTimeout(() => window.print(), 100);
  }
  async function remind() {
    setAsk(false);
    try {
      const x = await reportsApi.remind(code, params);
      toast(x.sent ? `ส่งแจ้งเตือน ${x.sent} รายการ` : "ไม่มีรายการที่ต้องแจ้ง หรือวันนี้แจ้งแล้ว", x.sent ? "ok" : "err");
    } catch (e) { toast((e as Error).message, "err"); }
  }
  const radar = r?.radar ? Object.entries(r.radar).filter((e): e is [string, number] => e[1] !== null) : [];
  return (
    <>
      {canMenu(session?.user?.perms, "r0") && <div className="no-print"><BackLink href="/rpt">ศูนย์รายงาน</BackLink></div>}
      <PageHead crumb={["รายงาน", code]} title={r ? `${code} ${r.title}` : code}
        sub={r ? `TOR ${r.tor} · ${r.users} · ส่งออก ${r.exports.join(" · ")}` : undefined}
        actions={r && <div className="row no-print" style={{ gap: 8 }}>
          {r.proposed && <Pill kind="info">เสนอเพิ่ม</Pill>}
          {canRemind && <button type="button" className="btn" onClick={() => setAsk(true)}>แจ้งเตือนผู้ที่ยังไม่ส่ง</button>}
          <button type="button" className="btn" onClick={print}>พิมพ์ / PDF</button>
          <a className="btn primary" href={reportsApi.xlsxUrl(code, params)} download>ส่งออก Excel</a>
        </div>} />
      {err && <Note kind="warn">{err}</Note>}
      {r && (
        <>
          {r.filters.length > 0 && (
            <div className="no-print"><Filters>
              {r.filters.map((f) => (
                <select key={f.key} className="inp" aria-label={f.label} value={f.value} onChange={(e) => setFilter(f.key, e.target.value)}>
                  {NARROWING.has(f.key) && <option value="">{f.label}: ทั้งหมด</option>}
                  {f.options.map(([v, t]) => <option key={v} value={v}>{NARROWING.has(f.key) ? `${f.label}: ${t}` : t}</option>)}
                </select>
              ))}
            </Filters></div>
          )}
          {r.kpis.length > 0 && <KpiRow cols={Math.min(r.kpis.length, 5)}>{r.kpis.map((k) => <Kpi key={k.label} label={k.label} value={cellText(k.value)} />)}</KpiRow>}
          {radar.length > 0 && <section className="card pad stack" style={{ alignItems: "center" }}><h2 className="h2" style={{ alignSelf: "flex-start" }}>ภาพรวมรายด้าน</h2><Radar items={radar} /></section>}
          {r.tables.map((t, i) => <TableCard key={`${i}-${t.title}`} t={t} all={all} onAll={() => setAll(true)} />)}
          {r.note && <Note kind="info">{r.note}</Note>}
        </>
      )}
      <Modal open={ask} title="แจ้งเตือนผู้ที่ยังไม่ส่ง" onClose={() => setAsk(false)}
        foot={<><button type="button" className="btn" onClick={() => setAsk(false)}>ยกเลิก</button><button type="button" className="btn primary" onClick={remind}>ส่งอีเมล</button></>}>
        <p>ส่งอีเมลถึงผู้ที่ยังไม่ส่งงานตามตัวกรองนี้ รายการเดียวกันแจ้งได้วันละครั้ง</p>
      </Modal>
    </>
  );
}

function TableCard({ t, all, onAll }: { t: ReportTable; all: boolean; onAll: () => void }) {
  const rows = all ? t.rows : t.rows.slice(0, SHOWN);
  return (
    <section className="card pad stack">
      <div className="between"><h2 className="h2">{t.title}</h2><span className="small faint">{t.rows.length.toLocaleString("th-TH")} แถว</span></div>
      <div className="tbl-wrap"><table className="tbl">
        <thead><tr>{t.columns.map((c) => <th key={c.key} className={c.num ? "r" : undefined}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, i) => <tr key={i}>{t.columns.map((c) => <td key={c.key} className={c.num ? "r num" : undefined}>{cellText(row[c.key])}</td>)}</tr>)}
          {!t.rows.length && <tr><td colSpan={Math.max(t.columns.length, 1)} className="empty">ไม่มีข้อมูลตามเงื่อนไข</td></tr>}
        </tbody>
      </table></div>
      {rows.length < t.rows.length && <button type="button" className="btn no-print" style={{ alignSelf: "flex-start" }} onClick={onAll}>แสดงทั้งหมด {t.rows.length.toLocaleString("th-TH")} แถว</button>}
      {t.note && <span className="small faint">{t.note}</span>}
    </section>
  );
}
