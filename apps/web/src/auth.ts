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

async function apiAuth(path: "lookup" | "credentials", body: Record<string, string>): Promise<ApiUser | null> {
  const token = await apiToken({ sub: "web", name: "web", roles: ["service"] });
  const r = await fetch(`${INTERNAL_API_BASE}/api/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) return null;
  return (await r.json()) as ApiUser;
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
      if (user) token.roles = (user as { roles?: string[] }).roles ?? [];
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
