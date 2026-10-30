// R11 (US-M5-01 · TOR 6.16.7): the curricula statistics anyone may read without signing in —
// curricula by faculty and level, and the results of the latest assessment round; no names.
// Outside (app), so no session is needed.
import { INTERNAL_API_BASE } from "@/auth";
import type { Report } from "@/lib/api";
import { cellText } from "@/lib/reports";

export const dynamic = "force-dynamic";

export default async function StatsPage() {
  let r: Report | null = null;
  try {
    const res = await fetch(`${INTERNAL_API_BASE}/api/public/stats`, { cache: "no-store" });
    if (res.ok) r = (await res.json()) as Report;
  } catch {
    r = null;
  }
  return (
    <main className="stack" style={{ maxWidth: 960, margin: "32px auto", padding: "0 16px", gap: 16 }}>
      <div className="row" style={{ gap: 10 }}><span className="av" style={{ background: "var(--red)", color: "#fff" }}>มศว</span><div><b>สถิติหลักสูตร</b><div className="small faint">มหาวิทยาลัยศรีนครินทรวิโรฒ · เผยแพร่สาธารณะ</div></div></div>
      {!r && <div className="note warn">ยังแสดงสถิติไม่ได้ ลองใหม่ภายหลัง</div>}
      {r && (
        <>
          <div className="grid kpi-row" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            {r.kpis.map((k) => <div key={k.label} className="card kpi"><span className="l">{k.label}</span><span className="v num">{cellText(k.value)}</span></div>)}
          </div>
          {r.tables.map((t) => (
            <section key={t.title} className="card pad stack">
              <h2 className="h2">{t.title}</h2>
              <div className="tbl-wrap"><table className="tbl">
                <thead><tr>{t.columns.map((c) => <th key={c.key} className={c.num ? "r" : undefined}>{c.label}</th>)}</tr></thead>
                <tbody>{t.rows.map((row, i) => <tr key={i}>{t.columns.map((c) => <td key={c.key} className={c.num ? "r num" : undefined}>{cellText(row[c.key])}</td>)}</tr>)}</tbody>
              </table></div>
            </section>
          ))}
        </>
      )}
    </main>
  );
}
