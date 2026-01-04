import { MarketingNavbar } from "@/components/ui/marketing-navbar";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <MarketingNavbar />
      <main className="flex flex-1 flex-col justify-center">{children}</main>
    </>
  );
}
