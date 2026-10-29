"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Ic, Note } from "@/components/ui";
import { ROLES, roleLabel } from "@/lib/perm";
import { canMenu, menuOfPath, visibleNav, NAV, type Perms } from "@/lib/nav";
import { LogoutButton } from "@/components/logout";

const menuLabel = (id: string) =>
  NAV.flatMap((m) => m.secs.flatMap((s) => s.items)).find((i) => i.id === id)?.label ?? id;

export type ShellUser = {
  name: string; email: string; roles: string[]; perms: Perms;
  roleNames: Record<string, string>; activeRole: string | null;
};

const NAV_KEY = "ocl.nav.collapsed"; // per-browser convenience only
const SMALL = "(max-width:1024px)"; // same breakpoint as design.css off-canvas nav

// screen size, as an external store (server and first paint = wide: no hydration mismatch)
const subscribeSmall = (cb: () => void) => {
  const mq = window.matchMedia(SMALL);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
// "sidebar collapsed" remembered per browser; works in memory when storage is blocked
let collapsedMem: boolean | null = null;
const collapsedListeners = new Set<() => void>();
const getCollapsed = () => {
  if (collapsedMem === null) {
    try { collapsedMem = localStorage.getItem(NAV_KEY) === "1"; } catch { collapsedMem = false; }
  }
  return collapsedMem;
};
const setCollapsedStore = (v: boolean) => {
  collapsedMem = v;
  try { localStorage.setItem(NAV_KEY, v ? "1" : "0"); } catch { /* storage blocked: memory only */ }
  collapsedListeners.forEach((l) => l());
};
const subscribeCollapsed = (cb: () => void) => { collapsedListeners.add(cb); return () => { collapsedListeners.delete(cb); }; };

export function Shell({ user, children }: { user: ShellUser; children: React.ReactNode }) {
  const initials = user.name.trim().slice(0, 2) || "ผู้";
  // wide screens: sidebar shown unless collapsed (remembered) · small screens: off-canvas, opened on demand
  const collapsed = useSyncExternalStore(subscribeCollapsed, getCollapsed, () => false);
  const small = useSyncExternalStore(subscribeSmall, () => window.matchMedia(SMALL).matches, () => false);
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const nav = visibleNav(user.perms);
  const roleText = user.activeRole ? roleLabel([user.activeRole], user.roleNames) : roleLabel(user.roles, user.roleNames);
  const roleStyle = { background: "var(--red-soft)", borderColor: "transparent", color: "var(--red-ink)", fontWeight: 600 };
  const { update } = useSession();
  const router = useRouter();
  const [switching, setSwitching] = useState(false);
  async function switchRole(role: string) {
    setSwitching(true);
    await update({ activeRole: role || null });
    router.refresh();
    setSwitching(false);
  }
  const activeMenu = menuOfPath(path);
  // a module starts open when it holds the current page; the user can open/close any module
  const [modOpen, setModOpen] = useState<Record<string, boolean>>({});
  const isOpen = (k: string, hasActive: boolean) => modOpen[k] ?? hasActive;
  // per-page permission (the API checks again on every call): pages of a menu the user may not view
  const denied = activeMenu !== undefined && !canMenu(user.perms, activeMenu);
  function toggle() {
    if (small) setOpen((o) => !o);
    else setCollapsedStore(!collapsed);
  }
  const shown = small ? open : !collapsed;
  return (
    <div className={`app ${collapsed ? "nav-collapsed" : ""} ${open ? "nav-open" : ""}`}>
      <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className="nav" id="main-nav" aria-label="เมนูหลัก">
        <div className="nav-head">
          <span className="av" style={{ background: "var(--red)", color: "#fff" }}>มศว</span>
          <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.3 }}>
            <b style={{ fontFamily: "var(--f-display)", fontSize: 13, color: "#fff", lineHeight: 1.35 }}>
              ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล
            </b>
            <span style={{ fontSize: 11, color: "var(--nav-muted)" }}>(Skill Transcript) · มหาวิทยาลัยศรีนครินทรวิโรฒ</span>
          </div>
        </div>
        <nav className="nav-body">
          <Link href="/" className={`nav-mod ${path === "/" ? "has-active" : ""}`} onClick={() => setOpen(false)}>
            <Ic name="home" size={20} />
            <span>หน้าแรก</span>
          </Link>
          {nav.map((m) => {
            const hasActive = m.secs.some((s) => s.items.some((i) => i.id === activeMenu));
            const opened = isOpen(m.k, hasActive);
            return (
              <div key={m.k}>
                <button
                  type="button"
                  className={`nav-mod ${opened ? "open" : ""} ${hasActive ? "has-active" : ""}`}
                  aria-expanded={opened}
                  onClick={() => setModOpen((s) => ({ ...s, [m.k]: !opened }))}
                >
                  <Ic name={m.icon} size={20} />
                  <span>{m.label}</span>
                  <span className="chev"><Ic name="chev" size={15} width={2} /></span>
                </button>
                {opened && (
                  <div style={{ padding: "2px 0 8px" }}>
                    {m.secs.map((s) => (
                      <div key={s.cap}>
                        <div className="nav-cap">{s.cap}</div>
                        {s.items.map((i) =>
                          i.href ? (
                            <Link
                              key={i.id}
                              href={i.href}
                              className={`nav-item ${i.id === activeMenu ? "active" : ""}`}
                              aria-current={i.id === activeMenu ? "page" : undefined}
                              onClick={() => setOpen(false)}
                            >
                              <span>{i.label}</span>
                              {i.tag && <span className="tag">{i.tag}</span>}
                            </Link>
                          ) : (
                            <button key={i.id} type="button" className="nav-item soon" disabled title={`อยู่ระหว่างพัฒนา (${i.phase})`}>
                              <span>{i.label}</span>
                              {i.tag ? <span className="tag">{i.tag}</span> : <span className="soon-tag">เร็ว ๆ นี้</span>}
                            </button>
                          ),
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="nav-foot">
          <span>OCR Agent</span>
          <span>{roleText}</span>
        </div>
      </aside>
      <div className="main">
        <header className="top">
          <button
            type="button"
            className="btn icon menu-btn"
            onClick={toggle}
            aria-controls="main-nav"
            aria-expanded={shown}
            title={shown ? "ซ่อนเมนู" : "แสดงเมนู"}
            aria-label={shown ? "ซ่อนเมนู" : "แสดงเมนู"}
          >
            <Ic name="menu" size={20} />
          </button>
          <label className="search hide-sm">
            <Ic name="search" size={17} />
            <input type="search" placeholder="ค้นหาเมนู หลักสูตร รายวิชา หรือนิสิต" aria-label="ค้นหา" disabled />
            <span className="kbd">Enter</span>
          </label>
          <div style={{ flex: 1 }} />
          {user.roles.length > 1 ? (
            // US-U-04: a user with several groups works as one of them; the menus follow
            <label className="btn role-btn" title={`${user.email} · สลับบทบาท`} style={roleStyle}>
              {user.name} ·
              <select
                aria-label="สลับบทบาท"
                value={user.activeRole ?? ""}
                disabled={switching}
                onChange={(e) => switchRole(e.target.value)}
                style={{ border: 0, background: "transparent", color: "inherit", font: "inherit", fontWeight: 600, cursor: "pointer" }}
              >
                <option value="">ทุกบทบาท</option>
                {user.roles.map((r) => <option key={r} value={r}>{user.roleNames[r] ?? ROLES[r] ?? r}</option>)}
              </select>
            </label>
          ) : (
            <span className="btn role-btn" title={user.email} style={roleStyle}>
              {user.name} · {roleText}
            </span>
          )}
          <span className="av" title={user.email} style={{ background: "var(--nav)", color: "#fff" }}>{initials}</span>
          <LogoutButton />
        </header>
        <div className="content">
          {denied ? (
            <section className="card pad stack" style={{ maxWidth: 720 }}>
              <h1 className="h1">ไม่มีสิทธิ์ในเมนูนี้</h1>
              <Note kind="warn">
                บัญชี {user.email} มีบทบาท {roleText} ซึ่งไม่ครอบคลุมเมนู &ldquo;{menuLabel(activeMenu ?? "")}&rdquo; ติดต่อผู้ดูแลส่วนกลางหากต้องการสิทธิ์เพิ่ม
              </Note>
              <Link href="/" className="btn" style={{ alignSelf: "flex-start" }}>กลับหน้าแรก</Link>
            </section>
          ) : (
            children
          )}
        </div>
      </div>
    </div>
  );
}
