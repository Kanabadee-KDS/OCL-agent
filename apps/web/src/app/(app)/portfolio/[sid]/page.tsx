"use client";

// portfolio-detail (mock · US-M3-07): one student; รายงานผลรายบุคคล prints this page.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { skillsApi, type Portfolio } from "@/lib/api";
import { Note, PageHead } from "@/components/ui";
import { BackLink } from "@/components/kit";
import { PortfolioView } from "@/components/skills";

export default function PortfolioDetailPage() {
  const { sid } = useParams<{ sid: string }>();
  const [p, setP] = useState<Portfolio | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { skillsApi.portfolio(sid).then(setP).catch((e) => setErr((e as Error).message)); }, [sid]);
  return (
    <>
      <div className="no-print"><BackLink href="/portfolio">กลับไป Skill Portfolio</BackLink></div>
      <PageHead crumb={["Skill Transcript", "Skill Portfolio"]} title="Skill Portfolio รายบุคคล" />
      {err && <Note kind="warn">{err}</Note>}
      {!p && !err && <div className="card pad">กำลังโหลด…</div>}
      {p && <PortfolioView p={p} actions={<span className="no-print row"><button type="button" className="btn" onClick={() => window.print()}>รายงานผลรายบุคคล</button><Link className="btn primary" href={`/portfolio/${sid}/transcript`}>ดู Skill Transcript</Link></span>} />}
    </>
  );
}
