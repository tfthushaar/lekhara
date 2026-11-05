import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

// Self-hosted at build time: no request goes to Google when a page loads.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Lekhara", template: "%s | Lekhara" },
  description: "Easy software for Karnataka builders: what is due, what you can draw, and what to do next",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
