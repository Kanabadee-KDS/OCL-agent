"use client";

// dash (mock · US-G-01): what the user should see first after signing in — the figures of their
// ขอบเขตข้อมูล (curricula, plans sent, skills assessed, transcripts issued), plans sent per unit
// against the target, the skill averages by category, and "งานของฉัน" (what is waiting on them).
import { useEffect, useState } from "react";
import Link from "next/link";
import { reportsApi, type HomeData } from "@/lib/api";
import { Bar, Kpi, KpiRow, Radar } from "@/components/kit";
import { Pill } from "@/components/ui";

export function HomeDash() {
  const [d, setD] = useState<HomeData | null>(null);
  useEffect(() => { reportsApi.home().then(setD).catch(() => setD(null)); }, []);
  if (!d || (!d.cards.length && !d.tasks.length)) return null;
  const skills = d.skills ? Object.entries(d.skills).filter((e): e is [string, number] => e[1] !== null) : [];
  return (
    <>
      {d.cards.length > 0 && (
        <KpiRow cols={Math.min(d.cards.length, 4)}>
          {d.cards.map((c) => <Link key={c.label} href={c.href} style={{ color: "inherit" }}><Kpi label={c.label} value={c.value} sub={c.sub} /></Link>)}
        </KpiRow>
      )}
      {(d.units.length > 0 || skills.length > 0) && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
          {d.units.length > 0 && (
            <section className="card pad stack">
              <h2 className="h2">แผนฯ ส่งแล้วตามหน่วยงาน</h2>
              <span className="small faint">แดงเมื่อต่ำกว่าเป้า {d.target}%</span>
              {d.units.slice(0, 8).map((u) => (
                <div key={u.unit}>
                  <div className="between small"><span style={u.below ? { color: "var(--red)", fontWeight: 600 } : undefined}>{u.unit}</span><b className="num">{u.plan_pct}%</b></div>
                  <Bar pct={u.plan_pct} color={u.below ? "var(--red)" : "var(--ok)"} />
                </div>
              ))}
            </section>
          )}
          {skills.length > 0 && (
            <section className="card pad stack" style={{ alignItems: "center" }}>
              <h2 className="h2" style={{ alignSelf: "flex-start" }}>คะแนน Skill เฉลี่ยรายด้าน</h2>
              <Radar items={skills} size={220} />
            </section>
          )}
        </div>
      )}
      {d.tasks.length > 0 && (
        <section className="card pad stack">
          <h2 className="h2">งานของฉัน ({d.tasks.length})</h2>
          <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: 6 }}>
            {d.tasks.map((t) => <li key={t.href} className="between" style={{ gap: 8 }}><Link href={t.href} style={{ fontWeight: 600 }}>{t.text}</Link><Pill kind="warn">{t.status}</Pill></li>)}
          </ul>
        </section>
      )}
    </>
  );
}
