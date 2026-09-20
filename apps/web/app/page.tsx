export const dynamic = "force-dynamic";

import { getIdToken } from "./api-client";
import DataView from "./data-view";

const API = process.env.API_URL ?? "http://localhost:8080";

// IAP chua bat duoc nen trinh duyet khong mang danh tinh. Cho phep chon
// danh tinh qua ?as=... de thay ro phan quyen hoat dong. CHI dung khi
// REQUIRE_IAP=false; bat IAP len thi danh tinh den tu JWT cua Google.
const USERS = [
  { email: "longbloginfo@gmail.com", label: "Admin — toàn quyền" },
  { email: "lead@dataops.test", label: "Team Lead — ký phát hành" },
  { email: "analyst.tx@dataops.test", label: "Analyst — chỉ Texas" },
  { email: "analyst.ca@dataops.test", label: "Analyst — chỉ California" },
  { email: "sale@dataops.test", label: "Sale — CA + TX" },
];

async function call<T>(path: string, as: string): Promise<T | null> {
  try {
    const token = await getIdToken(API);
    const headers: Record<string, string> = { "X-Dev-User": as };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
      headers,
    });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ as?: string }>;
}) {
  const sp = await searchParams;
  const as = USERS.some((u) => u.email === sp.as) ? sp.as! : USERS[0].email;

  const [me, version, gate, exceptions, facts] = await Promise.all([
    call<any>("/api/me", as),
    call<any>("/api/version", as),
    call<any>("/api/gate", as),
    call<any>("/api/exceptions?limit=12", as),
    call<any>("/api/facts?limit=12", as),
  ]);

  return (
    <DataView
      users={USERS}
      current={as}
      me={me}
      version={version}
      gate={gate}
      exceptions={exceptions}
      facts={facts}
    />
  );
}
