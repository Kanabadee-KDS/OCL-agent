import NextAuth, { type NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { SignJWT } from "jose";

export const INTERNAL_API_BASE = (process.env.INTERNAL_API_BASE ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const secret = () => new TextEncoder().encode(process.env.AUTH_SECRET ?? "");

/** HS256 token the API verifies (ocl_api.auth.verify_token). */
export async function apiToken(claims: { sub: string; name?: string; roles: string[] }, ttlSeconds = 300) {
  return new SignJWT({ name: claims.name ?? "", roles: claims.roles })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(claims.sub)
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + ttlSeconds)
    .sign(secret());
}

type Perms = Record<string, string[]>; // menu id -> actions (ocl_api.perms)
type ApiUser = {
  email: string; name: string; roles: string[]; active: boolean; perms: Perms;
  role_names: Record<string, string>; active_role: string | null;
};

async function apiCall(path: "lookup" | "credentials" | "refresh", body: Record<string, string>): Promise<Response> {
  const token = await apiToken({ sub: "web", name: "web", roles: ["service"] });
  return fetch(`${INTERNAL_API_BASE}/api/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}

async function apiAuth(path: "lookup" | "credentials", body: Record<string, string>): Promise<ApiUser | null> {
  const r = await apiCall(path, body);
  if (!r.ok) return null;
  return (await r.json()) as ApiUser;
}

// A session lives 8 hours; every RECHECK_SECONDS the user is read again so that a role change
// reaches the menus and a suspended user is signed out (the API checks the table on every call).
const RECHECK_SECONDS = 60;

/** Current user, "gone" when suspended or removed, null when the API cannot tell (keep the session). */
async function recheck(email: string, role?: string | null): Promise<ApiUser | "gone" | null> {
  try {
    const r = await apiCall("refresh", role ? { email, role } : { email });
    if (r.status === 404) return "gone";
    return r.ok ? ((await r.json()) as ApiUser) : null;
  } catch {
    return null;
  }
}

const googleOn = Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);

export const authConfig: NextAuthConfig = {
  trustHost: true,
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  pages: { signIn: "/login", error: "/login" },
  providers: [
    ...(googleOn ? [Google({ authorization: { params: { prompt: "select_account", hd: process.env.AUTH_ALLOWED_DOMAIN ?? "g.swu.ac.th" } } })] : []),
    Credentials({
      id: "buasri",
      name: "บัวศรีไอดี",
      credentials: { username: { label: "บัวศรีไอดี" }, password: { label: "รหัสผ่าน", type: "password" } },
      async authorize(c) {
        const u = await apiAuth("credentials", { username: String(c?.username ?? ""), password: String(c?.password ?? "") });
        return u ? { id: u.email, email: u.email, name: u.name, roles: u.roles, perms: u.perms, roleNames: u.role_names } : null;
      },
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        const u = await apiAuth("lookup", { email: user.email ?? "" });
        if (!u) return "/login?error=NotRegistered";
        Object.assign(user, { roles: u.roles, perms: u.perms, roleNames: u.role_names });
        user.name = u.name || user.name;
      }
      return true;
    },
    async jwt({ token, user, trigger, session }) {
      const now = Math.floor(Date.now() / 1000);
      if (user) {
        const u = user as { roles?: string[]; perms?: Perms; roleNames?: Record<string, string> };
        token.roles = u.roles ?? [];
        token.perms = u.perms ?? {};
        token.roleNames = u.roleNames ?? {};
        token.activeRole = null;
        token.checkedAt = now;
        return token;
      }
      // role switch from the top bar (useSession().update): re-read the menus of that group now
      if (trigger === "update" && session && "activeRole" in session) {
        token.activeRole = (session as { activeRole?: string | null }).activeRole || null;
        token.checkedAt = 0;
      }
      // sessions signed before FS-1a carry no menus: re-check them at once
      const fresh = token.perms && now - Number(token.checkedAt ?? 0) < RECHECK_SECONDS;
      if (!token.email || fresh) return token;
      const u = await recheck(token.email, token.activeRole as string | null | undefined);
      if (u === "gone") return null; // Auth.js clears the session cookie
      if (u) {
        token.roles = u.roles;
        token.perms = u.perms;
        token.roleNames = u.role_names;
        token.activeRole = u.active_role;
        token.name = u.name || token.name;
      }
      token.checkedAt = now;
      return token;
    },
    async session({ session, token }) {
      session.user.roles = (token.roles as string[] | undefined) ?? [];
      session.user.perms = (token.perms as Perms | undefined) ?? {};
      session.user.roleNames = (token.roleNames as Record<string, string> | undefined) ?? {};
      session.user.activeRole = (token.activeRole as string | null | undefined) ?? null;
      return session;
    },
  },
};

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
export const providersEnabled = { google: googleOn, buasri: true };
