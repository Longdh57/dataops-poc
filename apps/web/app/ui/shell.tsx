"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useGate, useOpenCount } from "@/app/lib/queries";

import FilterBar from "./filter-bar";
import Identity from "./identity";
import StatusStrip from "./status-strip";

const TABS = [
  { href: "/", label: "Dashboard" },
  { href: "/data", label: "Dữ liệu" },
  { href: "/exceptions", label: "Ngoại lệ", badge: true },
  { href: "/versions", label: "Phiên bản" },
  { href: "/requests", label: "Yêu cầu dữ liệu" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: gate } = useGate();
  const { data: count } = useOpenCount();
  const open = count?.total ?? 0;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            Data Operations
            <span>dataops · poc</span>
          </div>
          <nav className="tabs">
            {TABS.map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className="tab"
                data-on={pathname === t.href ? "1" : "0"}
              >
                {t.label}
                {t.badge && open ? (
                  <span className="tab-badge" title={gate?.locked ? "cổng phát hành đang khoá" : ""}>
                    {open}
                  </span>
                ) : null}
              </Link>
            ))}
          </nav>
          <Identity />
        </div>
      </header>

      <FilterBar />

      <main className="page">
        <StatusStrip />
        {children}
      </main>
    </>
  );
}
