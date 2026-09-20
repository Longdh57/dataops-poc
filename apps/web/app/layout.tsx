import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Suspense } from "react";

import "./globals.css";
import Providers from "./providers";
import Shell from "./ui/shell";

export const metadata: Metadata = {
  title: "Data Operations WebApp",
  description: "Noi xem so, sua so va chan so sai di ra ngoai",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <Providers>
          {/* Shell doc bo loc tu URL nen phai nam trong Suspense. */}
          <Suspense fallback={<div className="page">Đang tải…</div>}>
            <Shell>{children}</Shell>
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
