import { NextRequest } from "next/server";
import { apiCall } from "@/auth";

// ขอรหัสเข้าสู่ระบบทางอีเมล (US-U-02): before sign-in, so no session; the API checks that the
// address was invited and is still allowed, and sends the code through the outbox.
export async function POST(req: NextRequest) {
  let email = "";
  try { email = String((await req.json()).email ?? ""); } catch { /* empty body */ }
  if (!email.includes("@")) return Response.json({ detail: "กรอกอีเมลที่ได้รับเชิญ" }, { status: 400 });
  const r = await apiCall("otp/request", { email });
  const body = await r.json().catch(() => ({ detail: "ขอรหัสไม่สำเร็จ" }));
  return Response.json(body, { status: r.status });
}
