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
  const { runs, setRuns } = useAgentStore();

  return (
    <SidebarProvider>
      <div className="grid h-svh w-screen grid-cols-[auto_1fr] grid-rows-1">
        <AppSidebar runs={runs} setRuns={setRuns}/>
        <div className="grid h-svh min-h-0 grid-rows-[auto_1fr]">
          <div className="flex items-center justify-between">
            <SidebarTrigger />
            <DashboardNavbar />
          </div>
          <div className="min-h-0">{children}</div>
        </div>
      </div>
    </SidebarProvider>
  );
}
