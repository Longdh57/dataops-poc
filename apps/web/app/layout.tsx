import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Suspense } from "react";

import "./globals.css";
import { getLocale } from "./i18n/server";
import { translate } from "./i18n/translate";
import Providers from "./providers";
import Shell from "./ui/shell";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getLocale();
  return {
    title: translate(locale, "meta.title"),
    description: translate(locale, "meta.description"),
  };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Ngon ngu doc tu cookie ngay o day chu khong doi client: HTML dau tien
  // da dung thu tieng roi, va <html lang> dung cho trinh doc man hinh.
  const locale = await getLocale();

  return (
    <html lang={locale}>
      <body>
        <Providers locale={locale}>
          {/* Shell doc bo loc tu URL nen phai nam trong Suspense. */}
          <Suspense fallback={<div className="page">{translate(locale, "common.loadingShort")}</div>}>
            <Shell>{children}</Shell>
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
