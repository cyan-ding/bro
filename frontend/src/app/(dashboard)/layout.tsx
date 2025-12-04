import { AppSidebar } from "@/components/ui/app-sidebar";
import { DashboardNavbar } from "@/components/ui/dashboard-navbar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <DashboardNavbar />
      <main className="flex flex-1 flex-col">
        <SidebarTrigger />
        {children}
      </main>
    </SidebarProvider>
  );
}
