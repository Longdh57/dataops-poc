"use client";

// Danh tinh nguoi dang dang nhap. Khi IAP da bat, phan nay chi hien thi —
// danh tinh den tu JWT do Google ky. Khi chua bat (REQUIRE_IAP=false),
// them bo chon de thay phan quyen hoat dong that.
//
// Danh sach nguoi doi duoc lay tu /api/users chu khong con go cung trong
// ma nguon: tai khoan tao o man hinh Nguoi dung phai xuat hien ngay o day,
// khong thi tao xong roi khong co cach nao thu.

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/app/i18n/context";
import { useMe, useSwitchableUsers } from "@/app/lib/queries";

const COOKIE = "dataops_as";

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

  // Chi goi khi bo chon that su dung duoc. Bat IAP len thi endpoint nay
  // khong con, va bo chon cung dang bi khoa.
  const devMode = me?.require_iap === false;
  const { data: users } = useSwitchableUsers(devMode);
  const isAdmin = me?.roles?.includes("admin") ?? false;

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

  // Server da loc tai khoan bi tat: chung khong dang nhap duoc
  // (authz.load_principal chan), dua vao day chi de nguoi dung bam roi an 403.
  const rows = users?.rows ?? [];

  return (
    <div style={{ position: "relative" }}>
      <button
        className="btn btn-sm"
        onClick={() => setOpen((v) => !v)}
        disabled={!devMode}
        title={devMode ? t("identity.switchDev") : t("identity.fromIap")}
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
          style={{ position: "absolute", right: 0, top: 36, width: 300, zIndex: 30, padding: 9 }}
        >
          <div className="stat-label" style={{ padding: "2px 6px 7px" }}>
            {t("identity.signInAs")}
          </div>

          {rows.length === 0 ? (
            <div className="hint" style={{ padding: "0 6px 6px" }}>
              {t("identity.empty")}
            </div>
          ) : null}

          {rows.map((u) => (
            <button
              key={u.email}
              className="btn btn-sm identity-pick"
              data-on={u.email === me?.email ? "1" : "0"}
              onClick={() => pick(u.email)}
            >
              <span>{u.display_name || u.email}</span>
              <span className="mono identity-pick-mail">{u.email}</span>
              <span className="identity-pick-role">
                <span className="pill pill-accent">{u.role ?? "—"}</span>
                <span className="pill">
                  {u.scope_states?.length ? u.scope_states.join(", ") : t("common.all")}
                </span>
              </span>
            </button>
          ))}

          {isAdmin ? (
            <Link
              href="/users"
              className="btn btn-sm"
              style={{ display: "block", textAlign: "center", marginTop: 6 }}
              onClick={() => setOpen(false)}
            >
              {t("identity.manage")}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
