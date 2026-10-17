import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Horus",
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
            <nav className="nav" aria-label="Main">
              <Link href="/">Today</Link>
            </nav>
          </div>
        </header>
        <main className="main">{children}</main>
      </body>
    </html>
  );
}
