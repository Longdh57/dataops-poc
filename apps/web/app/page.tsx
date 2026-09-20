export const dynamic = "force-dynamic";

import { getIdToken } from "./api-client";
import DataView from "./data-view";

const API = process.env.API_URL ?? "http://localhost:8080";

async function call<T>(path: string): Promise<T | null> {
  try {
    const token = await getIdToken(API);
    const res = await fetch(`${API}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export default async function Home() {
  const [version, schema, facts] = await Promise.all([
    call<any>("/api/version"),
    call<any>("/api/schema"),
    call<any>("/api/facts?state=CA&year=2021&gender=F&limit=15"),
  ]);

  return <DataView version={version} schema={schema} facts={facts} apiUrl={API} />;
}
