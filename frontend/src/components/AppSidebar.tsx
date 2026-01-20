import { MoreVerticalIcon, PlusIcon, TrashIcon } from "lucide-react";
import { useState } from "react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { ListRunsResponse } from "@/lib/models";
import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";
import { useAgentStore } from "@/store/useAgentStore";
import { useRouter } from "next/navigation";
import { deleteRun } from "@/lib/api";

interface SidebarProps {
  runs: ListRunsResponse[],
  setRuns: (runs: ListRunsResponse[]) => void;
}

export function AppSidebar({ runs, setRuns }: SidebarProps) {
  const router = useRouter();
  const { clearAll } = useAgentStore();
  const { theme, resolvedTheme } = useTheme();
  const isDark = (theme ? (theme === "dark") : resolvedTheme === "dark");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [runToDelete, setRunToDelete] = useState<string | null>(null);

  const handleNewRun = () => {
    clearAll();
    router.push("/dashboard");
  };

  const handleDeleteClick = (runId: string) => {
    setRunToDelete(runId);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!runToDelete) return;

    try {
      await deleteRun(runToDelete);
      setRuns(runs.filter(run => run.id !== runToDelete))
      setDeleteDialogOpen(false);
      setRunToDelete(null);
      router.refresh();
    } catch (error) {
      alert(`Failed to delete run: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a href="/dashboard">
                <div className="flex size-8 items-center justify-center rounded-lg">
                  <img src={isDark ? "/assets/bro_logo_dark.svg" : "/assets/bro_logo.svg"} alt="Bro logo" className="w-full h-full object-contain" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Bro</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <Button
              onClick={handleNewRun}
              className="w-full justify-start"
              variant="default"
            >
              <PlusIcon className="h-4 w-4" />
              New Run
            </Button>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Recent Runs</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {runs.slice().sort((a, b) => new Date(b.completed_at ?? 0).getTime() - new Date(a.completed_at ?? 0).getTime()).map((run) => (
                <SidebarMenuItem key={run.id}>
                  <div className="relative flex items-center w-full">
                    <SidebarMenuButton asChild className="flex-1">
                      <a href={`/runs?runId=${run.id}`}>
                        <span>{run.title}</span>
                      </a>
                    </SidebarMenuButton>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVerticalIcon className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem tabIndex={-1}
                          onClick={() => handleDeleteClick(run.id)}
                          className="text-destructive"
                        >
                          <TrashIcon className="h-4 w-4 mr-2" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail/>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Run</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this run? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  );
}
