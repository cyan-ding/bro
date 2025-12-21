import { MoreVerticalIcon } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

import { ListRunsResponse } from "@/lib/api";
import { Button } from "./button";

export function AppSidebar({runs} : { runs: ListRunsResponse[]}) {
  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Bro</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {runs.map((run) => (
                <SidebarMenuItem key={run.id}>
                  <SidebarMenuButton asChild>
                    <a href={`/runs?runId=${run.id}`}>
                      <span>{run.title}</span>
                      <Button variant="outline" size="icon">
                        <MoreVerticalIcon />
                      </Button>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
