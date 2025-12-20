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

import { RunMetadata } from "@/lib/api";
import { Button } from "./button";

export function AppSidebar({runs} : { runs: RunMetadata[]}) {
  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Bro</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {runs.map((run) => (
                <SidebarMenuItem key={run.title}>
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
