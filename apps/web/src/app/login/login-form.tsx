"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { Ic, Note } from "@/components/ui";

export function LoginForm({ google, error, callbackUrl, forgot }: { google: boolean; error: string | null; callbackUrl: string; forgot?: string | null }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(error);
  const [ext, setExt] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState<string | null>(null);

  async function askCode() {
    setBusy(true);
    setErr(null);
    const r = await fetch("/api/otp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    const d = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) { setErr(d.detail ?? "ขอรหัสไม่สำเร็จ"); return; }
    setSent(`ส่งรหัสไปที่ ${email} แล้ว ใช้ได้ครั้งเดียวภายใน ${d.minutes ?? 10} นาที`);
  }
  async function submitCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const r = await signIn("otp", { email, code, redirect: false });
    if (r?.error) { setErr("รหัสไม่ถูกต้อง หมดอายุ หรือถูกใช้แล้ว"); setBusy(false); return; }
    window.location.href = callbackUrl;
  }

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
        {forgot && <a className="small" href={forgot} target="_blank" rel="noreferrer">ลืมรหัสผ่าน (บริการบัวศรีไอดี)</a>}
      </form>
      <button type="button" className="link-btn small" style={{ alignSelf: "flex-start" }} onClick={() => { setExt((x) => !x); setErr(null); }}>
        {ext ? "ซ่อน" : "ผู้ประเมินภายนอก: เข้าสู่ระบบด้วยอีเมลที่ได้รับเชิญ"}
      </button>
      {ext && (
        <form className="stack" style={{ gap: 10 }} onSubmit={submitCode}>
          <div className="field"><label htmlFor="ext-email">อีเมลที่ได้รับเชิญ</label><input id="ext-email" className="inp" type="email" autoComplete="email" value={email} onChange={(e) => { setEmail(e.target.value); setSent(null); }} required /></div>
          <button type="button" className="btn" disabled={busy || !email.includes("@")} onClick={askCode}>{sent ? "ขอรหัสใหม่" : "ส่งรหัสทางอีเมล"}</button>
          {sent && <Note kind="ok">{sent}</Note>}
          {sent && <div className="field"><label htmlFor="ext-code">รหัส 6 หลัก</label><input id="ext-code" className="inp num" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required /></div>}
          {sent && <button className="btn primary" style={{ height: 46 }} disabled={busy || code.length !== 6}>เข้าสู่ระบบ</button>}
        </form>
      )}
    </div>
  );
}
