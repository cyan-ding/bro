"use client";

import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
} from "@/components/ui/navigation-menu";
import { ThemeToggle } from "../ThemeToggle";
import { Button } from "./button";
import { useRouter } from "next/navigation";
import { Settings } from "lucide-react"


export function DashboardNavbar() {
  return (
      <NavigationMenu>
        <NavigationMenuList>
            <NavigationMenuItem>
              <ThemeToggle/>
              <SettingsToggle/>
            </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
  );
}

function SettingsToggle() {
  const router = useRouter();
  return (
    <Button
        size="icon"
        onClick={() => router.push("/?edit=true")}
    >
        { <Settings/>}
    </Button>
)
}
