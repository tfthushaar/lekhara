import { SiteFooter, SiteHeader } from "@/components/site";

/** The public website: what Lekhara is, its price and how to reach us. */
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="site">{children}</main>
      <SiteFooter />
    </>
  );
}
