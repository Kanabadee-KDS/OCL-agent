import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & {
      roles: string[];
      perms: Record<string, string[]>; // menu -> actions (of `activeRole` only when one is chosen)
      roleNames: Record<string, string>;
      activeRole: string | null;
    };
  }
}
