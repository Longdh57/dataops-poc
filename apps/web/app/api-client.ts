// Tren Cloud Run: lay ID token tu metadata server de goi service khac.
// Duoi local (docker compose): metadata server khong ton tai -> tra null,
// va API local khong doi xac thuc. Mot doan code chay dung ca hai noi.

const METADATA_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";

// Moi thao tac tren giao dien deu di qua proxy, nen goi metadata server
// tung lan la lang phi. Token song mot tieng; giu lai va doi truoc han
// nam phut cho chac.
const cache = new Map<string, { token: string; expires: number }>();
const SKEW_MS = 5 * 60_000;

function expiryOf(jwt: string): number {
  try {
    const payload = JSON.parse(Buffer.from(jwt.split(".")[1], "base64").toString());
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

export async function getIdToken(audience: string): Promise<string | null> {
  const hit = cache.get(audience);
  if (hit && hit.expires - SKEW_MS > Date.now()) return hit.token;

  try {
    const res = await fetch(`${METADATA_URL}?audience=${encodeURIComponent(audience)}`, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return null;
    const token = await res.text();
    const expires = expiryOf(token);
    if (expires) cache.set(audience, { token, expires });
    return token;
  } catch {
    return null; // khong phai moi truong GCP
  }
}
