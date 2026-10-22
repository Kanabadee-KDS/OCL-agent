"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { Ic, Note } from "@/components/ui";

export function LoginForm({ google, error, callbackUrl }: { google: boolean; error: string | null; callbackUrl: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(error);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const r = await signIn("buasri", { username, password, redirect: false });
    if (r?.error) {
      setErr("บัวศรีไอดีหรือรหัสผ่านไม่ถูกต้อง");
      setBusy(false);
      return;
    }
    window.location.href = callbackUrl;
  }

  return (
    <div className="login-card">
      <div>
        <h2 className="h2" style={{ fontSize: 22 }}>เข้าสู่ระบบ</h2>
        <div className="small faint">เลือกวิธีเข้าสู่ระบบ</div>
      </div>
      {err && <Note kind="warn">{err}</Note>}
      {google ? (
        <button className="btn" style={{ height: 46 }} onClick={() => signIn("google", { callbackUrl })}>
          <Ic name="user" size={18} /> เข้าสู่ระบบด้วย Google (@g.swu.ac.th)
        </button>
      ) : (
        <div className="small faint" style={{ padding: "8px 10px", border: "1px dashed var(--line-2)", borderRadius: 10 }}>
          Google SSO ยังไม่เปิด: รอ OAuth client จาก มศว และต้องมีชื่อโดเมน (Google ไม่รับ redirect ที่เป็น IP) · ใช้บัวศรีไอดีไปก่อน
        </div>
      )}
      <div className="row" style={{ alignItems: "center", gap: 10 }}>
        <div className="hr" style={{ flex: 1 }} /><span className="small faint">หรือ</span><div className="hr" style={{ flex: 1 }} />
      </div>
      <form className="stack" style={{ gap: 12 }} onSubmit={submit}>
        <div className="field"><label>บัวศรีไอดี</label><input className="inp" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
        <div className="field"><label>รหัสผ่าน</label><input className="inp" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <button className="btn primary" style={{ height: 46 }} disabled={busy}>{busy ? "กำลังตรวจสอบ…" : "เข้าสู่ระบบ"}</button>
      </form>
    </div>
  );
}
