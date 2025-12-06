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
      <div className="grid grid-cols-[auto_1fr] grid-rows-1 min-h-svh w-screen">
        <AppSidebar />
        <div className="grid grid-rows-[auto_1fr]">
          <div className="flex justify-between items-center">
            <SidebarTrigger />
            <DashboardNavbar />
          </div>
          {children}
        </div>
      </div>
    </SidebarProvider>
  );
}
