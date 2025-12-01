import { AppSidebar } from "@/components/ui/app-sidebar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

export default function DashboardLayout({
    children
}: { children: React.ReactNode }) {
    return (
        <SidebarProvider>
            <AppSidebar />
            <main className="flex flex-1 flex-col">
                <SidebarTrigger />
                {children}
            </main>

        </SidebarProvider>
    )
}