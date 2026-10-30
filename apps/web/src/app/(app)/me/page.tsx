"use client";

// me (mock · US-M3-09): the signed-in student's own portfolio (the account's รหัสนิสิต).
import { useEffect, useState } from "react";
import Link from "next/link";
import { skillsApi, type Portfolio } from "@/lib/api";
import { Note, PageHead } from "@/components/ui";
import { PortfolioView } from "@/components/skills";

export default function MyPortfolioPage() {
  const [p, setP] = useState<Portfolio | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { skillsApi.me().then(setP).catch((e) => setErr((e as Error).message)); }, []);
  return (
    <>
      <PageHead crumb={["สำหรับนิสิต"]} title="Skill Portfolio ของฉัน" sub="อัปเดตเมื่ออาจารย์ยืนยันผลการประเมินของแต่ละรายวิชา" />
      {err && <Note kind="warn">{err}</Note>}
      {!p && !err && <div className="card pad">กำลังโหลด…</div>}
      {p && <PortfolioView p={p} actions={<Link className="btn primary" href="/me/transcript">Skill Transcript ของฉัน</Link>} />}
    </>
  );
}
