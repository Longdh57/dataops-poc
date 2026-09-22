"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { useGate, useOpenCount, useTickets } from "@/app/lib/queries";

import FilterBar from "./filter-bar";
import Identity from "./identity";
import LangSwitch from "./lang-switch";
import StatusStrip from "./status-strip";

const TABS: { href: string; label: MessageKey; badge?: string }[] = [
  { href: "/", label: "nav.dashboard" },
  { href: "/data", label: "nav.data" },
  { href: "/exceptions", label: "nav.exceptions", badge: "vi_pham" },
  { href: "/tickets", label: "nav.tickets", badge: "ticket" },
  { href: "/versions", label: "nav.versions" },
  { href: "/requests", label: "nav.requests" },
  { href: "/agent", label: "nav.agent" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useI18n();
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
            {t("shell.brand")}
            <span>dataops · poc</span>
          </div>
          <nav className="tabs">
            {TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className="tab"
                data-on={pathname === tab.href ? "1" : "0"}
              >
                {t(tab.label)}
                {tab.badge && badges[tab.badge] ? (
                  <span
                    className="tab-badge"
                    data-crit={tab.badge === "ticket" && tickets?.blocking_open ? "1" : "0"}
                    title={
                      tab.badge === "ticket" && tickets?.blocking_open
                        ? t("shell.badgeBlocking", { n: tickets.blocking_open })
                        : gate?.locked
                          ? t("shell.badgeGateLocked")
                          : ""
                    }
                  >
                    {badges[tab.badge]}
                  </span>
                ) : null}
              </Link>
            ))}
          </nav>
          <LangSwitch />
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
