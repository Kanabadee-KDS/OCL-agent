"use client";

// reports (mock · US-M5-01): the reports this account may open, with the TOR item, who they are
// for and how they export; reports the mock proposes beyond the TOR carry "เสนอเพิ่ม".
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { reportsApi, type ReportItem } from "@/lib/api";
import { canMenu } from "@/lib/nav";
import { reportHref } from "@/lib/reports";
import { Note, PageHead, Pill } from "@/components/ui";

export default function ReportCenterPage() {
  const { data: session } = useSession();
  const perms = session?.user?.perms;
  const [items, setItems] = useState<ReportItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { reportsApi.catalog().then(setItems).catch((e) => setErr((e as Error).message)); }, []);
  return (
    <>
      <PageHead crumb={["รายงาน"]} title="ศูนย์รายงาน" sub="รายงานตามสิทธิ์ของบัญชีนี้ · ข้อมูลในทุกรายงานอยู่ในขอบเขตข้อมูลของบัญชี · ส่งออก Excel ได้ทุกรายงาน PDF ใช้การพิมพ์หน้ารายงาน" />
      {err && <Note kind="warn">{err}</Note>}
      {items && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {items.map((r) => (
            <Link key={r.code} href={reportHref(r.code, (m) => canMenu(perms, m))} className="card pad stack" style={{ gap: 6, color: "inherit" }}>
              <div className="between"><b className="num">{r.code}</b>{r.proposed ? <Pill kind="info">เสนอเพิ่ม</Pill> : r.public ? <Pill kind="ok">สาธารณะ</Pill> : null}</div>
              <b>{r.title}</b>
              <span className="small faint">TOR {r.tor} · {r.users}</span>
              <span className="small">ส่งออก {r.exports.join(" · ")}{r.remind ? " · แจ้งเตือนผู้ที่ยังไม่ส่ง" : ""}</span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
