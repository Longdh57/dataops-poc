// Goi API qua proxy /api/gw. Loi HTTP nem ra ApiError con nguyen status
// va detail — man hinh ngoai le doc status 409 de hien diff xung dot.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `API loi ${status}`);
  }
}

export async function gw<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/gw${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body);
  return body as T;
}

export const post = <T,>(path: string, body: unknown) =>
  gw<T>(path, { method: "POST", body: JSON.stringify(body) });

export const patch = <T,>(path: string, body: unknown) =>
  gw<T>(path, { method: "PATCH", body: JSON.stringify(body) });

/** Ghep query string, bo qua gia tri rong. */
export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
