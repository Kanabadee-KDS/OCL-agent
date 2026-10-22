import { NextRequest } from "next/server";
import { auth, apiToken, INTERNAL_API_BASE } from "@/auth";

// The browser never talks to FastAPI directly: every call goes through here with a
// short-lived token carrying the signed-in user's roles (ocl_api.auth).
async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const session = await auth();
  if (!session?.user?.email) return Response.json({ detail: "ต้องเข้าสู่ระบบก่อน" }, { status: 401 });
  const { path } = await ctx.params;
  const target = new URL(`${INTERNAL_API_BASE}/${path.join("/")}`);
  target.search = req.nextUrl.search;
  const token = await apiToken({ sub: session.user.email, name: session.user.name ?? "", roles: session.user.roles ?? [] });
  const headers = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  headers.set("authorization", `Bearer ${token}`);
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    // @ts-expect-error -- Node fetch needs duplex for streamed request bodies
    duplex: hasBody ? "half" : undefined,
    cache: "no-store",
    redirect: "manual",
  });
  const out = new Headers();
  for (const k of ["content-type", "content-length", "content-disposition", "cache-control"]) {
    const v = upstream.headers.get(k);
    if (v) out.set(k, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
