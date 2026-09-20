// Server component: doc API_URL luc CHAY, khong phai luc build.
// Nho vay mot image dung duoc cho moi moi truong.
export const dynamic = "force-dynamic";

import StatusRow from "./status-row";
import { getIdToken } from "./api-client";

type Health = {
  status: string;
  service: string;
  database: { connected: boolean; server?: string; error?: string };
};

async function probeApi(url: string): Promise<{ ok: boolean; data?: Health; error?: string }> {
  try {
    const token = await getIdToken(url);
    const res = await fetch(`${url}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    return { ok: true, data: (await res.json()) as Health };
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function Home() {
  const apiUrl = process.env.API_URL ?? "http://localhost:8080";
  const probe = await probeApi(apiUrl);
  const db = probe.data?.database;

  return (
    <main style={{ maxWidth: 680, margin: "0 auto", padding: "64px 20px" }}>
      <p
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: 11.5,
          letterSpacing: ".14em",
          textTransform: "uppercase",
          color: "#0F6B7B",
          margin: "0 0 14px",
        }}
      >
        Kiem tra duong day
      </p>
      <h1 style={{ fontSize: 32, margin: "0 0 24px", letterSpacing: "-.02em" }}>
        Data Operations WebApp
      </h1>

      <StatusRow label="Web (Next.js)" ok detail="dang chay" />
      <StatusRow
        label="API (FastAPI)"
        ok={probe.ok}
        detail={probe.ok ? (probe.data?.service ?? "ok") : `${apiUrl} — ${probe.error}`}
      />
      <StatusRow
        label="Postgres"
        ok={db?.connected === true}
        detail={db?.connected ? (db.server ?? "ket noi duoc") : (db?.error ?? "chua goi toi duoc API")}
      />

      <p style={{ marginTop: 32, fontSize: 13.5, color: "#6B7884" }}>
        API_URL = <code>{apiUrl}</code>
      </p>
    </main>
  );
}
