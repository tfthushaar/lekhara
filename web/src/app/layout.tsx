import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Horus", template: "%s | Horus" },
  description: "Outside obligations for Karnataka real estate projects",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
