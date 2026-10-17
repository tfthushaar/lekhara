import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Lekhara", template: "%s | Lekhara" },
  description: "Outside obligations for Karnataka real estate projects",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
