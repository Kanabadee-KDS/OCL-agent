import { redirect } from "next/navigation";
import { SessionProvider } from "next-auth/react";
import { auth } from "@/auth";
import { Shell } from "@/components/shell";
import { ToastProvider } from "@/components/kit";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session?.user?.email) redirect("/login");
  const roles = session.user.roles ?? [];
  const user = { name: session.user.name ?? session.user.email, email: session.user.email, roles };
  return (
    <SessionProvider session={session} refetchInterval={60}>
      {/* the refetch stores the minute-by-minute user re-check (auth.ts jwt) in the cookie;
          server components cannot write cookies, so without it every call would re-check */}
      {/* each page is checked against its menu in the Shell (lib/nav.ts); the API checks again */}
      <ToastProvider>
        <Shell user={user}>{children}</Shell>
      </ToastProvider>
    </SessionProvider>
  );
}
