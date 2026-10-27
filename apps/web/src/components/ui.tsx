"use client";

import type { ReactNode } from "react";

const ICONS: Record<string, string> = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/>',
  book: '<path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M4 17a3 3 0 0 1 3-3h11"/>',
  plan: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M9 12h6M9 16h4"/>',
  skill: '<circle cx="12" cy="9" r="5.5"/><path d="M8.5 13.8L7 21l5-3 5 3-1.5-7.2"/>',
  qa: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  chart: '<path d="M5 20V11M11 20V5M17 20v-7M3 20h18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
  file: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  ai: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4"/>',
  send: '<path d="M4 12l16-8-6 16-2-7z"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
};

export function Ic({ name, size = 18, width = 1.8 }: { name: string; size?: number; width?: number }) {
  return (
    <svg
      className="ic"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICONS[name] || "" }}
    />
  );
}

export function Pill({ kind = "grey", children }: { kind?: "ok" | "warn" | "red" | "info" | "grey" | "dark"; children: ReactNode }) {
  return <span className={`pill p-${kind}`}>{children}</span>;
}

export const CONF_TH: Record<string, [string, "ok" | "warn" | "red"]> = {
  high: ["สูง", "ok"],
  medium: ["กลาง", "warn"],
  low: ["ต่ำ", "red"],
};

export function ConfPill({ meta }: { meta?: { confidence?: string } | null }) {
  const c = CONF_TH[meta?.confidence ?? ""] ?? ["–", "warn"];
  return <Pill kind={c[1]}>{c[0]}</Pill>;
}

export const STEPS = ["อัปโหลดเล่มหลักสูตร", "AI อ่านและสกัดข้อมูล", "ตรวจสอบความถูกต้อง", "ยืนยันบันทึกเข้าระบบ"];

export function Steps({ current }: { current: number }) {
  return (
    <div className="card pad">
      <div className="grid g4" style={{ gap: 10 }}>
        {STEPS.map((t, i) => (
          <div key={t} className="row" style={{ flexWrap: "nowrap" }}>
            <span
              className="av"
              style={i < current ? { background: "var(--ok)", color: "#fff" } : i === current ? { background: "var(--red)", color: "#fff" } : {}}
            >
              {i < current ? "✓" : i + 1}
            </span>
            <span style={{ fontWeight: i === current ? 600 : 400 }}>{t}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PageHead({ crumb, title, sub, actions }: { crumb: string[]; title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="crumb">
          {crumb.map((c, i) => (
            <span key={c}>
              {i > 0 && <span style={{ margin: "0 4px" }}>›</span>}
              {c}
            </span>
          ))}
        </div>
        <h1>{title}</h1>
        {sub && <div className="muted" style={{ marginTop: 4 }}>{sub}</div>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Note({ kind, children }: { kind: "info" | "warn" | "ok"; children: ReactNode }) {
  return <div className={`note ${kind}`}>{children}</div>;
}

/** Tiny Markdown renderer for the preview (headings, tables, bullets, paragraphs). */
export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  const esc = (s: string) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith("<!--")) { i++; continue; }
    const h = /^(#{1,6})\s+(.*)$/.exec(l);
    if (h) {
      const Tag = `h${Math.min(h[1].length, 3)}` as "h1" | "h2" | "h3";
      out.push(<Tag key={i} dangerouslySetInnerHTML={{ __html: esc(h[2]) }} />);
      i++; continue;
    }
    if (l.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].slice(1, lines[i].endsWith("|") ? -1 : undefined).split("|").map((c) => c.trim());
        if (!cells.every((c) => /^-{3,}$/.test(c))) rows.push(cells);
        i++;
      }
      out.push(
        <table key={`t${i}`}>
          <thead><tr>{rows[0]?.map((c, k) => <th key={k} dangerouslySetInnerHTML={{ __html: esc(c) }} />)}</tr></thead>
          <tbody>{rows.slice(1).map((r, ri) => <tr key={ri}>{r.map((c, k) => <td key={k} dangerouslySetInnerHTML={{ __html: esc(c) }} />)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
      out.push(<ul key={`u${i}`}>{items.map((it, k) => <li key={k} dangerouslySetInnerHTML={{ __html: esc(it) }} />)}</ul>);
      continue;
    }
    if (l.trim()) out.push(<p key={i} dangerouslySetInnerHTML={{ __html: esc(l) }} />);
    i++;
  }
  return <div className="paper">{out}</div>;
}
