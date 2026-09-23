"use client";

// Danh tinh nguoi dang dang nhap. Khi IAP da bat, phan nay chi hien thi —
// danh tinh den tu JWT do Google ky. Khi chua bat (REQUIRE_IAP=false),
// them bo chon de thay phan quyen hoat dong that.

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { useMe } from "@/app/lib/queries";

const COOKIE = "dataops_as";

export const DEV_USERS: { email: string; label: MessageKey }[] = [
  { email: "longbloginfo@gmail.com", label: "identity.user.admin" },
  { email: "lead@dataops.test", label: "identity.user.lead" },
  { email: "analyst.tx@dataops.test", label: "identity.user.analystTx" },
  { email: "analyst.ca@dataops.test", label: "identity.user.analystCa" },
];

function setCookie(email: string) {
  document.cookie = `${COOKIE}=${encodeURIComponent(email)}; path=/; max-age=2592000; samesite=lax`;
}

function readCookie(): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${COOKIE}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

export default function Identity() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [open, setOpen] = useState(false);

  // Giu duong link cu cua README: /?as=analyst.tx@dataops.test
  //
  // Tai lai nguyen trang chu khong chi invalidate: luc trang vua mo, cac
  // query dau tien da bay di voi cookie CU roi. Ket qua cu ve sau se de
  // len ket qua moi. Tai lai la cach duy nhat chac chan dung.
  const asParam = sp.get("as");
  useEffect(() => {
    if (!asParam) return;
    const next = new URLSearchParams(sp.toString());
    next.delete("as");
    const clean = next.toString() ? `${pathname}?${next}` : pathname;
    if (readCookie() === asParam) {
      router.replace(clean, { scroll: false });
      return;
    }
    setCookie(asParam);
    window.location.replace(clean);
  }, [asParam, pathname, router, sp]);

  function pick(email: string) {
    setCookie(email);
    setOpen(false);
    qc.invalidateQueries();
  }

  // API tra ve chuoi "tat ca" khi pham vi khong bi gioi han — do la mot
  // ma, khong phai cau tieng Viet, nen dich lai o day.
  const scope = Array.isArray(me?.scope_states)
    ? me.scope_states.join(", ")
    : me?.scope_states
      ? t("common.all")
      : undefined;

  return (
    <div style={{ position: "relative" }}>
      <button
        className="btn btn-sm"
        onClick={() => setOpen((v) => !v)}
        disabled={me?.require_iap !== false}
        title={me?.require_iap ? t("identity.fromIap") : t("identity.switchDev")}
      >
        <span className="mono" style={{ fontSize: 11.5 }}>
          {me?.email ?? "…"}
        </span>
        <span className="pill pill-accent">{me?.roles?.join(" · ") ?? "—"}</span>
        <span className="pill">{scope ?? "—"}</span>
      </button>

      {open ? (
        <div
          className="card"
          style={{ position: "absolute", right: 0, top: 36, width: 280, zIndex: 30, padding: 9 }}
        >
          <div className="stat-label" style={{ padding: "2px 6px 7px" }}>
            {t("identity.signInAs")}
          </div>
          {DEV_USERS.map((u) => (
            <button
              key={u.email}
              className="btn btn-sm"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                border: 0,
                marginBottom: 2,
                background: u.email === me?.email ? "var(--accent-soft)" : "transparent",
                color: u.email === me?.email ? "var(--accent)" : "var(--ink2)",
              }}
              onClick={() => pick(u.email)}
            >
              {t(u.label)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
