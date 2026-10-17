import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Nav, PlainNav } from "@/components/nav";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Horus", template: "%s | Horus" },
  description: "Outside obligations for Karnataka real estate projects",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="topbar-inner">
            <Link href="/" className="wordmark">
              Horus
            </Link>
            <Suspense fallback={<PlainNav />}>
              <Nav />
            </Suspense>
          </div>
        </header>
        <main className="main">{children}</main>
      </body>
    </html>
  );
}
