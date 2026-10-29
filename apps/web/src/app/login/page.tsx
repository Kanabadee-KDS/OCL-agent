import { redirect } from "next/navigation";
import { auth, providersEnabled } from "@/auth";
import { LoginForm } from "./login-form";

const ERRORS: Record<string, string> = {
  NotRegistered: "บัญชีนี้ยังไม่ได้รับสิทธิ์ในระบบ ติดต่อผู้ดูแลส่วนกลางเพื่อกำหนดบทบาท",
  CredentialsSignin: "บัวศรีไอดีหรือรหัสผ่านไม่ถูกต้อง",
  AccessDenied: "บัญชีนี้ไม่ได้รับอนุญาต (ต้องเป็นบัญชี @g.swu.ac.th ที่ลงทะเบียนแล้ว)",
  Configuration: "ระบบยังไม่ได้ตั้งค่าการเข้าสู่ระบบ (AUTH_SECRET) ติดต่อผู้ดูแล",
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string; callbackUrl?: string }> }) {
  const session = await auth();
  const sp = await searchParams;
  if (session?.user) redirect(sp.callbackUrl || "/");
  const error = sp.error ? ERRORS[sp.error] ?? `เข้าสู่ระบบไม่สำเร็จ (${sp.error})` : null;
  return (
    <div className="login">
      <section className="login-brand">
        <div>
          <span className="av" style={{ background: "#fff", color: "var(--red)", width: 44, height: 44, fontSize: 15 }}>มศว</span>
          <h1 style={{ fontFamily: "var(--f-display)", fontSize: 28, lineHeight: 1.3, marginTop: 18 }}>
            ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล
          </h1>
          <p style={{ opacity: 0.85, marginTop: 8 }}>Skill Transcript · มหาวิทยาลัยศรีนครินทรวิโรฒ</p>
        </div>
        <p style={{ fontSize: 13, opacity: 0.75 }}>ผู้ใช้ภายในเข้าด้วยบัญชี Google @g.swu.ac.th หรือบัวศรีไอดี · ผู้ประเมินภายนอกเข้าด้วยอีเมลที่ได้รับเชิญ</p>
      </section>
      <section className="login-side">
        <div />
        <LoginForm google={providersEnabled.google} error={error} callbackUrl={sp.callbackUrl || "/"} />
        <p className="small faint" style={{ textAlign: "center" }}>ปัญหาการเข้าใช้ติดต่อผู้ดูแลส่วนกลาง (ฝ่ายวิชาการ)</p>
      </section>
    </div>
  );
}
