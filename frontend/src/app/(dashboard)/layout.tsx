"use client"

import { AppSidebar } from "@/components/AppSidebar";
import { DashboardNavbar } from "@/components/ui/dashboard-navbar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useAgentStore } from "@/store/useAgentStore";


export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { runs } = useAgentStore();

  return (
    <SidebarProvider>
      <div className="grid grid-cols-[auto_1fr] grid-rows-1 min-h-svh w-screen">
        <AppSidebar runs={runs}/>
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
