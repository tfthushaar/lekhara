import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Lekhara", template: "%s | Lekhara" },
  description: "Easy software for Karnataka builders: what is due, what you can draw, and what to do next",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
