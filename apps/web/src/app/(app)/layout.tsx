import { redirect } from "next/navigation";
import { SessionProvider } from "next-auth/react";
import { auth } from "@/auth";
import { Shell } from "@/components/shell";
import { Note } from "@/components/ui";
import { can, roleLabel } from "@/lib/perm";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session?.user?.email) redirect("/login");
  const roles = session.user.roles ?? [];
  const user = { name: session.user.name ?? session.user.email, email: session.user.email, roles };
  return (
    <SessionProvider session={session}>
      <Shell user={user}>
        {can(roles, "import_read") ? (
          children
        ) : (
          <section className="card pad stack" style={{ maxWidth: 720 }}>
            <h1 className="h1">ไม่มีสิทธิ์ในเมนูนี้</h1>
            <Note kind="warn">
              บัญชี {user.email} มีบทบาท {roleLabel(roles)} ซึ่งไม่ครอบคลุมเมนู &ldquo;นำเข้าข้อมูลเล่มหลักสูตรด้วย AI&rdquo; (เปิดให้ ผู้ดูแลระบบ · ผู้ดูแลส่วนกลาง · ผู้ตรวจสอบระดับหลักสูตร · ผู้ตรวจสอบระดับส่วนงาน) ติดต่อผู้ดูแลส่วนกลางหากต้องการสิทธิ์เพิ่ม
            </Note>
          </section>
        )}
      </Shell>
    </SessionProvider>
  );
}
