// Tren Cloud Run: lay ID token tu metadata server de goi service khac.
// Duoi local (docker compose): metadata server khong ton tai -> tra null,
// va API local khong doi xac thuc. Mot doan code chay dung ca hai noi.

const METADATA_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";

export async function getIdToken(audience: string): Promise<string | null> {
  try {
    const res = await fetch(`${METADATA_URL}?audience=${encodeURIComponent(audience)}`, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    return res.ok ? await res.text() : null;
  } catch {
    return null; // khong phai moi truong GCP
  }
}
