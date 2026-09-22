"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useGate, useOpenCount, useTickets } from "@/app/lib/queries";

import FilterBar from "./filter-bar";
import Identity from "./identity";
import StatusStrip from "./status-strip";

const TABS = [
  { href: "/", label: "Dashboard" },
  { href: "/data", label: "Dữ liệu" },
  { href: "/exceptions", label: "Vi phạm", badge: "vi_pham" },
  { href: "/tickets", label: "Ticket", badge: "ticket" },
  { href: "/versions", label: "Phiên bản" },
  { href: "/requests", label: "Yêu cầu dữ liệu" },
  { href: "/agent", label: "AI Agent" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: gate } = useGate();
  const { data: count } = useOpenCount();
  const { data: tickets } = useTickets();
  // Hai con so khac nhau va phai giu khac nhau: vi pham la nghi ngo cua
  // may o lan nap nay, ticket la loi da xac nhan dang cho nguon sua.
  const badges: Record<string, number> = {
    vi_pham: count?.total ?? 0,
    ticket: tickets?.total ?? 0,
  };

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
                {t.badge && badges[t.badge] ? (
                  <span
                    className="tab-badge"
                    data-crit={t.badge === "ticket" && tickets?.blocking_open ? "1" : "0"}
                    title={
                      t.badge === "ticket" && tickets?.blocking_open
                        ? `${tickets.blocking_open} ticket đang chặn phát hành`
                        : gate?.locked
                          ? "cổng phát hành đang khoá"
                          : ""
                    }
                  >
                    {badges[t.badge]}
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
