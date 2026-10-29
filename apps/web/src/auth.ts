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

type ApiUser = { email: string; name: string; roles: string[]; active: boolean };

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
async function recheck(email: string): Promise<ApiUser | "gone" | null> {
  try {
    const r = await apiCall("refresh", { email });
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
        return u ? { id: u.email, email: u.email, name: u.name, roles: u.roles } : null;
      },
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        const u = await apiAuth("lookup", { email: user.email ?? "" });
        if (!u) return "/login?error=NotRegistered";
        (user as { roles?: string[] }).roles = u.roles;
        user.name = u.name || user.name;
      }
      return true;
    },
    async jwt({ token, user }) {
      const now = Math.floor(Date.now() / 1000);
      if (user) {
        token.roles = (user as { roles?: string[] }).roles ?? [];
        token.checkedAt = now;
        return token;
      }
      if (!token.email || now - Number(token.checkedAt ?? 0) < RECHECK_SECONDS) return token;
      const u = await recheck(token.email);
      if (u === "gone") return null; // Auth.js clears the session cookie
      if (u) {
        token.roles = u.roles;
        token.name = u.name || token.name;
      }
      token.checkedAt = now;
      return token;
    },
    async session({ session, token }) {
      session.user.roles = (token.roles as string[] | undefined) ?? [];
      return session;
    },
  },
};

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
export const providersEnabled = { google: googleOn, buasri: true };
