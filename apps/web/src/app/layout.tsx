import type { Metadata } from "next";
import Link from "next/link";
import { Anuphan, IBM_Plex_Sans_Thai } from "next/font/google";
import "./design.css";
import "./app.css";
import { Ic } from "@/components/ui";

const display = Anuphan({ subsets: ["thai", "latin"], weight: ["400", "500", "600", "700"], variable: "--f-display-next" });
const body = IBM_Plex_Sans_Thai({ subsets: ["thai", "latin"], weight: ["400", "500", "600"], variable: "--f-body-next" });

export const metadata: Metadata = {
  title: "OCL Agent · นำเข้าข้อมูลเล่มหลักสูตรด้วย AI (POC)",
  description: "ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript) — POC โมดูลนำเข้าด้วย AI",
};

const NAV = [
  {
    label: "บริหารข้อมูลหลักสูตร",
    icon: "book",
    secs: [
      { cap: "คู่มือหลักสูตร", items: [["คู่มือหลักสูตรตาม TOR", null], ["ตรวจสอบและบันทึก PLO โดยคณะ", null], ["งานปรับปรุงแก้ไขหลักสูตร (สมอ.08)", null]] },
      { cap: "นำเข้าข้อมูลเล่มหลักสูตรด้วย AI", items: [["นำเข้าข้อมูลเล่มหลักสูตร", "/import"]] },
      { cap: "ข้อมูลหลัก (Master)", items: [["บริหารรายวิชา", null], ["บริหารบุคคลภายนอก", null]] },
    ],
  },
  { label: "แผนการจัดการเรียนรู้รายวิชา/ชุดวิชา", icon: "plan", secs: [] },
  { label: "Skill Transcript", icon: "skill", secs: [] },
  { label: "ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน", icon: "qa", secs: [] },
  { label: "รายงาน", icon: "chart", secs: [] },
] as const;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <body className={`${display.variable} ${body.variable}`}>
        <div className="app">
          <aside className="nav" aria-label="เมนูหลัก">
            <div className="nav-head">
              <span className="av" style={{ background: "var(--red)", color: "#fff" }}>มศว</span>
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.3 }}>
                <b style={{ fontFamily: "var(--f-display)", fontSize: 13, color: "#fff", lineHeight: 1.35 }}>
                  ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล
                </b>
                <span style={{ fontSize: 11, color: "var(--nav-muted)" }}>(Skill Transcript) · มศว · POC</span>
              </div>
            </div>
            <nav className="nav-body">
              {NAV.map((m) => (
                <div key={m.label}>
                  <button className={`nav-mod ${m.secs.length ? "open has-active" : ""}`} disabled={!m.secs.length}>
                    <Ic name={m.icon} size={20} />
                    <span>{m.label}</span>
                    <span className="chev"><Ic name="chev" size={15} width={2} /></span>
                  </button>
                  {m.secs.length > 0 && (
                    <div style={{ padding: "2px 0 8px" }}>
                      {m.secs.map((s) => (
                        <div key={s.cap}>
                          <div className="nav-cap">{s.cap}</div>
                          {s.items.map(([t, href]) =>
                            href ? (
                              <Link key={t} href={href} className="nav-item active">
                                <span>{t}</span>
                                <span className="tag">POC</span>
                              </Link>
                            ) : (
                              <button key={t} className="nav-item" disabled title="อยู่ใน R1">
                                <span>{t}</span>
                              </button>
                            ),
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </nav>
            <div className="nav-foot">
              <span>OCL Agent</span>
              <span>POC · sprint 1</span>
            </div>
          </aside>
          <div className="main">
            <header className="top">
              <label className="search hide-sm">
                <Ic name="search" size={17} />
                <input type="search" placeholder="ค้นหาเมนู หลักสูตร รายวิชา หรือนิสิต" aria-label="ค้นหา" disabled />
                <span className="kbd">Enter</span>
              </label>
              <div style={{ flex: 1 }} />
              <span className="btn role-btn" style={{ background: "var(--red-soft)", borderColor: "transparent", color: "var(--red-ink)", fontWeight: 600 }}>
                บทบาท: ผู้ดูแลส่วนกลาง (POC ไม่มี login)
              </span>
              <span className="av" style={{ background: "var(--nav)", color: "#fff" }}>ผด</span>
            </header>
            <div className="content">{children}</div>
          </div>
        </div>
      </body>
    </html>
  );
}
