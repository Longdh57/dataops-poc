import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Data Operations WebApp",
  description: "Noi xem so, sua so va chan so sai di ra ngoai",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body
        style={{
          margin: 0,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          background: "#F5F7F9",
          color: "#131A21",
        }}
      >
        {children}
      </body>
    </html>
  );
}
