"use client";

import { signOut } from "next-auth/react";

export function LogoutButton() {
  return (
    <button className="btn" style={{ height: 36 }} onClick={() => signOut({ callbackUrl: "/login" })} title="ออกจากระบบ">
      ออกจากระบบ
    </button>
  );
}
