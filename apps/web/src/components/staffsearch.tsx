"use client";

// Search the HURIS copy for a person to add (skill-assign, qa-assign).
import { useEffect, useState } from "react";
import { usersApi, type Staff } from "@/lib/api";

export function StaffSearch({ onPick, exclude, label = "ค้นบุคลากร" }: { onPick: (s: Staff) => void; exclude: string[]; label?: string }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Staff[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(() => { usersApi.staff(q).then((r) => setFound(r.items)).catch(() => setFound([])); }, 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="stack" style={{ gap: 4 }}>
      <input className="inp" aria-label={label} placeholder="พิมพ์ชื่อหรือรหัสบุคลากร (ระบบบุคลากร) เพื่อเพิ่ม" value={q} onChange={(e) => setQ(e.target.value)} />
      {q.trim().length >= 2 && found.filter((s) => !exclude.includes(s.pid)).map((s) => (
        <button key={s.pid} type="button" className="card" style={{ padding: "6px 10px", textAlign: "left", cursor: "pointer" }} onClick={() => { onPick(s); setQ(""); }}>
          <b>{s.title_short}{s.name_th}</b> <span className="small faint">{s.pid} · {s.faculty}</span>
        </button>
      ))}
    </div>
  );
}
