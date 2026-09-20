// Cong duy nhat trinh duyet goi API qua.
//
// Tren Cloud Run, dataops-api KHONG public: chi service account cua web
// goi duoc bang OIDC token. Trinh duyet khong co token do, nen moi request
// di vong qua day — Next.js lay token tu metadata server roi goi tiep.
//
// Danh tinh: co IAP thi chuyen tiep nguyen assertion cua Google (API tu
// verify chu ky). Chua co IAP thi lay tu cookie dev — duong nay chi mo khi
// REQUIRE_IAP=false.

import type { NextRequest } from "next/server";

import { getIdToken } from "@/app/api-client";

export const dynamic = "force-dynamic";

const API = process.env.API_URL ?? "http://localhost:8080";
const IAP_HEADER = "x-goog-iap-jwt-assertion";
const DEV_COOKIE = "dataops_as";
const DEV_FALLBACK = process.env.DEV_USER ?? "longbloginfo@gmail.com";

async function forward(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${API}/api/${path.join("/")}${new URL(req.url).search}`;
  const headers: Record<string, string> = { "content-type": "application/json" };

  const token = await getIdToken(API);
  if (token) headers.authorization = `Bearer ${token}`;

  const iap = req.headers.get(IAP_HEADER);
  if (iap) headers[IAP_HEADER] = iap;
  else headers["x-dev-user"] = req.cookies.get(DEV_COOKIE)?.value ?? DEV_FALLBACK;

  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();

  try {
    const res = await fetch(target, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    return Response.json(
      { detail: `khong goi duoc API: ${(err as Error).message}` },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return forward(req, (await ctx.params).path);
}
