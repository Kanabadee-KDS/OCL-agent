"use client";

// dash-cur (mock · US-M1-01 02): แดชบอร์ดหลักสูตร from the real curricula, inside the user's
// ขอบเขตข้อมูล (the API filters). Tab ติดตามการบันทึกข้อมูล follows the mock; tab วิเคราะห์เชิงสถิติ
// shows the three views the mock describes, its detail still an assumption until question C1.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { curricula, type Dashboard, type DashItem } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { toCsv } from "@/lib/table";
import { Note, PageHead, Pill } from "@/components/ui";
import { Bar, Filters, Kpi, KpiRow, Legend, SelectFilter, Tabs, useToast } from "@/components/kit";

const ST: [Dashboard["by_faculty"][number]["counts"] extends Record<infer K, number> ? K : never, string, string][] = [
  ["import", "ร่างนำเข้าหลักสูตร", "var(--line-2)"],
  ["review", "คณะตรวจสอบ", "var(--gold)"],
  ["verified", "ตรวจสอบสำเร็จ", "var(--info)"],
  ["published", "เผยแพร่แล้ว", "var(--ok)"],
];
const SEC = ["หมวด 0 ข้อมูลหลัก", "หมวด 1 ข้อมูลทั่วไป", "หมวด 2 ข้อมูลเฉพาะ", "หมวด 3 PLO/KSEC", "หมวด 4 โครงสร้าง/Mapping", "หมวด 5 สถานภาพ/อนุมัติ"];
const pct = (a: number, b: number) => (b ? Math.round((a * 100) / b) : 0);
const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

function StatusBar({ counts, lg }: { counts: Record<string, number>; lg?: boolean }) {
  const total = ST.reduce((a, [k]) => a + (counts[k] ?? 0), 0) || 1;
  return (
    <div className={`bar ${lg ? "lg" : ""}`} role="img" aria-label={ST.map(([k, l]) => `${l} ${counts[k] ?? 0}`).join(", ")}>
      {ST.filter(([k]) => counts[k]).map(([k, l, c]) => <span key={k} title={`${l}: ${counts[k]}`} style={{ width: `${(counts[k] / total) * 100}%`, background: c }} />)}
    </div>
  );
}

export default function CurriculumDashboard() {
  const { data: session } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<"mon" | "stat">("mon");
  const [f, setF] = useState({ faculty: "", level: "", year: "" });
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dim, setDim] = useState<"level" | "start_year" | "revision_type">("level");
  const canRemind = canMenu(session?.user?.perms, "d1", "edit");

  useEffect(() => { curricula.dashboard(f).then(setD).catch((e) => setErr((e as Error).message)); }, [f]);

  function exportCsv() {
    if (!d) return;
    const head = ["รหัส", "หลักสูตร", "คณะ", "ระดับ", "ปีที่เริ่มใช้", "สถานะ", "ค้าง (วัน)", "หมวดที่ยังไม่ครบ", "หน่วยกิต", "PLO", "รายวิชา", "ใหม่/ปรับปรุง"];
    const rows = d.items.map((i) => [i.id, i.name_th, i.faculty, i.level, i.start_year, i.status_th, i.days ?? "", i.missing.map((n) => `หมวด ${n}`).join(" "), i.total_credits ?? "", i.plo_count, i.course_count, i.revision_type ?? ""]);
    const url = URL.createObjectURL(new Blob([toCsv(head, rows)], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `dashboard-curricula-${d.today}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }

  async function remind(i: DashItem) {
    try {
      const r = await curricula.remind(i.id);
      toast(r.sent ? `ส่งแจ้งเตือนถึงผู้รับผิดชอบขั้น "${r.step}" ${r.to} คนแล้ว` : "วันนี้แจ้งเตือนหลักสูตรนี้แล้ว (ส่งได้วันละครั้ง)", r.sent ? "ok" : "err");
    } catch (e) { toast((e as Error).message, "err"); }
  }

  return (
    <>
      <PageHead crumb={["แดชบอร์ด"]} title="แดชบอร์ดหลักสูตร"
        sub={tab === "mon" ? "ติดตามสถานะการบันทึกข้อมูลคู่มือหลักสูตร · เฉพาะหลักสูตรในขอบเขตข้อมูลของบัญชีนี้" : "วิเคราะห์ข้อมูลเชิงสถิติของหลักสูตร: ภาพรวม · ตอบ อว. · หลักสูตรที่ใกล้ครบรอบปรับปรุง"}
        actions={<button type="button" className="btn" disabled={!d?.items.length} onClick={exportCsv}>ส่งออก CSV</button>} />
      <Tabs label="มุมมองแดชบอร์ด" value={tab} onChange={setTab} items={[["mon", "ติดตามการบันทึกข้อมูล"], ["stat", "วิเคราะห์เชิงสถิติ"]] as const} />
      <Filters>
        <SelectFilter label="คณะ/ส่วนงาน" value={f.faculty} options={d?.options.faculties ?? []} onChange={(v) => setF((x) => ({ ...x, faculty: v }))} />
        <SelectFilter label="ระดับ" value={f.level} options={d?.options.levels ?? []} onChange={(v) => setF((x) => ({ ...x, level: v }))} />
        <SelectFilter label="ปีที่เริ่มใช้" value={f.year} options={(d?.options.years ?? []).map(String)} onChange={(v) => setF((x) => ({ ...x, year: v }))} />
      </Filters>
      {err && <Note kind="warn">{err}</Note>}
      {!d ? <div className="card pad">กำลังโหลด…</div> : !d.total ? <Note kind="info">ไม่มีหลักสูตรตามเงื่อนไขนี้ในขอบเขตข้อมูลของบัญชีนี้</Note> : tab === "mon" ? <Monitor d={d} canRemind={canRemind} remind={remind} /> : <Stats d={d} dim={dim} setDim={setDim} />}
    </>
  );
}

function Monitor({ d, canRemind, remind }: { d: Dashboard; canRemind: boolean; remind: (i: DashItem) => void }) {
  return (
    <>
      <KpiRow>
        <Kpi label="หลักสูตรในระบบ" value={d.total} sub="ทุกระดับการศึกษา" />
        {ST.map(([k, l]) => <Kpi key={k} label={l} value={d.counts[k]} sub={`${pct(d.counts[k], d.total)}%`} />)}
      </KpiRow>
      <section className="card pad stack">
        <h2 className="h2">สถานะการบันทึกข้อมูลหลักสูตร (ภาพรวม)</h2>
        <StatusBar counts={d.counts} lg />
        <Legend items={ST.map(([k, l, c]) => [c, <>{l} <b className="num">{d.counts[k]}</b></>] as const)} />
        <span className="small faint">ลำดับขั้น: ร่างนำเข้า → คณะตรวจสอบ → ตรวจสอบสำเร็จ → เผยแพร่</span>
      </section>
      <div className="dash-grid">
        <section className="card pad stack">
          <h2 className="h2">ความคืบหน้าจำแนกตามคณะ/ส่วนงาน</h2>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>คณะ/ส่วนงาน</th><th className="r">หลักสูตร</th><th style={{ minWidth: 160 }}>สถานะ</th><th className="r">ตรวจสอบสำเร็จ</th><th className="r">ค้างนานสุด</th></tr></thead>
              <tbody>
                {d.by_faculty.map((x) => (
                  <tr key={x.faculty}><td>{x.faculty}</td><td className="r num">{x.count}</td><td><StatusBar counts={x.counts} /></td><td className="r num">{x.verified_pct}%</td><td className="r num">{x.longest_days ? `${x.longest_days} วัน` : "–"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="card pad stack">
          <h2 className="h2">ความครบถ้วนรายหมวด</h2>
          <span className="small faint">ร้อยละของหลักสูตรที่กรอกช่องบังคับของหมวดนั้นครบ</span>
          {SEC.map((label, n) => (
            <div key={n} className="stack" style={{ gap: 4 }}>
              <div className="between small"><span>{label}</span><b className="num">{d.completeness[String(n)]}%</b></div>
              <Bar pct={d.completeness[String(n)]} label={`${label} ${d.completeness[String(n)]}%`} />
            </div>
          ))}
        </section>
      </div>
      <section className="card pad stack">
        <h2 className="h2">หลักสูตรที่ค้างนานที่สุด</h2>
        <span className="small faint">นับวันตั้งแต่เข้าสถานะปัจจุบัน · แจ้งเตือนส่งอีเมลถึงผู้รับผิดชอบขั้นนั้นของคณะ ได้วันละครั้งต่อหลักสูตร</span>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>หลักสูตร</th><th>คณะ/ส่วนงาน</th><th>สถานะ</th><th>หมวดที่ยังไม่ครบ</th><th className="r">ค้าง</th><th /></tr></thead>
            <tbody>
              {d.stuck.map((i) => (
                <tr key={i.id}>
                  <td><Link href={`/curricula/${i.id}`} style={{ fontWeight: 600 }}>{i.name_th}</Link></td>
                  <td className="small">{i.faculty ?? "–"}</td>
                  <td><Pill kind={i.status === "review" ? "warn" : "grey"}>{i.status_th}</Pill></td>
                  <td className="small">{i.missing.length ? i.missing.map((n) => `หมวด ${n}`).join(" · ") : "ครบทุกหมวด"}</td>
                  <td className="r num">{i.days} วัน</td>
                  <td>{canRemind && <button type="button" className="btn xs" onClick={() => remind(i)}>แจ้งเตือน</button>}</td>
                </tr>
              ))}
              {!d.stuck.length && <tr><td colSpan={6} className="small faint">ไม่มีหลักสูตรที่ค้างในร่างหรือการตรวจของคณะ</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

const DIM: Record<"level" | "start_year" | "revision_type", string> = { level: "ระดับการศึกษา", start_year: "ปีที่เริ่มใช้", revision_type: "ใหม่/ปรับปรุง" };

function Stats({ d, dim, setDim }: { d: Dashboard; dim: keyof typeof DIM; setDim: (k: keyof typeof DIM) => void }) {
  const groups = useMemo(() => {
    const m = new Map<string, DashItem[]>();
    for (const i of d.items) { const k = String(i[dim] ?? "ไม่ระบุ"); m.set(k, [...(m.get(k) ?? []), i]); }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "th"));
  }, [d.items, dim]);
  const levels = [...new Set(d.items.map((i) => i.level ?? "ไม่ระบุ"))].sort();
  const facs = [...new Set(d.items.map((i) => i.faculty ?? "ไม่ระบุคณะ"))].sort();
  // BR-08: revise every 5 years from the year it started; due this year or next
  const due = d.items.filter((i) => i.start_year && i.start_year + 5 <= d.this_year + 1).sort((a, b) => (a.start_year ?? 0) - (b.start_year ?? 0));
  const ksec = ["K", "S", "E", "C"].map((c) => [c, avg(d.items.map((i) => i.ksec[c] ?? 0))] as const);
  const ksecMax = Math.max(1, ...ksec.map(([, v]) => v));
  return (
    <>
      <Note kind="info">[สมมติ] แท็บนี้แสดง 3 มุมมองตามคำบรรยายใน mock รายละเอียดกราฟรอคำตอบข้อ C1 จากลูกค้า</Note>
      <div className="row" style={{ gap: 10 }}>
        <span className="small faint">แยกตาม</span>
        <div className="seg">{(Object.keys(DIM) as (keyof typeof DIM)[]).map((k) => <button key={k} type="button" className={dim === k ? "on" : ""} onClick={() => setDim(k)}>{DIM[k]}</button>)}</div>
      </div>
      <div className="dash-grid">
        <section className="card pad stack">
          <h2 className="h2">ภาพรวม: ตัวชี้วัดตาม{DIM[dim]}</h2>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>{DIM[dim]}</th><th className="r">หลักสูตร</th><th className="r">หน่วยกิตเฉลี่ย</th><th className="r">PLO เฉลี่ย</th><th className="r">รายวิชาเฉลี่ย</th><th className="r">เผยแพร่แล้ว</th></tr></thead>
              <tbody>
                {groups.map(([k, xs]) => (
                  <tr key={k}>
                    <td>{k}</td><td className="r num">{xs.length}</td>
                    <td className="r num">{avg(xs.map((x) => Number(x.total_credits) || 0).filter(Boolean)).toFixed(1)}</td>
                    <td className="r num">{avg(xs.map((x) => x.plo_count)).toFixed(1)}</td>
                    <td className="r num">{avg(xs.map((x) => x.course_count)).toFixed(1)}</td>
                    <td className="r num">{pct(xs.filter((x) => x.status === "published").length, xs.length)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="card pad stack">
          <h2 className="h2">ความครอบคลุม KSEC</h2>
          <span className="small faint">จำนวนรายการ KSEC เฉลี่ยต่อหลักสูตร แยกด้าน</span>
          {ksec.map(([c, v]) => (
            <div key={c} className="stack" style={{ gap: 4 }}>
              <div className="between small"><span>{{ K: "K ความรู้", S: "S ทักษะ", E: "E จริยธรรม", C: "C ลักษณะบุคคล" }[c]}</span><b className="num">{v.toFixed(1)}</b></div>
              <Bar pct={(v / ksecMax) * 100} label={`${c} ${v.toFixed(1)}`} />
            </div>
          ))}
        </section>
      </div>
      <section className="card pad stack">
        <h2 className="h2">ข้อมูลสำหรับตอบ อว.: จำนวนหลักสูตร คณะ × ระดับ</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>คณะ/ส่วนงาน</th>{levels.map((l) => <th key={l} className="r">{l}</th>)}<th className="r">รวม</th></tr></thead>
            <tbody>
              {facs.map((f) => {
                const xs = d.items.filter((i) => (i.faculty ?? "ไม่ระบุคณะ") === f);
                return <tr key={f}><td>{f}</td>{levels.map((l) => <td key={l} className="r num">{xs.filter((i) => (i.level ?? "ไม่ระบุ") === l).length || "–"}</td>)}<td className="r num"><b>{xs.length}</b></td></tr>;
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card pad stack">
        <h2 className="h2">หลักสูตรที่ใกล้ครบรอบปรับปรุง</h2>
        <span className="small faint">ปีที่เริ่มใช้ + 5 ปี (BR-08) ถึงภายในปี พ.ศ. {d.this_year + 1}</span>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>หลักสูตร</th><th>คณะ/ส่วนงาน</th><th className="r">ปีที่เริ่มใช้</th><th className="r">ครบรอบ</th></tr></thead>
            <tbody>
              {due.map((i) => <tr key={i.id}><td><Link href={`/curricula/${i.id}`}>{i.name_th}</Link></td><td className="small">{i.faculty}</td><td className="r num">{i.start_year}</td><td className="r">{(i.start_year ?? 0) + 5 <= d.this_year ? <Pill kind="red">{(i.start_year ?? 0) + 5}</Pill> : <span className="num">{(i.start_year ?? 0) + 5}</span>}</td></tr>)}
              {!due.length && <tr><td colSpan={4} className="small faint">ไม่มีหลักสูตรที่ครบรอบภายในปี พ.ศ. {d.this_year + 1}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
