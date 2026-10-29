import Link from "next/link";
import { auth } from "@/auth";
import { Ic, Note, PageHead, Pill } from "@/components/ui";
import { roleLabel } from "@/lib/perm";
import { visibleNav } from "@/lib/nav";

// Landing page for every role: the menus the user may open, built or still in development.
// The dashboard of the mock (US-G-01) replaces the summary cards in FS-7.
export default async function HomePage() {
  const session = await auth();
  const roles = session?.user?.roles ?? [];
  const nav = visibleNav(roles);
  const items = nav.flatMap((m) => m.secs.flatMap((s) => s.items));
  const ready = items.filter((i) => i.href).length;
  return (
    <>
      <PageHead
        crumb={["หน้าแรก"]}
        title={`สวัสดี ${session?.user?.name ?? ""}`.trim()}
        sub={`บทบาท ${roleLabel(roles)} · เมนูที่ใช้ได้ ${ready} จาก ${items.length} เมนู`}
      />
      {nav.length === 0 && (
        <Note kind="warn">บัญชีนี้ยังไม่มีบทบาทในระบบ ติดต่อผู้ดูแลส่วนกลาง (ฝ่ายวิชาการ) เพื่อกำหนดสิทธิ์</Note>
      )}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {nav.map((m) => (
          <section key={m.k} className="card pad stack">
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <Ic name={m.icon} size={22} />
              <h2 className="h2" style={{ margin: 0 }}>{m.label}</h2>
            </div>
            <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: 6 }}>
              {m.secs.flatMap((s) => s.items).map((i) => (
                <li key={i.id} className="between" style={{ gap: 8 }}>
                  {i.href ? <Link href={i.href} style={{ fontWeight: 600 }}>{i.label}</Link> : <span className="muted">{i.label}</span>}
                  {i.href ? <Pill kind="ok">ใช้งานได้</Pill> : <Pill kind="grey">อยู่ระหว่างพัฒนา</Pill>}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
