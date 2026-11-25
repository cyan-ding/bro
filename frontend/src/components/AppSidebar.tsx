import { MoreVerticalIcon, PlusIcon, TrashIcon } from "lucide-react";
import { useEffect, useState } from "react";

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

import { ListRunsResponse, RunStatus } from "@/lib/models";
import { Button } from "@/components/ui/button";
import { useAgentStore } from "@/store/useAgentStore";
import { useRouter } from "next/navigation";
import { deleteRun } from "@/lib/api";

function isLive(status: RunStatus): boolean {
  return status === "running" || status === "awaiting_decision";
}

function orderedRuns(runs: ListRunsResponse[]): ListRunsResponse[] {
  return runs.slice().sort((a, b) => {
    if (isLive(a.status) !== isLive(b.status)) {
      return isLive(a.status) ? -1 : 1;
    }
    const aStarted = a.created_at ?? a.completed_at;
    const bStarted = b.created_at ?? b.completed_at;
    const aTime = aStarted ? new Date(aStarted).getTime() : 0;
    const bTime = bStarted ? new Date(bStarted).getTime() : 0;
    return bTime - aTime;
  });
}

function StatusDot({ status }: { status: RunStatus }) {
  if (status === "running") {
    return <span className="size-1.5 shrink-0 rounded-full bg-green-500" />;
  }
  if (status === "awaiting_decision") {
    return <span className="size-1.5 shrink-0 rounded-full bg-amber-500" />;
  }
  if (status === "error") {
    return <span className="size-1.5 shrink-0 rounded-full bg-destructive" />;
  }
  return <span className="size-1.5 shrink-0" />;
}

interface SidebarProps {
  runs: ListRunsResponse[],
  setRuns: (runs: ListRunsResponse[]) => void;
}

export function AppSidebar({ runs, setRuns }: SidebarProps) {
  const router = useRouter();
  const { clearAll } = useAgentStore();
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const update = () => setIsDark(root.classList.contains("dark"));
    update();
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
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
              New chat
            </Button>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Chats</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {orderedRuns(runs).map((run) => (
                <SidebarMenuItem key={run.id}>
                  <div className="relative flex items-center w-full">
                    <SidebarMenuButton asChild className="flex-1">
                      <a href={`/runs?runId=${run.id}`}>
                        <StatusDot status={run.status} />
                        <span className="truncate">{run.title?.trim() || "Untitled"}</span>
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
