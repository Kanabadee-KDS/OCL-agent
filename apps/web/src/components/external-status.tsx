"use client";

// Which external systems the pages read from, and whether that is still sample data (plan FS-0c2).
import { useEffect, useState } from "react";
import { external, fmtTime, type ExternalSource } from "@/lib/api";
import { SampleData } from "@/components/kit";
import { Note, Pill } from "@/components/ui";

const SHORT: Record<string, string> = { huris: "HURIS", supreme: "SUPREME" };

export function ExternalStatus() {
  const [rows, setRows] = useState<ExternalSource[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { external.status().then(setRows).catch((e) => setErr((e as Error).message)); }, []);
  return (
    <section className="card pad stack">
      <h2 className="h2" style={{ margin: 0 }}>ข้อมูลจากระบบภายนอก</h2>
      <p className="small faint" style={{ margin: 0 }}>หน้าที่แสดงอาจารย์ หลักสูตร ตารางสอน และนิสิต ใช้ข้อมูลชุดนี้ · แก้ไขในระบบนี้ไม่ได้</p>
      {err && <Note kind="warn">{err}</Note>}
      {rows && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>ระบบ</th><th>แหล่งข้อมูล</th><th className="r">จำนวน</th><th>วันที่ข้อมูล</th><th>ปรับปรุงล่าสุด</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.system}>
                  <td>{r.label}</td>
                  <td>{!r.adapter ? <Pill kind="grey">ยังไม่มีข้อมูล</Pill> : r.sample ? <SampleData source={SHORT[r.system] ?? r.system} /> : r.adapter_label}</td>
                  <td className="r num">{r.counts ? Object.values(r.counts).reduce((a, b) => a + b, 0).toLocaleString("th-TH") : "–"}</td>
                  <td className="small">{r.as_of ?? "–"}</td>
                  <td className="small">{r.synced_at ? fmtTime(r.synced_at) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
