"use client";

// Shared pieces of the customer's mock (samples/ui-mock.html helpers kpi, searchF, selectF,
// tabsUI, segUI, modal, toast, F, pulled, bar, radarSVG, timeline), as React components on the
// mock's own CSS classes (design.css). List logic lives in lib/table.ts, radar geometry in lib/chart.ts.

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { Ic } from "@/components/ui";
import { filterRows, pageList, paginate, sortRows, type SortDir } from "@/lib/table";
import { RADAR, labelAnchor, radarPoint, radarPolygon, radarRing } from "@/lib/chart";

/* ---------- KPI card: clickable when it filters the list below (mock: card kpi · kpi.on) ---------- */
export function Kpi({ label, value, sub, on, onClick }: { label: ReactNode; value: ReactNode; sub?: ReactNode; on?: boolean; onClick?: () => void }) {
  const inner = (
    <>
      <span className="l">{label}</span>
      <span className="v num">{value}</span>
      {sub && <span className="small faint">{sub}</span>}
    </>
  );
  return onClick ? (
    <button type="button" className={`card kpi ${on ? "on" : ""}`} aria-pressed={on} onClick={onClick}
      style={{ textAlign: "left", cursor: "pointer", borderColor: on ? "var(--red)" : undefined }}>
      {inner}
    </button>
  ) : (
    <div className="card kpi">{inner}</div>
  );
}

export function KpiRow({ children, cols = 4 }: { children: ReactNode; cols?: number }) {
  return <div className="grid kpi-row" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }}>{children}</div>;
}

/* ---------- filters bar (mock: .filters with searchF + selectF) ---------- */
export function Filters({ children }: { children: ReactNode }) {
  return <div className="filters">{children}</div>;
}

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="inp grow row" style={{ gap: 8, height: 38, flexWrap: "nowrap" }}>
      <Ic name="search" size={16} />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        style={{ border: 0, outline: "none", background: "transparent", flex: 1, minWidth: 0, font: "inherit" }} />
    </label>
  );
}

export function SelectFilter({ label, value, options, onChange }: { label: string; value: string; options: readonly (string | [string, string])[]; onChange: (v: string) => void }) {
  return (
    <select className="inp" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{label}: ทั้งหมด</option>
      {options.map((o) => {
        const [v, t] = typeof o === "string" ? [o, o] : o;
        return <option key={v} value={v}>{t}</option>;
      })}
    </select>
  );
}

/* ---------- data table: search + filters + sortable headers + pager ---------- */
export type Column<T> = {
  key: string;
  label: ReactNode;
  render: (row: T) => ReactNode;
  sort?: (row: T) => unknown; // sortable when given
  align?: "right";
  width?: number | string;
};

export function DataTable<T>({
  rows, columns, rowKey, search, searchText, filters, filterValue, pageSize = 20, empty = "ไม่พบข้อมูลตามเงื่อนไข", unit = "รายการ", toolbar, onRowClick,
}: {
  rows: readonly T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  search?: string;
  searchText?: (row: T) => string;
  filters?: Record<string, string>;
  filterValue?: (row: T, key: string) => string | null | undefined;
  pageSize?: number;
  empty?: ReactNode;
  unit?: string;
  toolbar?: ReactNode;
  onRowClick?: (row: T) => void;
}) {
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(null);
  const [page, setPage] = useState(1);
  const shown = useMemo(() => {
    const f = filterRows(rows, search ?? "", searchText ?? (() => ""), filters, filterValue);
    const col = sort && columns.find((c) => c.key === sort.key);
    return sort && col?.sort ? sortRows(f, col.sort, sort.dir) : f;
  }, [rows, search, searchText, filters, filterValue, sort, columns]);
  // a new search or filter starts again from page 1
  const sig = `${search ?? ""}|${JSON.stringify(filters ?? {})}`;
  const [lastSig, setLastSig] = useState(sig);
  if (sig !== lastSig) { setLastSig(sig); setPage(1); }
  const pg = paginate(shown, page, pageSize);
  const toggle = (key: string) =>
    setSort((s) => (!s || s.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));
  return (
    <section className="card">
      {toolbar && <div className="pad" style={{ paddingBottom: 0 }}>{toolbar}</div>}
      <div className="tbl-wrap" style={{ border: 0, borderRadius: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.align === "right" ? "r" : undefined} style={{ width: c.width }}
                  aria-sort={sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                  {c.sort ? (
                    <button type="button" className="link-btn" onClick={() => toggle(c.key)} style={{ fontWeight: 600 }}>
                      {c.label} {sort?.key === c.key ? (sort.dir === "asc" ? "▲" : "▼") : ""}
                    </button>
                  ) : c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pg.rows.map((r) => (
              <tr key={rowKey(r)} className={onRowClick ? "click" : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}>
                {columns.map((c) => <td key={c.key} className={c.align === "right" ? "r" : undefined}>{c.render(r)}</td>)}
              </tr>
            ))}
            {pg.total === 0 && <tr><td colSpan={columns.length} className="empty">{empty}</td></tr>}
          </tbody>
        </table>
      </div>
      <Pager page={pg.page} pages={pg.pages} from={pg.from} to={pg.to} total={pg.total} all={rows.length} unit={unit} onPage={setPage} />
    </section>
  );
}

export function Pager({ page, pages, from, to, total, all, unit, onPage }: { page: number; pages: number; from: number; to: number; total: number; all: number; unit: string; onPage: (p: number) => void }) {
  return (
    <div className="between pad small faint" style={{ paddingTop: 12, paddingBottom: 12 }}>
      <span>
        {total === 0 ? `ไม่มี${unit}` : `แสดง ${from}–${to} จาก ${total} ${unit}`}
        {total !== all && ` (กรองจาก ${all})`}
      </span>
      {pages > 1 && (
        <nav className="row" style={{ gap: 4 }} aria-label="เลือกหน้า">
          <button type="button" className="btn xs" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="หน้าก่อน">‹</button>
          {pageList(page, pages).map((n, i) =>
            n === "…" ? <span key={`g${i}`}>…</span> : (
              <button key={n} type="button" className={`btn xs ${n === page ? "primary" : ""}`} aria-current={n === page ? "page" : undefined} onClick={() => onPage(n)}>{n}</button>
            ),
          )}
          <button type="button" className="btn xs" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="หน้าถัดไป">›</button>
        </nav>
      )}
    </div>
  );
}

/* ---------- tabs and segmented choice (mock: tabsUI · segUI) ---------- */
export function Tabs<K extends string>({ items, value, onChange, label }: { items: readonly (readonly [K, ReactNode])[]; value: K; onChange: (k: K) => void; label?: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map(([k, t]) => (
        <button key={k} type="button" role="tab" aria-selected={k === value} className={k === value ? "on" : ""} onClick={() => onChange(k)}>{t}</button>
      ))}
    </div>
  );
}

export function Seg<K extends string>({ items, value, onChange }: { items: readonly (readonly [K, ReactNode])[]; value: K; onChange: (k: K) => void }) {
  return (
    <div className="seg">
      {items.map(([k, t]) => (
        <button key={k} type="button" aria-pressed={k === value} className={k === value ? "on" : ""} onClick={() => onChange(k)}>{t}</button>
      ))}
    </div>
  );
}

/* ---------- modal dialog: Escape and the backdrop close it, focus moves in and back ---------- */
export function Modal({ open, title, onClose, children, foot, size }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode; foot?: ReactNode | false; size?: "lg" | "xl" }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const back = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>("input,select,textarea,button:not([data-close])")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); back?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={box} className={`modal ${size ?? ""}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}>
        <div className="modal-h">
          <h2 className="h2" style={{ margin: 0 }}>{title}</h2>
          <button type="button" className="btn icon ghost" data-close onClick={onClose} aria-label="ปิด"><Ic name="x" /></button>
        </div>
        <div className="modal-b">{children}</div>
        {foot !== false && <div className="modal-f">{foot ?? <button type="button" className="btn" onClick={onClose}>ปิด</button>}</div>}
      </div>
    </div>
  );
}

/* ---------- toasts (mock: toast()) ---------- */
type ToastMsg = { id: number; text: string; kind: "ok" | "err" };
const ToastCtx = createContext<(text: string, kind?: "ok" | "err") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<ToastMsg[]>([]);
  const push = useCallback((text: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setList((l) => [...l, { id, text, kind }]);
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap" role="status" aria-live="polite">
        {list.map((t) => <div key={t.id} className="toast"><Ic name={t.kind === "err" ? "x" : "check"} size={16} /><span>{t.text}</span></div>)}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------- form pieces (mock: F() · pulled() · checks · switch) ---------- */
export function Field({ label, children, full, hint, pulled }: { label: ReactNode; children: (id: string) => ReactNode; full?: boolean; hint?: ReactNode; pulled?: string }) {
  const id = useId();
  return (
    <div className={`field ${full ? "full" : ""}`}>
      <label htmlFor={id}>{label}{pulled && <Pulled src={pulled} />}</label>
      {children(id)}
      {hint && <span className="small faint">{hint}</span>}
    </div>
  );
}

export function FormGrid({ children }: { children: ReactNode }) {
  return <div className="form-grid">{children}</div>;
}

/** Badge of a value the system fills from another source (mock: "ดึงอัตโนมัติ" · SUPREME · HURIS). */
export function Pulled({ src }: { src: string }) {
  return <span className="pulled"><Ic name="link" size={11} width={2} /> {src}</span>;
}

/** Badge of data that comes from a sample adapter until the real system is connected (plan FS-0c). */
export function SampleData({ source }: { source: string }) {
  return <span className="pill p-warn" title={`ยังไม่เชื่อม ${source} จริง ใช้ข้อมูลตัวอย่าง`}>ข้อมูลตัวอย่าง · {source}</span>;
}

export function Check({ checked, onChange, children, disabled }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; disabled?: boolean }) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {children}
    </label>
  );
}

export function Switch({ on, onChange, label, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "on" : ""}`} disabled={disabled} onClick={() => onChange(!on)}>
      <span className="knob" />
    </button>
  );
}

/* ---------- small displays ---------- */
export function Bar({ pct, color = "var(--red)", label }: { pct: number; color?: string; label?: string }) {
  const v = Math.max(0, Math.min(100, pct));
  return <div className="bar" role="img" aria-label={label ?? `${Math.round(v)}%`}><span style={{ width: `${v}%`, background: color }} /></div>;
}

export function Legend({ items }: { items: readonly (readonly [string, ReactNode])[] }) {
  return <div className="legend">{items.map(([c, t], i) => <span key={i}><i className="sw" style={{ background: c }} />{t}</span>)}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function BackLink({ href, children = "กลับ" }: { href: string; children?: ReactNode }) {
  return <Link href={href} className="btn sm ghost" style={{ alignSelf: "flex-start", paddingLeft: 4 }}><Ic name="back" size={16} /> {children}</Link>;
}

export type Step = { title: string; detail?: string; state?: "done" | "cur" | "rej" };
export function Timeline({ steps }: { steps: readonly Step[] }) {
  return (
    <div className="timeline">
      {steps.map((s, i) => (
        <div key={i} className={`tl ${s.state ?? ""}`}>
          <span className="dot">{s.state === "done" ? "✓" : s.state === "rej" ? "!" : i + 1}</span>
          <div><b style={{ fontSize: 14 }}>{s.title}</b>{s.detail && <div className="small faint">{s.detail}</div>}</div>
        </div>
      ))}
    </div>
  );
}

/** Radar of 0–5 scores (mock radarSVG: Skill Portfolio, dashboards). Fewer than 3 axes: use bars instead. */
export function Radar({ items, color = "var(--red)", size = 260, labels = true }: { items: readonly (readonly [string, number])[]; color?: string; size?: number; labels?: boolean }) {
  const n = items.length;
  if (n < 3) {
    return (
      <div className="stack" style={{ gap: 8 }}>
        {items.map(([l, v]) => <div key={l}><div className="between small"><span>{l}</span><b className="num">{v.toFixed(2)}</b></div><Bar pct={(v / RADAR.max) * 100} color={color} /></div>)}
      </div>
    );
  }
  return (
    <svg viewBox={`0 0 ${RADAR.width} ${RADAR.height}`} width={size} role="img" aria-label={items.map(([l, v]) => `${l} ${v.toFixed(2)}`).join(", ")}>
      {[0.2, 0.4, 0.6, 0.8, 1].map((f) => <polygon key={f} points={radarRing(n, f)} fill="none" stroke="var(--line)" />)}
      {items.map((_, i) => { const p = radarPoint(i, n, 1); return <line key={i} x1={RADAR.cx} y1={RADAR.cy} x2={p[0]} y2={p[1]} stroke="var(--line)" />; })}
      <polygon points={radarPolygon(items.map(([, v]) => v))} fill={color} fillOpacity={0.18} stroke={color} strokeWidth={2} />
      {labels && items.map(([l], i) => { const p = radarPoint(i, n, 1.24); return <text key={l} x={p[0]} y={p[1] + 4} textAnchor={labelAnchor(p)} fontSize={12} fill="var(--fg-2)">{l}</text>; })}
    </svg>
  );
}
